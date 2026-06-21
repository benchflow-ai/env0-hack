#!/usr/bin/env python3
"""Build LLaMA-Factory native-tool SFT data from env-0 ACP trajectories."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from export_llamafactory_data import convert_row


DEFAULT_SKILL_PREFIX = "Skills available at ~/.agents/skills: gws, slack. Read them before starting."
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ALLOWED_TOOL_KINDS = {"execute", "skill", "read", "edit", "write"}
DEFAULT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute",
            "description": "Run a shell command in the task sandbox.",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill",
            "description": "Load guidance for an available skill.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file or path in the task sandbox.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Edit a file in the task sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write content to a file in the task sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    },
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clean_text(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("\u001b[?2004h", "").replace("\u001b[?2004l", "")
    return text.strip()


def nested_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if "content" in value:
            return nested_text(value["content"])
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := nested_text(item)))
    return "" if value is None else str(value)


def extract_execute_command(title: str) -> str | None:
    for marker in (": $ ", "$ "):
        if marker in title:
            return title.split(marker, 1)[1].strip()
    return None


def parse_json_object_from_title(title: str) -> dict[str, Any] | None:
    start = title.find("{")
    end = title.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        value = json.loads(title[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def tool_call_from_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = str(event.get("kind") or "other")
    title = str(event.get("title") or "")
    arguments: dict[str, Any]
    if kind == "execute":
        arguments = {"cmd": extract_execute_command(title) or title}
    elif parsed := parse_json_object_from_title(title):
        arguments = parsed
    else:
        arguments = {}
    return {
        "id": event.get("tool_call_id") or "call_" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:16],
        "type": "function",
        "function": {
            "name": kind,
            "arguments": json.dumps(arguments, ensure_ascii=False, sort_keys=True),
        },
    }


def default_tools_for_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used: set[str] = set()
    for row in rows:
        for message in row.get("messages") or []:
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                if function.get("name"):
                    used.add(str(function["name"]))
    tools = [tool for tool in DEFAULT_TOOLS if tool["function"]["name"] in used]
    return tools or [DEFAULT_TOOLS[0]]


def task_name_from_dir(path: Path) -> str:
    name = path.name
    if "__" in name:
        return name.split("__", 1)[0]
    return name


def result_reward(result: dict[str, Any]) -> float | None:
    rewards = result.get("rewards") if isinstance(result.get("rewards"), dict) else {}
    reward = rewards.get("reward", result.get("reward"))
    return float(reward) if isinstance(reward, (int, float)) else None


def build_openai_row(traj_dir: Path, *, min_reward: float, prepend_skills_prompt: bool) -> dict[str, Any] | None:
    acp_path = traj_dir / "acp_trajectory.jsonl"
    result_path = traj_dir / "result.json"
    meta_path = traj_dir / "meta.json"
    if not acp_path.exists() or not result_path.exists():
        return None
    result = read_json(result_path)
    reward = result_reward(result)
    if reward is None or reward < min_reward:
        return None
    events = read_jsonl(acp_path)
    meta = read_json(meta_path) if meta_path.exists() else {}
    messages: list[dict[str, Any]] = []
    saw_user = False
    tool_calls = 0
    observations = 0
    skipped_tool_calls = 0
    for event in events:
        event_type = event.get("type")
        if event_type == "user_message" and not saw_user:
            text = clean_text(str(event.get("text") or ""))
            if prepend_skills_prompt:
                text = f"{DEFAULT_SKILL_PREFIX}\n\n{text}"
            messages.append({"role": "user", "content": text})
            saw_user = True
        elif event_type == "tool_call":
            kind = str(event.get("kind") or "other")
            observation = clean_text(nested_text(event.get("content")))
            if kind not in ALLOWED_TOOL_KINDS or not observation:
                skipped_tool_calls += 1
                continue
            call = tool_call_from_event(event)
            messages.append({"role": "assistant", "content": "", "tool_calls": [call]})
            tool_calls += 1
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": observation})
            observations += 1
        elif event_type == "agent_message":
            text = clean_text(str(event.get("text") or ""))
            if text:
                messages.append({"role": "assistant", "content": text})
    if not saw_user or not tool_calls:
        return None
    while messages and messages[-1]["role"] == "tool":
        messages.pop()
    if not messages or messages[-1]["role"] != "assistant":
        return None
    task_name = str(result.get("task_name") or meta.get("task") or task_name_from_dir(traj_dir))
    return {
        "id": traj_dir.name,
        "task_name": task_name,
        "score": reward,
        "passed": reward >= 1.0,
        "source_format": "acp_trajectory",
        "source_trial_dir": str(traj_dir),
        "tool_calls": tool_calls,
        "observations": observations,
        "skipped_tool_calls": skipped_tool_calls,
        "messages": messages,
        "tools": default_tools_for_rows([{"messages": messages}]),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_llamafactory(path: Path, dataset_info: Path, dataset_name: str, rows: list[dict[str, Any]]) -> int:
    converted = [item for row in rows if (item := convert_row(row, strip_thinking_text=True))]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(converted, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    info = {}
    if dataset_info.exists():
        info = json.loads(dataset_info.read_text(encoding="utf-8"))
    info[dataset_name] = {
        "file_name": path.name,
        "formatting": "sharegpt",
        "columns": {"messages": "conversations", "system": "system", "tools": "tools"},
        "tags": {
            "role_tag": "from",
            "content_tag": "value",
            "user_tag": "human",
            "assistant_tag": "gpt",
            "observation_tag": "observation",
            "function_tag": "function_call",
        },
    }
    dataset_info.parent.mkdir(parents=True, exist_ok=True)
    dataset_info.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return len(converted)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectories-root", type=Path, required=True)
    parser.add_argument("--out-openai", type=Path, required=True)
    parser.add_argument("--out-llamafactory", type=Path, required=True)
    parser.add_argument("--dataset-info", type=Path, required=True)
    parser.add_argument("--dataset-name", default="env0_tasks_lite_gemma4_sft")
    parser.add_argument("--min-reward", type=float, default=1.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-skill-prefix", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    traj_dirs = sorted(path.parent for path in args.trajectories_root.rglob("acp_trajectory.jsonl"))
    if args.limit is not None:
        traj_dirs = traj_dirs[: args.limit]
    rows = [
        row
        for traj_dir in traj_dirs
        if (row := build_openai_row(traj_dir, min_reward=args.min_reward, prepend_skills_prompt=not args.no_skill_prefix))
    ]
    write_jsonl(args.out_openai, rows)
    converted_rows = write_llamafactory(args.out_llamafactory, args.dataset_info, args.dataset_name, rows)
    report = {
        "trajectory_dirs": len(traj_dirs),
        "openai_rows": len(rows),
        "llamafactory_rows": converted_rows,
        "min_reward": args.min_reward,
        "tool_calls": sum(row["tool_calls"] for row in rows),
        "observations": sum(row["observations"] for row in rows),
        "skipped_tool_calls": sum(row["skipped_tool_calls"] for row in rows),
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
