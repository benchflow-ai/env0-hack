#!/usr/bin/env python3
"""Select a deterministic tiny-overfit slice from env-0 OpenAI SFT rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from export_llamafactory_data import convert_row


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def task_name(row: dict[str, Any]) -> str:
    return str(row.get("task_name") or row.get("id") or "")


def family(row: dict[str, Any]) -> str:
    return task_name(row).split("-", 1)[0]


def count_tool_calls(row: dict[str, Any]) -> int:
    explicit = row.get("tool_calls")
    if isinstance(explicit, int):
        return explicit
    count = 0
    for message in row.get("messages") or []:
        count += len(message.get("tool_calls") or []) if isinstance(message, dict) else 0
    return count


def row_chars(row: dict[str, Any]) -> int:
    return len(json.dumps(row.get("messages") or [], ensure_ascii=False, sort_keys=True))


def row_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return (count_tool_calls(row), row_chars(row), task_name(row))


def read_task_filter(path: Path | None) -> set[str]:
    if path is None:
        return set()
    payload = load_json(path)
    if isinstance(payload, list):
        values = payload
    else:
        values = payload.get("tasks") or []
    out = set()
    for item in values:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict) and item.get("task_name"):
            out.add(str(item["task_name"]))
    return out


def select_rows(
    rows: list[dict[str, Any]],
    *,
    count: int,
    task_filter: set[str],
    families: set[str],
    max_tool_calls: int | None,
) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        if task_filter and task_name(row) not in task_filter:
            continue
        if families and family(row) not in families:
            continue
        if max_tool_calls is not None and count_tool_calls(row) > max_tool_calls:
            continue
        candidates.append(row)
    if not candidates:
        raise SystemExit("No rows matched the tiny-overfit selection filters.")
    candidates.sort(key=row_sort_key)
    selected: list[dict[str, Any]] = []
    seen_families: set[str] = set()
    for row in candidates:
        row_family = family(row)
        if row_family in seen_families:
            continue
        selected.append(row)
        seen_families.add(row_family)
        if len(selected) == count:
            return selected
    for row in candidates:
        if row in selected:
            continue
        selected.append(row)
        if len(selected) == count:
            return selected
    return selected


def repeat_rows(rows: list[dict[str, Any]], repeat: int) -> list[dict[str, Any]]:
    if repeat <= 1:
        return rows
    out = []
    for row in rows:
        for idx in range(repeat):
            item = dict(row)
            item["id"] = f"{row.get('id') or row.get('task_name')}::repeat-{idx:03d}"
            item["source_id"] = row.get("id")
            out.append(item)
    return out


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
        info = load_json(dataset_info)
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
    parser.add_argument("--input-openai", type=Path, required=True)
    parser.add_argument("--out-openai", type=Path, required=True)
    parser.add_argument("--out-llamafactory", type=Path, required=True)
    parser.add_argument("--dataset-info", type=Path, required=True)
    parser.add_argument("--dataset-name", default="env0_tasks_lite_tiny_overfit_sft")
    parser.add_argument("--task-list", type=Path)
    parser.add_argument("--families", nargs="*", default=[])
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--max-tool-calls", type=int)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.count < 1:
        raise SystemExit("--count must be >= 1.")
    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1.")

    rows = load_jsonl(args.input_openai)
    selected = select_rows(
        rows,
        count=args.count,
        task_filter=read_task_filter(args.task_list),
        families={str(item) for item in args.families},
        max_tool_calls=args.max_tool_calls,
    )
    repeated = repeat_rows(selected, args.repeat)
    write_jsonl(args.out_openai, repeated)
    converted_rows = write_llamafactory(args.out_llamafactory, args.dataset_info, args.dataset_name, repeated)
    report = {
        "input_rows": len(rows),
        "unique_selected_rows": len(selected),
        "output_openai_rows": len(repeated),
        "output_llamafactory_rows": converted_rows,
        "repeat": args.repeat,
        "dataset_name": args.dataset_name,
        "selected": [
            {
                "id": row.get("id"),
                "task_name": task_name(row),
                "family": family(row),
                "tool_calls": count_tool_calls(row),
                "message_chars": row_chars(row),
            }
            for row in selected
        ],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not repeated or not converted_rows:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
