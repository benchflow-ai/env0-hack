# Hud Hackathon

OpenThoughts Agent, but for mobile agents and small models.

This repo packages the hackathon build from the env0 workstream:

- a mobile-first agent demo;
- an end-to-end SFT pipeline that trains and converges;
- an env0 data recipe for mobile agent use cases;
- a lite benchmark built from verified synthetic env tasks.

Reference workspace: [benchflow-ai/env-0-experiment](https://github.com/benchflow-ai/env-0-experiment/tree/main)

## What We Are Shipping

1. **End-to-end training recipe**
   The pipeline turns env0 trajectories into filtered SFT rows, validates the
   tool-use contract, exports LLaMA-Factory data, trains a Gemma E4B-it adapter,
   and evaluates on a fixed lite benchmark slice.

2. **Target model**
   The hackathon target is the latest mobile-class Gemma E4B-it model track.
   The public story is a small model that can plausibly run on-device or near
   device, then gets better at mobile agent workflows through env0 training.

3. **Mobile agent data recipe**
   env0 supplies the controlled environments and task generators for general
   mobile assistant work:

   - search email and calendar for restaurant, flight, event, and meeting
     information;
   - send emails, manage calendar invitations, write notes, research, and prep
     for meetings;
   - use Drive and Docs to retrieve personal records, summarize documents, and
     update artifacts;
   - model productivity and lifestyle flows, including food logs, daily
     planning, reminders, and lightweight personal analytics;
   - start with Google Workspace support: Gmail, Calendar, Docs, and Drive.

4. **Lite benchmark**
   `tasks-lite/` contains 2,004 synthetic env0 tasks across auth, Gmail,
   Calendar, Docs, Drive, and multi-app workflows. The benchmark recipe is:

   - generate synthetic tasks with a verified oracle;
   - keep tasks that are solvable by the teacher trajectory pipeline;
   - use Gemma pass@5 / trace quality as a selection gate;
   - train on filtered SFT traces;
   - evaluate Gemma baseline, Qwen3.5-4B, Qwen3.5-9B, larger reference models,
     and the fine-tuned Gemma model on fixed eval slices.

5. **Demo frontend**
   `apps/Env0Mobile/` is a SwiftUI mobile client over `Env0Kit`, covering Mail,
   Calendar, Docs, Drive, and Settings.

## Headline Results

The public result we are showing:

| Model | Completed rows | Stuck counted fail | Passes / Total | Pass rate |
| --- | ---: | ---: | ---: | ---: |
| Gemma E4B-it pre-SFT | 60 | 0 | 0 / 60 | 0% |
| Gemma E4B-it post-SFT | 60 | 0 | 4 / 60 | 7% |
| Qwen/Qwen3.5-4B | 60 | 0 | 18 / 60 | 30.00% |
| Qwen/Qwen3.5-9B | 58 | 2 | 28 / 60 | 46.67% |

The important claim is directional: env0 SFT moves the mobile-class Gemma model
from 0% to 7% on the fixed reported slice. Qwen3.5-4B and Qwen3.5-9B are
reference baselines for the same task family, with stuck rows counted as fail.

## Training Cost Snapshot

The SFT loops are cheap enough for hackathon iteration. Costs below use the
recorded wall-clock minutes and estimated H100 cost at `$3.387/h`.

| SFT run | Train wall-clock | Eval wall-clock | Estimated training cost |
| --- | ---: | ---: | ---: |
| Native-tool SFT | 25m | 38m | $1.41 |
| Tasks-lite native SFT | 49m | n/a | $2.79 |
| Action-prefix SFT | 94m | n/a | $5.32 |
| 4096 r32 SFT | 93m | n/a | $5.24 |
| Text-tool SFT | 48m | n/a | $2.71 |

Only the native-tool SFT run has eval wall-clock recorded in the chart. Missing
eval elapsed time was not recorded in the log.

## Training Pipeline

The reusable pipeline lives in `pipelines/gemma4-e4b-env0-sft/`.

Pipeline stages:

1. discover env0 task manifests;
2. collect teacher or model trajectories from env0 tasks;
3. filter rows by reward, safety, infra status, and tool-call presence;
4. validate OpenAI-style and ShareGPT tool-use rows;
5. audit prompt/tool parity against runtime requests;
6. export LLaMA-Factory datasets;
7. train Gemma E4B-it with QLoRA;
8. evaluate on fixed env0 lite slices;
9. use failures as the next SFT or RL data recipe.

Large artifacts are intentionally not committed. Trained adapter weights,
external eval logs, and raw trajectory dumps are produced by the pipeline and
should be published as separate release artifacts.

## Eval Dataset

`tasks-lite/` is the hackathon eval and data-generation corpus.

Current task counts:

| Family | Count |
| --- | ---: |
| auth | 300 |
| gcal | 299 |
| gdoc | 316 |
| gdrive | 384 |
| gmail | 333 |
| multi | 371 |
| **total** | **2,004** |

For the presentation, we report the fixed 60-row slice shown above and can draw
a 100-task slice across the same domains for broader demo evaluation.

## Repo Layout

```text
env0-hack/
├── apps/Env0Mobile/                 # SwiftUI mobile demo + Env0Kit
├── pipelines/gemma4-e4b-env0-sft/   # SFT data, train, and eval pipeline
├── tasks-lite/                      # 2,004 synthetic env0 tasks
├── tasks/                           # selected reference tasks
├── packages/environments/           # mock Gmail/GCal/GDoc/GDrive/Slack services
├── docker/                          # env0 base image tooling
├── scripts/                         # local service/dev scripts
└── docs/                            # env0 runtime documentation
```

## Quickstart

Run the pipeline tests:

```bash
python3 -m unittest pipelines/gemma4-e4b-env0-sft/tests/test_pipeline.py
```

Run the mobile client package tests:

```bash
cd apps/Env0Mobile
swift test
```

Refresh the task manifests from this checkout:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py discover-tasks \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json
```

Run a zero-spend training preflight:

```bash
python3 pipelines/gemma4-e4b-env0-sft/scripts/run_pipeline.py preflight \
  --config pipelines/gemma4-e4b-env0-sft/configs/default.json \
  --env-file /Users/bingran_you/Downloads/GitHub/bingran-you/.env \
  --out .local/gemma4-e4b-env0-sft/preflight.json
```

Start local env0 services for development:

```bash
scripts/dev.sh
```

## Why This Matters

Mobile agents need models that are small, private, cheap to run, and still able
to use tools reliably. env0 gives us controllable mobile-adjacent environments,
verified tasks, oracle traces, and repeatable evals. The thesis is simple:
train small mobile-class models on realistic env0 agent traces, then measure
whether they actually become better mobile assistants.
