# Gemma 4 E4B env0 SFT pipeline

This directory contains the reusable SFT pipeline for training
`google/gemma-4-E4B-it` on env0 task trajectories.

It is intentionally limited to pipeline code, configuration, task-list inputs,
and zero-spend tests. It does not include experiment logs, reports, run outputs,
checkpoints, adapters, raw job dumps, or result summaries.

## Scope

The pipeline supports:

- task discovery from this env0 checkout;
- zero-spend input and provider preflight;
- read-only provider capability probing for Fireworks and Prime Intellect;
- strict SFT row extraction from BenchFlow job directories;
- ACP trajectory conversion into OpenAI-style and LLaMA-Factory ShareGPT rows;
- prompt/tool parity checks between runtime requests and training rows;
- deterministic tiny-overfit slice construction;
- LLaMA-Factory QLoRA command generation.

The default data boundary is env0-only. Do not mix in TBLite, SkillsBench,
live-browsing, or other non-env0 training data.

## Default Config

```bash
pipelines/gemma4-e4b-env0-sft/configs/default.json
```

Primary inputs:

- `teacher_model`
- `student_model`
- `task_list`
- `gpu_provider`

The default `env0_dir` is `.` so commands should run from the repository root.

## Commands

Refresh task manifests from the current checkout:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py discover-tasks \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json
```

Run a zero-spend preflight:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py preflight \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json \
  --env-file /Users/bingran_you/Downloads/GitHub/bingran-you/.env \
  --out .local/gemma4-e4b-env0-sft/preflight.json
```

Run the read-only provider capability probe:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py probe-providers \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json \
  --env-file /Users/bingran_you/Downloads/GitHub/bingran-you/.env \
  --out .local/gemma4-e4b-env0-sft/provider-probe.json
```

Build strict SFT rows from one or more BenchFlow teacher job directories:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py build-sft-rows \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json \
  --job-dir .local/gemma4-e4b-env0-sft/jobs/teacher-collect \
  --out .local/gemma4-e4b-env0-sft/data/train.clean.jsonl \
  --manifest .local/gemma4-e4b-env0-sft/data/train.clean.manifest.json
```

Audit prompt and tool parity:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/audit_prompt_parity.py \
  --runtime-request .local/gemma4-e4b-env0-sft/audit/runtime_request.json \
  --training-row .local/gemma4-e4b-env0-sft/data/train.clean.jsonl \
  --training-index 0 \
  --report .local/gemma4-e4b-env0-sft/audit/prompt_parity.json
```

Build a deterministic tiny-overfit slice:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/select_tiny_overfit_slice.py \
  --input-openai .local/gemma4-e4b-env0-sft/data/train.clean.jsonl \
  --out-openai .local/gemma4-e4b-env0-sft/tiny-overfit/train.openai.jsonl \
  --out-llamafactory .local/gemma4-e4b-env0-sft/tiny-overfit/env0_tiny_overfit_sft.json \
  --dataset-info .local/gemma4-e4b-env0-sft/tiny-overfit/dataset_info.json \
  --count 5 \
  --max-tool-calls 8 \
  --repeat 64
```

Write the selected provider training command:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py write-train-command \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json \
  --env-file /Users/bingran_you/Downloads/GitHub/bingran-you/.env \
  --train-jsonl .local/gemma4-e4b-env0-sft/data/train.clean.jsonl \
  --out .local/gemma4-e4b-env0-sft/train_command.sh
```

Force the raw-GPU LLaMA-Factory QLoRA path:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py write-train-command \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json \
  --provider prime \
  --train-jsonl .local/gemma4-e4b-env0-sft/data/train.clean.jsonl \
  --out .local/gemma4-e4b-env0-sft/train_prime_qlora.sh
```

Run zero-spend tests:

```bash
python3 -m unittest pipelines/gemma4-e4b-env0-sft/tests/test_pipeline.py
```
