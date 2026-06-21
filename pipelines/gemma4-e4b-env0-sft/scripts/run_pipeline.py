#!/usr/bin/env python3
"""Control-plane helpers for the Gemma 4 E4B env-0 SFT pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import statistics
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PIPELINE_DIR / "configs" / "default.json"
GOOGLE_TAGS = {"auth", "gmail", "gcal", "gdoc", "gdrive"}
NON_GOOGLE_SERVICE_TAGS = {"slack", "stripe", "discord"}
FIREWORKS_BASE_URL = "https://api.fireworks.ai"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def resolve(path: str | Path, base: Path = ROOT) -> Path:
    path = Path(path)
    return path if path.is_absolute() else base / path


def load_config(path: Path) -> dict[str, Any]:
    config = read_json(path)
    config["_config_path"] = str(path)
    return config


def parse_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            env[key] = value
    return env


def merged_env(path: Path | None) -> dict[str, str]:
    env = parse_env_file(path)
    env.update(os.environ)
    return env


def stable_digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def git_rev(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def task_keywords(task_dir: Path) -> list[str]:
    task_toml = task_dir / "task.toml"
    if not task_toml.exists():
        return []
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback not expected here.
        return []
    data = tomllib.loads(task_toml.read_text(encoding="utf-8"))
    keywords = data.get("task", {}).get("keywords") or data.get("metadata", {}).get("tags") or []
    return [str(item) for item in keywords]


def task_instruction(task_dir: Path) -> str:
    path = task_dir / "instruction.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def discover_task_rows(env0_dir: Path) -> list[dict[str, Any]]:
    tasks_dir = env0_dir / "tasks"
    if not tasks_dir.exists():
        raise SystemExit(f"Missing env-0 tasks directory: {tasks_dir}")
    rows: list[dict[str, Any]] = []
    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir() or task_dir.name.startswith("_"):
            continue
        if not (task_dir / "task.toml").exists():
            continue
        keywords = task_keywords(task_dir)
        instruction = task_instruction(task_dir)
        rows.append(
            {
                "task_name": task_dir.name,
                "family": task_dir.name.split("-", 1)[0],
                "keywords": keywords,
                "instruction_preview": instruction.replace("\n", " ")[:220],
            }
        )
    return rows


def google_workspace_core(row: dict[str, Any]) -> bool:
    keywords = set(row.get("keywords") or [])
    if not (keywords & GOOGLE_TAGS):
        return False
    if keywords & NON_GOOGLE_SERVICE_TAGS:
        return False
    return True


def read_task_list(path: Path) -> list[str]:
    payload = read_json(path)
    if isinstance(payload, list):
        tasks = payload
    else:
        tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise SystemExit(f"Task list must be a JSON list or object with tasks: {path}")
    out = []
    for item in tasks:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("task_name"):
            out.append(str(item["task_name"]))
        else:
            raise SystemExit(f"Unsupported task list item in {path}: {item!r}")
    return out


def select_provider(config: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    requested = str(config.get("gpu_provider", "auto")).lower()
    order = [str(item).lower() for item in config.get("provider_order", ["fireworks", "prime"])]
    candidates = order if requested == "auto" else [requested]
    availability = {
        "fireworks": bool(env.get("FIREWORKS_API_KEY")),
        "prime": bool(env.get("PRIMEINTELLECT_API_KEY") or env.get("PRIME_API_KEY")),
    }
    for provider in candidates:
        if availability.get(provider):
            mode = "managed_sft" if provider == "fireworks" else "pod_qlora"
            return {"provider": provider, "mode": mode, "available": availability}
    return {"provider": None, "mode": None, "available": availability}


def fireworks_request(env: dict[str, str], path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
    key = env.get("FIREWORKS_API_KEY")
    if not key:
        raise SystemExit("FIREWORKS_API_KEY is required for Fireworks provider probing.")
    if query:
        clean_query = {key: value for key, value in query.items() if value not in (None, "")}
        encoded = urllib.parse.urlencode(clean_query)
        if encoded:
            path = f"{path}?{encoded}"
    req = urllib.request.Request(
        FIREWORKS_BASE_URL + path,
        headers={"Accept": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Fireworks API GET {path} failed: HTTP {exc.code}\n{body}") from exc
    return json.loads(raw) if raw else {}


def fireworks_accounts(env: dict[str, str]) -> list[dict[str, Any]]:
    payload = fireworks_request(env, "/v1/accounts", {"pageSize": 100})
    return payload.get("accounts") or []


def fireworks_models(env: dict[str, str]) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    page_token = ""
    while True:
        payload = fireworks_request(env, "/v1/accounts/-/models", {"pageSize": 1000, "pageToken": page_token})
        models.extend(payload.get("models") or [])
        page_token = payload.get("nextPageToken") or ""
        if not page_token:
            return models


def normalize_model_key(value: str) -> str:
    value = value.lower().strip()
    value = value.removeprefix("accounts/fireworks/models/")
    value = value.removeprefix("google/")
    value = value.replace("_", "-").replace(" ", "-")
    if value.endswith("-it"):
        value = value[:-3]
    return value


def safe_fireworks_model(model: dict[str, Any]) -> dict[str, Any]:
    details = model.get("baseModelDetails") if isinstance(model.get("baseModelDetails"), dict) else {}
    return {
        "name": model.get("name"),
        "displayName": model.get("displayName"),
        "state": model.get("state"),
        "kind": model.get("kind"),
        "contextLength": model.get("contextLength"),
        "modelType": details.get("modelType"),
        "parameterCount": details.get("parameterCount"),
        "tunable": bool(details.get("tunable")),
    }


def find_fireworks_model(models: list[dict[str, Any]], student_model: str) -> dict[str, Any] | None:
    target = normalize_model_key(student_model)
    aliases = {target}
    if target == "gemma-4-e4b":
        aliases.add("gemma-4-e4b")
    exact_matches = []
    fuzzy_matches = []
    for model in models:
        name = str(model.get("name") or "")
        display = str(model.get("displayName") or "")
        normalized_name = normalize_model_key(name)
        normalized_display = normalize_model_key(display)
        haystack = f"{normalized_name} {normalized_display}"
        if normalized_name in aliases or normalized_display in aliases:
            exact_matches.append(model)
        elif all(part in haystack for part in target.split("-") if part):
            fuzzy_matches.append(model)
    preferred = exact_matches or fuzzy_matches
    if not preferred:
        return None
    preferred.sort(key=lambda item: (str(item.get("name", "")).startswith("accounts/fireworks/models/") is False, str(item.get("name", ""))))
    return preferred[0]


def probe_fireworks(env: dict[str, str], student_model: str) -> dict[str, Any]:
    accounts = fireworks_accounts(env)
    models = fireworks_models(env)
    matched = find_fireworks_model(models, student_model)
    account_names = [str(account.get("name")) for account in accounts if account.get("name")]
    result: dict[str, Any] = {
        "available": True,
        "account_names": account_names,
        "model_count": len(models),
        "matched_student_model": safe_fireworks_model(matched) if matched else None,
        "managed_sft_supported": bool(matched and safe_fireworks_model(matched)["tunable"]),
    }
    if not result["managed_sft_supported"]:
        result["reason"] = "student model is absent from Fireworks or baseModelDetails.tunable=false"
    return result


def recommend_provider(config: dict[str, Any], env: dict[str, str], fireworks: dict[str, Any] | None = None) -> dict[str, Any]:
    requested = str(config.get("gpu_provider", "auto")).lower()
    base = select_provider(config, env)
    if requested == "fireworks":
        return base
    if requested == "prime":
        return base
    if fireworks and fireworks.get("available") and not fireworks.get("managed_sft_supported"):
        if env.get("PRIMEINTELLECT_API_KEY") or env.get("PRIME_API_KEY"):
            return {
                "provider": "prime",
                "mode": "pod_qlora",
                "available": base["available"],
                "reason": "Fireworks key is present, but the configured student is not tunable there.",
            }
    return base


def score_from_result(result: dict[str, Any]) -> float | None:
    score = result.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    rewards = result.get("rewards")
    if isinstance(rewards, dict):
        reward = rewards.get("reward", rewards.get("score"))
        if isinstance(reward, (int, float)):
            return float(reward)
    return None


def safety_violation(result: dict[str, Any]) -> bool:
    rewards = result.get("rewards") if isinstance(result.get("rewards"), dict) else {}
    details = rewards.get("details") if isinstance(rewards.get("details"), dict) else {}
    violations = details.get("safety_violations")
    if isinstance(violations, list) and violations:
        return True
    gate = details.get("safety_gate")
    return isinstance(gate, str) and "fail" in gate.lower()


def result_error(result: dict[str, Any]) -> Any:
    return result.get("error") or result.get("exception") or result.get("failure_mode")


def message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    out = dict(message)
    if "content" in out:
        out["content"] = message_content_to_text(out.get("content"))
    return out


def iter_rollout_dirs(job_dir: Path) -> list[Path]:
    if not job_dir.exists():
        raise SystemExit(f"Job dir does not exist: {job_dir}")
    if (job_dir / "result.json").exists():
        return [job_dir]
    candidates = sorted(path for path in job_dir.rglob("result.json") if path.parent.is_dir())
    return [path.parent for path in candidates]


def extract_llm_rows(rollout: Path, result: dict[str, Any], *, label_last_assistant_only: bool) -> list[dict[str, Any]]:
    trace_path = rollout / "trajectory" / "llm_trajectory.jsonl"
    if not trace_path.exists():
        return []
    task_name = str(result.get("task_name") or rollout.name.split("__", 1)[0])
    score = score_from_result(result)
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        item = json.loads(line)
        request_body = (item.get("request") or {}).get("body") or {}
        tools = request_body.get("tools") or []
        if not tools:
            continue
        response = item.get("response") or {}
        if response.get("status_code") != 200:
            continue
        body = response.get("body") or {}
        choices = body.get("choices") or []
        if not choices:
            continue
        message = choices[0].get("message") or {}
        if not isinstance(message, dict):
            continue
        if not message.get("tool_calls"):
            continue
        messages = [
            normalize_message(msg)
            for msg in request_body.get("messages", [])
            if isinstance(msg, dict)
        ]
        messages.append(normalize_message(message))
        rows.append(
            {
                "id": f"{rollout.name}::llm-{idx}",
                "task_name": task_name,
                "score": score,
                "passed": bool(score is not None and score >= 0.8),
                "source_trial_dir": str(rollout),
                "source_format": "llm_trajectory",
                "label_last_assistant_only": label_last_assistant_only,
                "messages": messages,
                "tools": tools,
            }
        )
    return rows


def build_rows_from_jobs(config: dict[str, Any], job_dirs: list[Path], task_list: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data_cfg = config.get("data", {})
    min_score = float(data_cfg.get("min_score", 1.0))
    reject_safety = bool(data_cfg.get("reject_safety_violations", True))
    reject_errors = bool(data_cfg.get("reject_errors", True))
    label_last = bool(data_cfg.get("label_last_assistant_only", True))

    rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_rollouts = 0
    valid_scores: list[float] = []
    for job_dir in job_dirs:
        for rollout in iter_rollout_dirs(job_dir):
            seen_rollouts += 1
            result = read_json(rollout / "result.json")
            task = str(result.get("task_name") or rollout.name.split("__", 1)[0])
            score = score_from_result(result)
            if isinstance(score, (int, float)):
                valid_scores.append(float(score))
            reason = ""
            if task not in task_list:
                reason = "task_not_in_configured_list"
            elif score is None:
                reason = "missing_score"
            elif score < min_score:
                reason = f"score_below_{min_score:g}"
            elif reject_safety and safety_violation(result):
                reason = "safety_violation"
            elif reject_errors and result_error(result):
                reason = "result_error"
            if reason:
                rejected.append({"rollout": str(rollout), "task_name": task, "score": score, "reason": reason})
                continue
            extracted = extract_llm_rows(rollout, result, label_last_assistant_only=label_last)
            if not extracted:
                rejected.append({"rollout": str(rollout), "task_name": task, "score": score, "reason": "no_llm_tool_rows"})
                continue
            rows.extend(extracted)

    manifest = {
        "job_dirs": [str(path) for path in job_dirs],
        "seen_rollouts": seen_rollouts,
        "valid_scores": len(valid_scores),
        "mean_score": statistics.fmean(valid_scores) if valid_scores else None,
        "selected_rows": len(rows),
        "rejected_rollouts": len(rejected),
        "rejected": rejected[:1000],
        "row_digest": stable_digest(rows),
    }
    return rows, manifest


def cmd_discover_tasks(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    env0_dir = resolve(config.get("env0_dir", "."))
    rows = discover_task_rows(env0_dir)
    all_payload = {
        "name": "current_all",
        "env0_commit": git_rev(env0_dir),
        "count": len(rows),
        "tasks": rows,
    }
    google_rows = [row for row in rows if google_workspace_core(row)]
    google_payload = {
        "name": "google_workspace_core",
        "description": "Google Workspace core tasks from the current env0 checkout; excludes Slack/Stripe/Discord tagged tasks.",
        "env0_commit": git_rev(env0_dir),
        "count": len(google_rows),
        "tasks": google_rows,
    }
    out_all = resolve(args.all_out or PIPELINE_DIR / "task_lists" / "current_all.json")
    out_google = resolve(args.google_out or PIPELINE_DIR / "task_lists" / "google_workspace_core.json")
    write_json(out_all, all_payload)
    write_json(out_google, google_payload)
    print(json.dumps({"all": str(out_all), "all_count": len(rows), "google": str(out_google), "google_count": len(google_rows)}, indent=2, sort_keys=True))


def cmd_preflight(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    env = merged_env(args.env_file)
    env0_dir = resolve(config.get("env0_dir", "."))
    task_list_path = resolve(config["task_list"])
    tasks = read_task_list(task_list_path)
    missing = [task for task in tasks if not (env0_dir / "tasks" / task / "task.toml").exists()]
    fireworks_probe = probe_fireworks(env, str(config["student_model"])) if args.probe_providers and env.get("FIREWORKS_API_KEY") else None
    provider = recommend_provider(config, env, fireworks_probe)
    present_keys = sorted(
        key
        for key in (
            "FIREWORKS_API_KEY",
            "PRIMEINTELLECT_API_KEY",
            "PRIME_API_KEY",
            "DAYTONA_API_KEY",
            "HF_TOKEN",
            "HUGGING_FACE_TOKEN",
        )
        if env.get(key)
    )
    ok = env0_dir.exists() and not missing and provider["provider"] is not None
    payload = {
        "ok": ok,
        "config": str(args.config),
        "env0_dir": str(env0_dir),
        "env0_commit": git_rev(env0_dir),
        "parent_commit": git_rev(ROOT),
        "teacher_model": config.get("teacher_model"),
        "teacher_reasoning_effort": config.get("teacher_reasoning_effort"),
        "student_model": config.get("student_model"),
        "task_list": str(task_list_path),
        "task_count": len(tasks),
        "missing_tasks": missing,
        "selected_provider": provider,
        "fireworks_probe": fireworks_probe,
        "present_secret_names": present_keys,
        "spendful": False,
    }
    if args.out:
        write_json(resolve(args.out), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not ok:
        raise SystemExit(2)


def cmd_probe_providers(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    env = merged_env(args.env_file)
    fireworks = probe_fireworks(env, str(config["student_model"])) if env.get("FIREWORKS_API_KEY") else {"available": False}
    provider = recommend_provider(config, env, fireworks if fireworks.get("available") else None)
    payload = {
        "config": str(args.config),
        "student_model": config.get("student_model"),
        "gpu_provider": config.get("gpu_provider", "auto"),
        "provider_order": config.get("provider_order", []),
        "fireworks": fireworks,
        "prime": {
            "available": bool(env.get("PRIMEINTELLECT_API_KEY") or env.get("PRIME_API_KEY")),
            "mode": "pod_qlora",
        },
        "recommended_provider": provider,
        "spendful": False,
    }
    if args.out:
        write_json(resolve(args.out), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_build_sft_rows(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    task_list = set(read_task_list(resolve(config["task_list"])))
    rows, manifest = build_rows_from_jobs(config, [resolve(path) for path in args.job_dir], task_list)
    out = resolve(args.out)
    manifest_path = resolve(args.manifest)
    manifest.update(
        {
            "config": str(args.config),
            "teacher_model": config.get("teacher_model"),
            "student_model": config.get("student_model"),
            "task_list": str(resolve(config["task_list"])),
            "task_count": len(task_list),
            "data_filter": config.get("data", {}),
        }
    )
    write_jsonl(out, rows)
    write_json(manifest_path, manifest)
    print(json.dumps({"out": str(out), "manifest": str(manifest_path), "rows": len(rows)}, indent=2, sort_keys=True))
    if not rows:
        raise SystemExit(3)


def cmd_write_train_command(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    if args.provider:
        config = dict(config)
        config["gpu_provider"] = args.provider
    env = merged_env(args.env_file)
    fireworks_probe = probe_fireworks(env, str(config["student_model"])) if args.probe_providers and env.get("FIREWORKS_API_KEY") else None
    provider = recommend_provider(config, env, fireworks_probe)
    train_cfg = config.get("training", {})
    train_jsonl = resolve(args.train_jsonl)
    output_dir = resolve(args.output_dir or train_cfg.get("output_dir") or Path(config.get("output_root", ".local/gemma4-e4b-env0-sft")) / "train" / "llamafactory-gemma4-e4b")
    metrics_out = resolve(args.metrics_out or Path(config.get("output_root", ".local/gemma4-e4b-env0-sft")) / "train" / "metrics.jsonl")
    data_root = output_dir.parent / "llamafactory-data"
    dataset_json = data_root / "env0_gemma4_sft.json"
    dataset_info = data_root / "dataset_info.json"
    recipe = output_dir.parent / "llamafactory-gemma4-e4b-sft.yaml"
    command_text = "#!/usr/bin/env bash\nset -euo pipefail\n\n"
    command_text += f"# selected_provider={provider['provider']} mode={provider['mode']}\n"
    if provider["provider"] == "fireworks":
        command_text += "# Fireworks is the default managed-SFT provider.\n"
        command_text += "# This script intentionally does not guess account-specific Fireworks model support.\n"
        command_text += "# Verify that the student base is supported by Fireworks managed SFT, then launch via the Fireworks API/CLI using this JSONL.\n"
        command_text += f"echo 'Fireworks managed SFT selected for {shlex.quote(str(config['student_model']))}.'\n"
        command_text += f"echo 'Training JSONL: {shlex.quote(str(train_jsonl))}'\n"
        command_text += "echo 'For raw-GPU QLoRA, regenerate this command with --provider prime.'\n"
        command_text += "exit 2\n"
    else:
        export_script = PIPELINE_DIR / "scripts" / "export_llamafactory_data.py"
        command_text += "# Run this on the selected Prime/raw GPU host after dependency bootstrap.\n"
        command_text += "python3 -m pip install -U 'llamafactory[torch]'\n"
        command_text += (
            "python3 "
            + shlex.quote(str(export_script))
            + " --input "
            + shlex.quote(str(train_jsonl))
            + " --out "
            + shlex.quote(str(dataset_json))
            + " --dataset-info "
            + shlex.quote(str(dataset_info))
            + " --dataset-name "
            + shlex.quote(str(train_cfg.get("dataset_name", "env0_gemma4_sft")))
            + (" --strip-thinking" if train_cfg.get("strip_thinking", True) else "")
            + "\n"
        )
        command_text += "cat > " + shlex.quote(str(recipe)) + " <<'YAML'\n"
        command_text += f"""### model
