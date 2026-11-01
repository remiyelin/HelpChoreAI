# Open-Weight Only Mode (P-25)

Set `OPEN_WEIGHT_ONLY=1` to run with **Meta API spend of exactly
$0.00**. In this mode every Meta entry point in `src/meta_api.py`
(chat, rater, SAM, video, voice) refuses **before the network** with
status `BLOCKED_OPEN_ONLY`; the agent and the narrative path route to
Baseten instead. This was **tested on Baseten only**.

Terminology, precisely: this is **open weights, hosted on Baseten
here; the same OpenAI-compatible endpoint can run on your own
hardware** by pointing the base URL at your own deployment (below).
Baseten is a hosted service, not on-premise — do not describe this
setup as on-premise.

## Pointing at your own endpoint

The Baseten calls are OpenAI-compatible chat completions. To use your
own deployment instead of Baseten:

1. Serve the model behind any OpenAI-compatible `/v1/chat/completions`
   endpoint (for example vLLM or SGLang serving the same weights).
2. Set `BASETEN_API_URL` to your endpoint's chat-completions URL and
   `BASETEN_API_KEY` to whatever token your server expects (or a dummy
   value if it ignores auth).
3. Set `OPEN_WEIGHT_ONLY=1` and run as usual. The served model id is
   discovered once per run with `GET /v1/models` and recorded in
   every result row; if your server serves a different model id, set
   it in the parity CSV from that discovery, not by assumption.

## Mechanism

`GET /v1/models` on the endpoint lists `meta-models/muse-spark-open`
as served. A probe completion confirmed that **the endpoint returns
native tool calls** (`message.tool_calls`), so the agent uses Baseten
function calling directly — no JSON-action loop was needed. The
Baseten agent chat validates each message in code (content or
tool_calls required), retries once on an invalid message, then
refuses. All calls go through `data/api_cache/`; repeat runs are
cache hits.

## Parity result — reported as observed (BUG)

The number-computing code path is unchanged, so payload hashes should
match exactly. They do **where the open run completes**: 16 of 16
completed pairs have `payload_sha256` identical to the cloud run.

But the expected **21 of 21 did not happen**: 5 indeterminate pairs
(P1 10w→14w, P1 14w→20w, P1 29w→53w, P2 18w→22w, P2 22w→27w) ended
`NEEDS_HUMAN` with no report. Diagnosis from the open trail: the
open-weight model spends its tool budget on repeated inspection
calls (`sample_cells`, `rater_summary` for both visits, repeatedly)
and never calls `render_and_sign` before the 8-tool-call budget or
the refusal ladder ends the run — for P1 10w→14w it used 9 calls
without rendering at all. This is an agent-loop/model-behaviour bug
in open-weight mode, **not** a numbers-path difference: no completed
pair disagrees on any payload value. Per the task, this is stopped
and reported rather than forced. Parity table:
`data/tables/open_weight_parity.csv` (the 5 failed pairs have empty
open hashes and `NEEDS_HUMAN` status).

Spark Open audit of the 16 final reports (`baseten_audit`):
14 PASS, 2 BLOCK. Both BLOCKs cite the citation boilerplate numbers
(“CC BY 4.0”, “Reichel et al. 2022”) as numbers not in the payload —
a known-style false positive of the strict auditor prompt — and one
also flags a genuine narrative overreach (“stable disease …”) written
by the open-weight model. Per-pair verdicts:
`logs/agent_runs/<pair>/open_weight_audit.json`.

## Tamper benchmark (12 old + 12 paraphrases)

Local rules = `checker.audit_report`; Spark Open = `baseten_audit`
verdict. Sensitivity is the share of tampered reports blocked;
specificity is the share of 12 clean reports passed.

| Set | Local rules | Spark Open |
|---|---|---|
| Old tampered 12 (sensitivity) | 0.500 (6/12) | 0.833 (10/12) |
| Paraphrased advice 12 (sensitivity) | 0.000 (0/12) | 1.000 (12/12) |
| Clean 12 (specificity) | 1.000 (12/12) | 0.833 (10/12) |

Local rules miss every paraphrased-advice report (their phrases
match no banned string); Spark Open catches all 12, at the cost of
blocking 2 clean reports (the citation-number false positive above).
Detail: `logs/tamper_benchmark_open.json`. Baseten calls in this
task (probes, agent turns, audits): approximately 191, under the 200
cap; Meta calls: 0.
