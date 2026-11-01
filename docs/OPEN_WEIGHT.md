# Open-weight mode

With `OPEN_WEIGHT_ONLY=1`, every Meta entry point in `src/meta_api.py` (chat, rater, SAM, video, voice) refuses before the network with status `BLOCKED_OPEN_ONLY`. The agent, the narrative and the auditor go to Muse Spark Open instead. Meta spend in this mode is exactly $0.00.

Wording: **open weights, hosted by a partner here; the same OpenAI-compatible endpoint can run on your own hardware.** A hosted service is not on-premise.

## Why it matters

Numbers come from code, not from the model. So a model can be replaced without touching a signed number. That is a controlled change: swap the model, compare the hashes, and only the words differ.

## Choosing a host

Any OpenAI-compatible endpoint works. Set these in `.env`:

```text
OPEN_BASE_URL=<endpoint>/v1
OPEN_API_KEY=<key>
OPEN_MODEL=<model name on that host>
OPEN_REASONING_EFFORT=low
```

| Host | Base URL | Model |
|---|---|---|
| Baseten (default) | `https://inference.baseten.co/v1` | `meta-models/muse-spark-open` |
| Modal Shared Endpoint | from the dashboard | `modal endpoint create --shared --model meta-models/Muse-Spark-Open-816B-A42B` |
| Fireworks | `https://api.fireworks.ai/inference/v1` | `accounts/fireworks/models/muse-spark-open` |
| Your own server | your vLLM or SGLang endpoint | as served |

Only hosts with a `logs/tamper_benchmark_<host>.json` file have been tested.

## Running it

```bash
uv run python tools/open_weight_parity.py runs --label modal
uv run python tools/open_weight_parity.py audit --label modal
uv run python tools/open_weight_parity.py tamper --label modal
uv run python tools/open_weight_parity.py table
```

Each step writes to the cache, so a repeat costs nothing. Each step stops at 80 new calls.

## Evidence

| What | Where |
|---|---|
| Reports signed in open-weight mode | `logs/open_weight_runs/agent_runs/<pair>/` |
| Trail of those runs | `logs/open_weight_runs/audit_trail.jsonl` |
| Audit of each committed report | `logs/agent_runs/<pair>/open_weight_audit.json` |
| Hash comparison, 21 pairs | `data/tables/open_weight_parity.csv` |
| Tamper benchmark per host | `logs/tamper_benchmark_<host>.json` |

`tests/test_open_weight_evidence.py` checks that every audit file carries the hash of the report beside it, and that every open-weight report verifies and has the same payload hash as the cloud run.

## What happened on the first run

16 of 21 pairs finished on Baseten, all with identical payload hashes. Five pairs with no decision ended `NEEDS_HUMAN`. There were three causes, all in our loop and not in the numbers:

1. A rule read "skip rate exceeds the threshold" as a claim of change.
2. The agent answered only the first of several tool calls, and the budget of 8 calls ran out before signing.
3. The auditor counted the citation year, the licence version and the patient code as violations.

All three are fixed. The first audit files also described open-run text instead of the committed reports, so they were deleted and the audit was repeated.

Earlier benchmark on Baseten, before the auditor prompt fix: Spark Open stopped 12 of 12 paraphrased advice reports (local rules 0 of 12) and passed 10 of 12 clean reports (`logs/tamper_benchmark_open.json`).