model_name_or_path: {config["student_model"]}
trust_remote_code: true

### method
stage: {train_cfg.get("stage", "sft")}
do_train: true
finetuning_type: lora
lora_rank: {train_cfg.get("lora_rank", 32)}
lora_alpha: 64
lora_dropout: 0.05
lora_target: all
quantization_bit: 4
freeze_vision_tower: true

### dataset
dataset: {train_cfg.get("dataset_name", "env0_gemma4_sft")}
dataset_dir: {data_root}
template: {train_cfg.get("template", "gemma")}
cutoff_len: {train_cfg.get("max_length", 8192)}
overwrite_cache: true
preprocessing_num_workers: 8

### output
output_dir: {output_dir}
logging_steps: 1
save_steps: 50
plot_loss: true
overwrite_output_dir: true
report_to: none

### train
per_device_train_batch_size: 1
gradient_accumulation_steps: 8
learning_rate: {train_cfg.get("learning_rate", 3e-5)}
max_steps: {train_cfg.get("max_steps", 300)}
lr_scheduler_type: cosine
warmup_ratio: 0.03
bf16: true
gradient_checkpointing: true

### eval
val_size: {train_cfg.get("eval_fraction", 0.1)}
per_device_eval_batch_size: 1
eval_strategy: steps
eval_steps: 20
YAML
"""
        command_text += "llamafactory-cli train " + shlex.quote(str(recipe)) + "\n"
    out = resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(command_text, encoding="utf-8")
    out.chmod(0o755)
    payload = {
        "out": str(out),
        "selected_provider": provider,
        "fireworks_probe": fireworks_probe,
        "train_jsonl": str(train_jsonl),
        "output_dir": str(output_dir),
        "metrics_out": str(metrics_out),
        "trainer_backend": "llamafactory",
        "llamafactory_dataset": str(dataset_json),
        "llamafactory_dataset_info": str(dataset_info),
        "llamafactory_recipe": str(recipe),
        "spendful_when_executed": True,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("discover-tasks", help="Generate task-list manifests from env-0/tasks.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--all-out")
    p.add_argument("--google-out")
    p.set_defaults(func=cmd_discover_tasks)

    p = sub.add_parser("preflight", help="Run zero-spend input/provider checks.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--env-file", type=Path)
    p.add_argument("--out")
    p.add_argument("--probe-providers", action="store_true", help="Call read-only provider APIs and recommend Fireworks vs Prime from current capability.")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("probe-providers", help="Run read-only provider capability probes.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--env-file", type=Path)
    p.add_argument("--out")
    p.set_defaults(func=cmd_probe_providers)

    p = sub.add_parser("build-sft-rows", help="Extract strict SFT rows from BenchFlow job dirs.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--job-dir", action="append", type=Path, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_build_sft_rows)

    p = sub.add_parser("write-train-command", help="Write the spendful QLoRA training command.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--env-file", type=Path)
    p.add_argument("--train-jsonl", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--provider", choices=["fireworks", "prime"], help="Override config gpu_provider for this command only.")
    p.add_argument("--probe-providers", action="store_true", help="Call read-only provider APIs before choosing the auto provider.")
    p.add_argument("--output-dir")
    p.add_argument("--metrics-out")
    p.set_defaults(func=cmd_write_train_command)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
