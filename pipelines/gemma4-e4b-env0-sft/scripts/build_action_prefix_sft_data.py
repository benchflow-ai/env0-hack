#!/usr/bin/env python3
"""Build next-action SFT rows from env-0 ACP trajectories.

Each output row contains the task prompt plus a compact previous execution
trace in the user message, and supervises only the next assistant action. This
avoids training on entire trajectories where early actions dominate and late
actions may be truncated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_acp_sft_data import (
    ALLOWED_TOOL_KINDS,
    DEFAULT_SKILL_PREFIX,
    DEFAULT_TOOLS,
    clean_text,
    default_tools_for_rows,
    nested_text,
    read_json,
    read_jsonl,
    result_reward,
    task_name_from_dir,
    tool_call_from_event,
    write_llamafactory,
    write_jsonl,
)


def short_observation(event: dict[str, Any], *, max_chars: int) -> str:
    text = clean_text(nested_text(event.get("content")))
    if len(text) <= max_chars:
        return text
    return text[: max_chars // 2].rstrip() + "\n...[observation truncated]...\n" + text[-max_chars // 2 :].lstrip()


def trim_left(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "[earlier execution trace omitted]\n" + text[-max_chars:].lstrip()


def trace_block(history: list[dict[str, str]], *, max_chars: int) -> str:
    if not history:
        return ""
    parts = ["Previous execution trace:"]
    for idx, item in enumerate(history, start=1):
        if item["role"] == "assistant_tool":
            parts.append(f"\n[{idx}] assistant tool call:\n{item['text']}")
        elif item["role"] == "tool_observation":
            parts.append(f"\n[{idx}] observation:\n{item['text']}")
        elif item["role"] == "assistant_final":
            parts.append(f"\n[{idx}] assistant message:\n{item['text']}")
    return trim_left("\n".join(parts).strip(), max_chars=max_chars)


def row_user_content(task_prompt: str, history: list[dict[str, str]], *, max_history_chars: int) -> str:
    trace = trace_block(history, max_chars=max_history_chars)
    if not trace:
        return task_prompt
    return f"{task_prompt}\n\n{trace}\n\nContinue with the next assistant action."


def task_prompt_from_events(events: list[dict[str, Any]], *, prepend_skill_prefix: bool) -> str | None:
    for event in events:
        if event.get("type") != "user_message":
            continue
        text = clean_text(str(event.get("text") or ""))
        if prepend_skill_prefix:
            text = f"{DEFAULT_SKILL_PREFIX}\n\n{text}"
        return text
    return None


def build_rows_from_trajectory(
    traj_dir: Path,
    *,
    min_reward: float,
    prepend_skill_prefix: bool,
    max_history_chars: int,
    max_observation_chars: int,
    include_final: bool,
) -> list[dict[str, Any]]:
    acp_path = traj_dir / "acp_trajectory.jsonl"
    result_path = traj_dir / "result.json"
    meta_path = traj_dir / "meta.json"
    if not acp_path.exists() or not result_path.exists():
        return []
    result = read_json(result_path)
    reward = result_reward(result)
    if reward is None or reward < min_reward:
        return []
    events = read_jsonl(acp_path)
    prompt = task_prompt_from_events(events, prepend_skill_prefix=prepend_skill_prefix)
    if not prompt:
        return []
    meta = read_json(meta_path) if meta_path.exists() else {}
    task_name = str(result.get("task_name") or meta.get("task") or task_name_from_dir(traj_dir))

    rows: list[dict[str, Any]] = []
    history: list[dict[str, str]] = []
    action_index = 0
    skipped_tool_calls = 0
    for event in events:
        event_type = event.get("type")
        if event_type == "tool_call":
            kind = str(event.get("kind") or "other")
            observation = short_observation(event, max_chars=max_observation_chars)
            if kind not in ALLOWED_TOOL_KINDS or not observation:
                skipped_tool_calls += 1
                continue
            call = tool_call_from_event(event)
            user_content = row_user_content(prompt, history, max_history_chars=max_history_chars)
            tools = default_tools_for_rows([{"messages": [{"tool_calls": [call]}]}])
            rows.append(
                {
                    "id": f"{traj_dir.name}::action-{action_index:03d}",
                    "task_name": task_name,
                    "score": reward,
                    "passed": reward >= 1.0,
                    "source_format": "acp_action_prefix",
                    "source_trial_dir": str(traj_dir),
                    "action_index": action_index,
                    "messages": [
                        {"role": "user", "content": user_content},
                        {"role": "assistant", "content": "", "tool_calls": [call]},
                    ],
                    "skipped_tool_calls": skipped_tool_calls,
                    "tools": tools,
                }
            )
            action_index += 1
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            history.append(
                {
                    "role": "assistant_tool",
                    "text": json.dumps(
                        {"name": function.get("name"), "arguments": function.get("arguments")},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
            history.append({"role": "tool_observation", "text": observation})
        elif include_final and event_type == "agent_message":
            text = clean_text(str(event.get("text") or ""))
            if not text:
                continue
            user_content = row_user_content(prompt, history, max_history_chars=max_history_chars)
            rows.append(
                {
                    "id": f"{traj_dir.name}::action-{action_index:03d}",
                    "task_name": task_name,
                    "score": reward,
                    "passed": reward >= 1.0,
                    "source_format": "acp_action_prefix",
                    "source_trial_dir": str(traj_dir),
                    "action_index": action_index,
                    "messages": [
                        {"role": "user", "content": user_content},
                        {"role": "assistant", "content": text},
                    ],
                    "skipped_tool_calls": skipped_tool_calls,
                    "tools": DEFAULT_TOOLS,
                }
            )
            action_index += 1
            history.append({"role": "assistant_final", "text": text})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectories-root", type=Path, required=True)
    parser.add_argument("--out-openai", type=Path, required=True)
    parser.add_argument("--out-llamafactory", type=Path, required=True)
    parser.add_argument("--dataset-info", type=Path, required=True)
    parser.add_argument("--dataset-name", default="env0_tasks_lite_action_prefix_sft")
    parser.add_argument("--min-reward", type=float, default=1.0)
    parser.add_argument("--limit-trajectories", type=int)
    parser.add_argument("--limit-rows", type=int)
    parser.add_argument("--max-history-chars", type=int, default=6000)
    parser.add_argument("--max-observation-chars", type=int, default=1200)
    parser.add_argument("--include-final", action="store_true")
    parser.add_argument("--no-skill-prefix", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    traj_dirs = sorted(path.parent for path in args.trajectories_root.rglob("acp_trajectory.jsonl"))
    if args.limit_trajectories is not None:
        traj_dirs = traj_dirs[: args.limit_trajectories]
    rows: list[dict[str, Any]] = []
    for traj_dir in traj_dirs:
        rows.extend(
            build_rows_from_trajectory(
                traj_dir,
                min_reward=args.min_reward,
                prepend_skill_prefix=not args.no_skill_prefix,
                max_history_chars=args.max_history_chars,
                max_observation_chars=args.max_observation_chars,
                include_final=args.include_final,
            )
        )
    if args.limit_rows is not None:
        rows = rows[: args.limit_rows]
    write_jsonl(args.out_openai, rows)
    converted_rows = write_llamafactory(args.out_llamafactory, args.dataset_info, args.dataset_name, rows)
    report = {
        "trajectory_dirs": len(traj_dirs),
        "openai_rows": len(rows),
        "llamafactory_rows": converted_rows,
        "min_reward": args.min_reward,
        "max_history_chars": args.max_history_chars,
        "max_observation_chars": args.max_observation_chars,
        "include_final": args.include_final,
        "out_openai": str(args.out_openai),
        "out_llamafactory": str(args.out_llamafactory),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not rows or not converted_rows:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
