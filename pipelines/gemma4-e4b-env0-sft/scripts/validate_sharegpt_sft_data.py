#!/usr/bin/env python3
"""Validate env-0 ShareGPT SFT data before LLaMA-Factory training."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ASSISTANT_SIDE = {"gpt", "function_call"}
USER_SIDE = {"human", "observation"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_tools(raw: Any) -> tuple[set[str], str | None]:
    if isinstance(raw, str):
        try:
            tools = json.loads(raw)
        except json.JSONDecodeError:
            return set(), "bad_tools_json"
    else:
        tools = raw
    if not isinstance(tools, list) or not tools:
        return set(), "empty_tools"
    names = set()
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        name = function.get("name")
        if name:
            names.add(str(name))
    return names, None if names else "empty_tools"


def parse_function_calls(value: Any) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(value, str):
        try:
            calls = json.loads(value)
        except json.JSONDecodeError:
            return [], "bad_function_json"
    else:
        calls = value
    if isinstance(calls, dict):
        calls = [calls]
    if not isinstance(calls, list) or not calls:
        return [], "bad_function_json"
    if not all(isinstance(call, dict) for call in calls):
        return [], "bad_function_json"
    return calls, None


def add_error(
    errors: Counter[str],
    examples: dict[str, list[dict[str, Any]]],
    invalid_row_ids: set[str],
    reason: str,
    row: dict[str, Any],
    idx: int | None,
) -> None:
    errors[reason] += 1
    invalid_row_ids.add(str(row.get("id") or "<missing-id>"))
    if len(examples[reason]) < 20:
        examples[reason].append(
            {
                "id": row.get("id"),
                "task_name": row.get("task_name"),
                "turn_index": idx,
            }
        )


def validate_row(row: dict[str, Any], *, mode: str) -> tuple[Counter[str], dict[str, list[dict[str, Any]]], set[str]]:
    errors: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid_row_ids: set[str] = set()
    conversations = row.get("conversations")
    if not isinstance(conversations, list) or len(conversations) < 2:
        add_error(errors, examples, invalid_row_ids, "invalid_message_count", row, None)
        return errors, examples, invalid_row_ids
    tool_names, tool_error = parse_tools(row.get("tools"))
    if tool_error:
        add_error(errors, examples, invalid_row_ids, tool_error, row, None)
    for idx, message in enumerate(conversations):
        role = message.get("from") if isinstance(message, dict) else None
        expected = USER_SIDE if idx % 2 == 0 else ASSISTANT_SIDE
        if role not in expected:
            add_error(errors, examples, invalid_row_ids, "invalid_role_parity", row, idx)
        value = str(message.get("value") or "") if isinstance(message, dict) else ""
        if role in ASSISTANT_SIDE and not value.strip():
            add_error(errors, examples, invalid_row_ids, "empty_response", row, idx)
        if role == "function_call":
            calls, function_error = parse_function_calls(message.get("value"))
            if function_error:
                add_error(errors, examples, invalid_row_ids, function_error, row, idx)
                continue
            for call in calls:
                name = str(call.get("name") or "")
                if name == "other":
                    add_error(errors, examples, invalid_row_ids, "other_function_call", row, idx)
                if tool_names and name not in tool_names:
                    add_error(errors, examples, invalid_row_ids, "missing_tool_definition", row, idx)
            is_terminal = idx == len(conversations) - 1
            next_role = conversations[idx + 1].get("from") if not is_terminal and isinstance(conversations[idx + 1], dict) else None
            if mode == "full":
                if is_terminal or next_role != "observation":
                    add_error(errors, examples, invalid_row_ids, "terminal_or_unobserved_function_call", row, idx)
            elif mode == "next-action":
                if not is_terminal and next_role != "observation":
                    add_error(errors, examples, invalid_row_ids, "terminal_or_unobserved_function_call", row, idx)
    if mode == "full" and conversations[-1].get("from") != "gpt":
        add_error(errors, examples, invalid_row_ids, "non_gpt_terminal_message", row, len(conversations) - 1)
    return errors, examples, invalid_row_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dataset-info", type=Path)
    parser.add_argument("--dataset-name")
    parser.add_argument("--mode", choices=["full", "next-action"], default="full")
    parser.add_argument("--expected-rows", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    rows = load_json(args.input)
    if not isinstance(rows, list):
        raise SystemExit("Input must be a JSON list.")
    errors: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid_row_ids: set[str] = set()
    for row in rows:
        row_errors, row_examples, row_invalid_ids = validate_row(row, mode=args.mode)
        errors.update(row_errors)
        invalid_row_ids.update(row_invalid_ids)
        for reason, values in row_examples.items():
            examples[reason].extend(values)
            examples[reason] = examples[reason][:20]
    if args.expected_rows is not None and len(rows) != args.expected_rows:
        errors["unexpected_row_count"] += 1
        examples["unexpected_row_count"].append(
            {
                "id": None,
                "task_name": f"expected={args.expected_rows}, actual={len(rows)}",
                "turn_index": None,
            }
        )
    likely = len(rows) - len(invalid_row_ids)
    report = {
        "status": "pass" if not errors else "fail",
        "rows": len(rows),
        "likely_llamafactory_eligible_rows": likely if errors else len(rows),
        "drop_risk_rows": len(rows) - (likely if errors else len(rows)),
        "errors": dict(errors),
        "examples": dict(examples),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "rows", "likely_llamafactory_eligible_rows", "drop_risk_rows", "errors")}, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
