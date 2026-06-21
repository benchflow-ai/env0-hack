#!/usr/bin/env python3
"""Zero-spend tests for the Gemma 4 E4B env-0 SFT pipeline."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "pipelines" / "gemma4-e4b-env0-sft" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "run_pipeline.py"
EXPORT_SCRIPT = SCRIPT_DIR / "export_llamafactory_data.py"
VALIDATE_SCRIPT = SCRIPT_DIR / "validate_sharegpt_sft_data.py"
ACP_BUILD_SCRIPT = SCRIPT_DIR / "build_acp_sft_data.py"
PARITY_SCRIPT = SCRIPT_DIR / "audit_prompt_parity.py"
TINY_SLICE_SCRIPT = SCRIPT_DIR / "select_tiny_overfit_slice.py"
spec = importlib.util.spec_from_file_location("gemma4_sft_pipeline", SCRIPT)
assert spec and spec.loader
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)
export_spec = importlib.util.spec_from_file_location("gemma4_sft_export", EXPORT_SCRIPT)
assert export_spec and export_spec.loader
exporter = importlib.util.module_from_spec(export_spec)
export_spec.loader.exec_module(exporter)
validate_spec = importlib.util.spec_from_file_location("gemma4_sft_validate", VALIDATE_SCRIPT)
assert validate_spec and validate_spec.loader
validator = importlib.util.module_from_spec(validate_spec)
validate_spec.loader.exec_module(validator)
acp_spec = importlib.util.spec_from_file_location("gemma4_sft_acp_build", ACP_BUILD_SCRIPT)
assert acp_spec and acp_spec.loader
acp_builder = importlib.util.module_from_spec(acp_spec)
acp_spec.loader.exec_module(acp_builder)
parity_spec = importlib.util.spec_from_file_location("gemma4_sft_prompt_parity", PARITY_SCRIPT)
assert parity_spec and parity_spec.loader
parity = importlib.util.module_from_spec(parity_spec)
parity_spec.loader.exec_module(parity)
tiny_spec = importlib.util.spec_from_file_location("gemma4_sft_tiny_slice", TINY_SLICE_SCRIPT)
assert tiny_spec and tiny_spec.loader
tiny_slice = importlib.util.module_from_spec(tiny_spec)
tiny_spec.loader.exec_module(tiny_slice)


class PipelineTests(unittest.TestCase):
    def test_provider_selection_prefers_fireworks_then_prime(self) -> None:
        config = {"gpu_provider": "auto", "provider_order": ["fireworks", "prime"]}
        selected = pipeline.select_provider(config, {"FIREWORKS_API_KEY": "fw", "PRIMEINTELLECT_API_KEY": "pi"})
        self.assertEqual(selected["provider"], "fireworks")
        selected = pipeline.select_provider(config, {"PRIMEINTELLECT_API_KEY": "pi"})
        self.assertEqual(selected["provider"], "prime")
        selected = pipeline.select_provider(config, {})
        self.assertIsNone(selected["provider"])

    def test_google_workspace_filter_excludes_slack_and_stripe(self) -> None:
        self.assertTrue(pipeline.google_workspace_core({"keywords": ["gmail", "safety"]}))
        self.assertTrue(pipeline.google_workspace_core({"keywords": ["auth", "gdrive"]}))
        self.assertFalse(pipeline.google_workspace_core({"keywords": ["gdoc", "slack"]}))
        self.assertFalse(pipeline.google_workspace_core({"keywords": ["stripe", "auth"]}))

    def test_tasks_lite_train_sample60_task_list_is_stratified(self) -> None:
        path = ROOT / "pipelines" / "gemma4-e4b-env0-sft" / "task_lists" / "tasks_lite_train_sample60.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        tasks = payload["tasks"]
        self.assertEqual(len(tasks), 60)
        self.assertEqual(len(set(tasks)), 60)
        counts = Counter(task.split("-", 1)[0] for task in tasks)
        self.assertEqual(dict(sorted(counts.items())), payload["family_counts"])
        self.assertEqual(payload["count"], 60)

    def test_fireworks_model_probe_recommends_prime_when_student_is_not_tunable(self) -> None:
        models = [
            {
                "name": "accounts/fireworks/models/gemma-4-e4b",
                "displayName": "Gemma 4 E4B",
                "baseModelDetails": {"tunable": False},
            }
        ]
        matched = pipeline.find_fireworks_model(models, "google/gemma-4-E4B-it")
        self.assertIsNotNone(matched)
        fireworks = {
            "available": True,
            "matched_student_model": pipeline.safe_fireworks_model(matched),
            "managed_sft_supported": False,
        }
        provider = pipeline.recommend_provider(
            {"gpu_provider": "auto", "provider_order": ["fireworks", "prime"]},
            {"FIREWORKS_API_KEY": "fw", "PRIMEINTELLECT_API_KEY": "pi"},
            fireworks,
        )
        self.assertEqual(provider["provider"], "prime")

    def test_extracts_strict_sft_rows_from_synthetic_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "teacher-job" / "gdrive-task__abc"
            trace = rollout / "trajectory"
            trace.mkdir(parents=True)
            (rollout / "result.json").write_text(
                json.dumps({"task_name": "gdrive-task", "score": 1.0, "rewards": {"details": {}}}),
                encoding="utf-8",
            )
            llm_item = {
                "request": {
                    "body": {
                        "messages": [{"role": "user", "content": "Share the right file."}],
                        "tools": [{"type": "function", "function": {"name": "bash"}}],
                    }
                },
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {"name": "bash", "arguments": "{\"cmd\":\"echo ok\"}"},
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                },
            }
            (trace / "llm_trajectory.jsonl").write_text(json.dumps(llm_item) + "\n", encoding="utf-8")
            config = {"data": {"min_score": 1.0, "label_last_assistant_only": True}}
            rows, manifest = pipeline.build_rows_from_jobs(config, [root / "teacher-job"], {"gdrive-task"})
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["task_name"], "gdrive-task")
            self.assertEqual(manifest["selected_rows"], 1)

    def test_converts_openai_row_to_sharegpt(self) -> None:
        row = {
            "id": "row-1",
            "task_name": "gdrive-task",
            "score": 1.0,
            "messages": [
                {"role": "system", "content": "Use tools carefully."},
                {"role": "user", "content": "Share the file."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "bash", "arguments": "{\"cmd\":\"echo ok\"}"},
                        }
                    ],
                },
            ],
        }
        item = exporter.convert_row(row, strip_thinking_text=True)
        self.assertIsNotNone(item)
        self.assertEqual(item["system"], "Use tools carefully.")
        self.assertEqual(item["conversations"][0]["from"], "human")
        self.assertEqual(item["conversations"][1]["from"], "function_call")
        self.assertIn("\"name\": \"bash\"", item["conversations"][1]["value"])
        self.assertIn("tools", item)

    def test_merges_consecutive_function_calls_as_valid_json(self) -> None:
        conversations = []
        exporter.append_message(conversations, "function_call", '[{"name":"one","arguments":{}}]')
        exporter.append_message(conversations, "function_call", '[{"name":"two","arguments":{}}]')
        merged = json.loads(conversations[0]["value"])
        self.assertEqual([call["name"] for call in merged], ["one", "two"])

    def test_acp_rows_include_matching_tool_schema(self) -> None:
        tools = acp_builder.default_tools_for_rows(
            [
                {
                    "messages": [
                        {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": "execute", "arguments": "{}"},
                                }
                            ],
                        }
                    ]
                }
            ]
        )
        self.assertEqual([tool["function"]["name"] for tool in tools], ["execute"])
        self.assertIn("parameters", tools[0]["function"])

    def test_sharegpt_validator_accepts_full_tool_sequence(self) -> None:
        row = {
            "id": "valid",
            "task_name": "gmail-task",
            "tools": json.dumps(acp_builder.DEFAULT_TOOLS[:1]),
            "conversations": [
                {"from": "human", "value": "Find the email."},
                {
                    "from": "function_call",
                    "value": json.dumps([{"name": "execute", "arguments": {"cmd": "echo ok"}}]),
                },
                {"from": "observation", "value": "ok"},
                {"from": "gpt", "value": "Done."},
            ],
        }
        errors, examples, invalid_row_ids = validator.validate_row(row, mode="full")
        self.assertEqual(errors, {})
        self.assertEqual(examples, {})
        self.assertEqual(invalid_row_ids, set())

    def test_sharegpt_validator_counts_invalid_rows_beyond_example_cap(self) -> None:
        errors = {}
        invalid_row_ids = set()
        for idx in range(25):
            row = {
                "id": f"invalid-{idx}",
                "task_name": "gmail-task",
                "tools": "[]",
                "conversations": [
                    {"from": "human", "value": "Find the email."},
                    {"from": "gpt", "value": "Done."},
                ],
            }
            row_errors, _examples, row_invalid_ids = validator.validate_row(row, mode="full")
            for key, value in row_errors.items():
                errors[key] = errors.get(key, 0) + value
            invalid_row_ids.update(row_invalid_ids)
        self.assertEqual(errors["empty_tools"], 25)
        self.assertEqual(len(invalid_row_ids), 25)

    def test_prompt_parity_accepts_matching_runtime_request(self) -> None:
        tools = [{"type": "function", "function": {"name": "execute", "parameters": {"type": "object"}}}]
        runtime_request = {
            "messages": [
                {"role": "system", "content": "Use tools carefully."},
                {"role": "user", "content": "Find the email."},
            ],
            "tools": tools,
        }
        training_row = {
            "id": "row-1",
            "task_name": "gmail-task",
            "tools": tools,
            "messages": [
                {"role": "system", "content": "Use tools carefully."},
                {"role": "user", "content": "Find the email."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "execute", "arguments": "{\"cmd\":\"echo ok\"}"},
                        }
                    ],
                },
            ],
        }
        report = parity.audit(runtime_request, training_row)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["messages_equal"])
        self.assertTrue(report["tools_equal"])

    def test_prompt_parity_reports_first_mismatch(self) -> None:
        tools = [{"type": "function", "function": {"name": "execute", "parameters": {"type": "object"}}}]
        runtime_request = {"messages": [{"role": "user", "content": "Runtime task."}], "tools": tools}
        training_row = {
            "id": "row-1",
            "tools": tools,
            "messages": [
                {"role": "user", "content": "Training task."},
                {"role": "assistant", "content": "Done."},
            ],
        }
        report = parity.audit(runtime_request, training_row)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["mismatches"][0]["path"], "$.messages[0].content")

    def test_tiny_slice_balances_short_rows_by_family(self) -> None:
        def row(task: str, tool_calls: int, padding: str = "") -> dict[str, object]:
            return {
                "id": task,
                "task_name": task,
                "tool_calls": tool_calls,
                "messages": [
                    {"role": "user", "content": f"Task {task}. {padding}"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": f"call_{task}",
                                "type": "function",
                                "function": {"name": "execute", "arguments": "{\"cmd\":\"echo ok\"}"},
                            }
                        ],
                    },
                ],
                "tools": acp_builder.DEFAULT_TOOLS[:1],
            }

        selected = tiny_slice.select_rows(
            [
                row("gmail-long", 5, "x" * 100),
                row("gcal-short", 2),
                row("gmail-short", 1),
                row("gdrive-short", 3),
            ],
            count=3,
            task_filter=set(),
            families=set(),
            max_tool_calls=3,
        )
        self.assertEqual([item["task_name"] for item in selected], ["gmail-short", "gcal-short", "gdrive-short"])
        repeated = tiny_slice.repeat_rows(selected, 2)
        self.assertEqual(len(repeated), 6)
        self.assertTrue(str(repeated[0]["id"]).endswith("::repeat-000"))


if __name__ == "__main__":
    unittest.main()
