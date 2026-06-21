#!/usr/bin/env python3
"""Compare a runtime OpenAI request with an env-0 SFT training prefix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from export_llamafactory_data import content_to_text


def load_json_or_jsonl(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        raise SystemExit(f"Empty input: {path}")
    if stripped.startswith("[") or stripped.startswith("{"):
        return json.loads(stripped)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def select_item(payload: Any, *, item_id: str | None = None, index: int = 0) -> dict[str, Any]:
    if isinstance(payload, list):
        if item_id is not None:
            for item in payload:
                if isinstance(item, dict) and str(item.get("id")) == item_id:
                    return item
            raise SystemExit(f"Could not find id={item_id!r}.")
        try:
            item = payload[index]
        except IndexError as exc:
            raise SystemExit(f"Index {index} out of range for {len(payload)} items.") from exc
        if not isinstance(item, dict):
            raise SystemExit("Selected item must be a JSON object.")
        return item
    if isinstance(payload, dict):
        return payload
    raise SystemExit("Input must be a JSON object, JSON list, or JSONL file.")


def runtime_body(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("request"), dict):
        body = payload["request"].get("body")
        if isinstance(body, dict):
            return body
    if isinstance(payload.get("body"), dict) and (
        "messages" in payload["body"] or "tools" in payload["body"]
    ):
        return payload["body"]
    if "messages" in payload or "tools" in payload:
        return payload
    raise SystemExit("Runtime input must contain request.body, body, or top-level messages/tools.")


def parse_json_maybe(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def normalize_tool_call(call: dict[str, Any], *, ignore_ids: bool) -> dict[str, Any]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    normalized = {
        "type": call.get("type", "function"),
        "function": {
            "name": str(function.get("name") or call.get("name") or ""),
            "arguments": parse_json_maybe(function.get("arguments", call.get("arguments", {}))) or {},
        },
    }
    if not ignore_ids and call.get("id"):
        normalized["id"] = str(call["id"])
    return normalized


def normalize_message(message: dict[str, Any], *, ignore_ids: bool) -> dict[str, Any]:
    out: dict[str, Any] = {"role": message.get("role")}
    if "content" in message:
        out["content"] = content_to_text(message.get("content")).strip()
    if message.get("name"):
        out["name"] = str(message["name"])
    if message.get("tool_call_id") and not ignore_ids:
        out["tool_call_id"] = str(message["tool_call_id"])
    if message.get("tool_calls"):
        out["tool_calls"] = [
            normalize_tool_call(call, ignore_ids=ignore_ids)
            for call in message.get("tool_calls") or []
            if isinstance(call, dict)
        ]
    return out


def normalize_tools(raw_tools: Any) -> list[dict[str, Any]]:
    tools = parse_json_maybe(raw_tools)
    if not isinstance(tools, list):
        return []
    return tools


def sharegpt_to_openai_messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if row.get("system"):
        messages.append({"role": "system", "content": row["system"]})
    pending_tool_call_id = None
    tool_call_index = 0
    for message in row.get("conversations") or []:
        role = message.get("from") if isinstance(message, dict) else None
        value = str(message.get("value") or "") if isinstance(message, dict) else ""
        if role == "human":
            messages.append({"role": "user", "content": value})
        elif role == "gpt":
            messages.append({"role": "assistant", "content": value})
        elif role == "function_call":
            calls = parse_json_maybe(value)
            if isinstance(calls, dict):
                calls = [calls]
            if not isinstance(calls, list):
                calls = []
            tool_calls = []
            for call in calls:
                if not isinstance(call, dict):
                    continue
                tool_call_index += 1
                call_id = f"sharegpt_call_{tool_call_index}"
                pending_tool_call_id = call_id
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": call.get("name"),
                            "arguments": json.dumps(call.get("arguments") or {}, sort_keys=True),
                        },
                    }
                )
            messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})
        elif role == "observation":
            messages.append({"role": "tool", "tool_call_id": pending_tool_call_id, "content": value})
    return messages


def training_messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(row.get("messages"), list):
        return row["messages"]
    if isinstance(row.get("conversations"), list):
        return sharegpt_to_openai_messages(row)
    raise SystemExit("Training row must contain OpenAI messages or ShareGPT conversations.")


def choose_target_index(messages: list[dict[str, Any]], requested: int | None) -> int:
    if requested is not None:
        if requested < 0 or requested >= len(messages):
            raise SystemExit(f"target-index={requested} out of range for {len(messages)} messages.")
        return requested
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].get("role") == "assistant":
            return idx
    raise SystemExit("Training row has no assistant target message.")


def summarize_target(message: dict[str, Any]) -> dict[str, Any]:
    calls = message.get("tool_calls") or []
    names = []
    for call in calls:
        if isinstance(call, dict):
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            names.append(str(function.get("name") or call.get("name") or ""))
    return {
        "role": message.get("role"),
        "content_chars": len(content_to_text(message.get("content"))),
        "tool_call_count": len(calls),
        "tool_names": names,
    }


def first_mismatch(left: Any, right: Any, path: str = "$") -> dict[str, Any] | None:
    if type(left) is not type(right):
        return {"path": path, "runtime": left, "training": right, "reason": "type_mismatch"}
    if isinstance(left, dict):
        keys = sorted(set(left) | set(right))
        for key in keys:
            if key not in left or key not in right:
                return {
                    "path": f"{path}.{key}",
                    "runtime": left.get(key),
                    "training": right.get(key),
                    "reason": "missing_key",
                }
            mismatch = first_mismatch(left[key], right[key], f"{path}.{key}")
            if mismatch:
                return mismatch
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return {"path": path, "runtime": len(left), "training": len(right), "reason": "length_mismatch"}
        for idx, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            mismatch = first_mismatch(left_item, right_item, f"{path}[{idx}]")
            if mismatch:
                return mismatch
        return None
    if left != right:
        return {"path": path, "runtime": left, "training": right, "reason": "value_mismatch"}
    return None


def render_token_ids(messages: list[dict[str, Any]], tools: list[dict[str, Any]], tokenizer_name: str) -> list[int]:
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - optional spendful/remote dependency.
        raise SystemExit("Token rendering requires `transformers`.") from exc

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, trust_remote_code=True)
    kwargs: dict[str, Any] = {"tokenize": True, "add_generation_prompt": True}
    if tools:
        kwargs["tools"] = tools
    try:
        ids = tokenizer.apply_chat_template(messages, **kwargs)
    except TypeError:
        kwargs.pop("tools", None)
        ids = tokenizer.apply_chat_template(messages, **kwargs)
    if hasattr(ids, "tolist"):
        ids = ids.tolist()
    return [int(item) for item in ids]


def audit(
    runtime: dict[str, Any],
    train_row: dict[str, Any],
    *,
    target_index: int | None = None,
    ignore_ids: bool = False,
    tokenizer_name: str | None = None,
) -> dict[str, Any]:
    body = runtime_body(runtime)
    messages = training_messages(train_row)
    target_idx = choose_target_index(messages, target_index)
    training_prefix = messages[:target_idx]
    runtime_messages = [
        normalize_message(message, ignore_ids=ignore_ids)
        for message in body.get("messages") or []
        if isinstance(message, dict)
    ]
    normalized_prefix = [
        normalize_message(message, ignore_ids=ignore_ids)
        for message in training_prefix
        if isinstance(message, dict)
    ]
    runtime_tools = normalize_tools(body.get("tools") or [])
    training_tools = normalize_tools(train_row.get("tools") or [])
    messages_mismatch = first_mismatch(runtime_messages, normalized_prefix, "$.messages")
    tools_mismatch = first_mismatch(runtime_tools, training_tools, "$.tools")
    token_mismatch: dict[str, Any] | None = None
    token_counts: dict[str, int] = {}
    if tokenizer_name:
        runtime_token_ids = render_token_ids(runtime_messages, runtime_tools, tokenizer_name)
        training_token_ids = render_token_ids(normalized_prefix, training_tools, tokenizer_name)
        token_counts = {
            "runtime_token_count": len(runtime_token_ids),
            "training_prefix_token_count": len(training_token_ids),
        }
        token_mismatch = first_mismatch(runtime_token_ids, training_token_ids, "$.token_ids")
    report = {
        "status": "pass"
        if messages_mismatch is None and tools_mismatch is None and token_mismatch is None
        else "fail",
        "training_id": train_row.get("id"),
        "training_task_name": train_row.get("task_name"),
        "target_index": target_idx,
        "target": summarize_target(messages[target_idx]),
        "runtime_message_count": len(runtime_messages),
        "training_prefix_message_count": len(normalized_prefix),
        "runtime_tool_count": len(runtime_tools),
        "training_tool_count": len(training_tools),
        "messages_equal": messages_mismatch is None,
        "tools_equal": tools_mismatch is None,
        "token_ids_equal": token_mismatch is None if tokenizer_name else None,
        "mismatches": [item for item in (messages_mismatch, tools_mismatch, token_mismatch) if item],
    }
    report.update(token_counts)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-request", type=Path, required=True)
    parser.add_argument("--training-row", type=Path, required=True)
    parser.add_argument("--training-id")
    parser.add_argument("--training-index", type=int, default=0)
    parser.add_argument("--target-index", type=int)
    parser.add_argument("--ignore-tool-call-ids", action="store_true")
    parser.add_argument("--tokenizer", help="Optional HF tokenizer name/path for token-id parity.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    runtime = runtime_body(select_item(load_json_or_jsonl(args.runtime_request)))
    train_row = select_item(
        load_json_or_jsonl(args.training_row),
        item_id=args.training_id,
        index=args.training_index,
    )
    report = audit(
        runtime,
        train_row,
        target_index=args.target_index,
        ignore_ids=args.ignore_tool_call_ids,
        tokenizer_name=args.tokenizer,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
