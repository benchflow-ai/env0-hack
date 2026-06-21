#!/usr/bin/env python3
"""Convert env-0 OpenAI-style SFT rows to LLaMA-Factory ShareGPT data."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def strip_thinking(text: str) -> str:
    text = re.sub(r"(?is)<think>.*?</think>", "", text)
    text = re.sub(r"(?is)<thinking>.*?</thinking>", "", text)
    return re.sub(r"(?is)</?(?:think|thinking)>", "", text).strip()


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    normalized = []
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = function.get("name") or call.get("name")
        if not name:
            continue
        arguments = function.get("arguments", call.get("arguments", {}))
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw": arguments}
        normalized.append({"name": str(name), "arguments": arguments or {}})
    return normalized


def assistant_text(message: dict[str, Any], *, strip_thinking_text: bool) -> str:
    text = content_to_text(message.get("content")).strip()
    if strip_thinking_text:
        text = strip_thinking(text)
    return text


def user_text(message: dict[str, Any]) -> str:
    role = message.get("role")
    text = content_to_text(message.get("content")).strip()
    return text


def append_message(conversations: list[dict[str, str]], role: str, value: str) -> None:
    value = value.strip()
    if not value:
        return
    if conversations and conversations[-1]["from"] == role and role == "function_call":
        try:
            existing = json.loads(conversations[-1]["value"])
            incoming = json.loads(value)
            if not isinstance(existing, list):
                existing = [existing]
            if not isinstance(incoming, list):
                incoming = [incoming]
            conversations[-1]["value"] = json.dumps(existing + incoming, ensure_ascii=False, sort_keys=True)
        except json.JSONDecodeError:
            conversations[-1]["value"] += "\n\n" + value
    elif conversations and conversations[-1]["from"] == role:
        conversations[-1]["value"] += "\n\n" + value
    else:
        conversations.append({"from": role, "value": value})


def convert_row(row: dict[str, Any], *, strip_thinking_text: bool) -> dict[str, Any] | None:
    system_parts: list[str] = []
    conversations: list[dict[str, str]] = []
    for message in row.get("messages") or []:
        role = message.get("role")
        if role == "system":
            text = content_to_text(message.get("content")).strip()
            if text:
                system_parts.append(text)
        elif role == "user":
            text = user_text(message)
            append_message(conversations, "human", text)
        elif role == "tool":
            append_message(conversations, "observation", content_to_text(message.get("content")))
        elif role == "assistant":
            tool_calls = normalize_tool_calls(message.get("tool_calls"))
            if tool_calls:
                append_message(conversations, "function_call", json.dumps(tool_calls, ensure_ascii=False, sort_keys=True))
            else:
                append_message(conversations, "gpt", assistant_text(message, strip_thinking_text=strip_thinking_text))
    if len(conversations) < 2 or conversations[-1]["from"] not in {"gpt", "function_call"}:
        return None
    item = {
        "id": row.get("id"),
        "task_name": row.get("task_name"),
        "score": row.get("score"),
        "system": "\n\n".join(system_parts),
        "tools": json.dumps(row.get("tools") or [], ensure_ascii=False, sort_keys=True),
        "conversations": conversations,
    }
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset-info", type=Path, required=True)
    parser.add_argument("--dataset-name", default="env0_gemma4_sft")
    parser.add_argument("--strip-thinking", action="store_true")
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    converted = [item for row in rows if (item := convert_row(row, strip_thinking_text=args.strip_thinking))]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(converted, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    dataset_info = {}
    if args.dataset_info.exists():
        dataset_info = json.loads(args.dataset_info.read_text(encoding="utf-8"))
    dataset_info[args.dataset_name] = {
        "file_name": args.out.name,
        "formatting": "sharegpt",
        "columns": {
            "messages": "conversations",
            "system": "system",
            "tools": "tools",
        },
        "tags": {
            "role_tag": "from",
            "content_tag": "value",
            "user_tag": "human",
            "assistant_tag": "gpt",
            "observation_tag": "observation",
            "function_tag": "function_call",
        },
    }
    args.dataset_info.parent.mkdir(parents=True, exist_ok=True)
    args.dataset_info.write_text(json.dumps(dataset_info, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"input_rows": len(rows), "converted_rows": len(converted), "out": str(args.out)}, indent=2, sort_keys=True))
    if not converted:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
