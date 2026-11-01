# P-10 Verifiable Audit Agent

Pattern (after Meta's legal-agent-workshop): verification runs inside deterministic
Python tools at fixed points so the model cannot skip it; ground truth (the v3 tables)
stays outside the agent's message history except as sealed tool outputs; rejection
feedback names the error but never the expected value; three rejections escalate to
human review (`NEEDS_HUMAN`); every passing report is `AWAITING_SIGNOFF` until a
researcher signs off in the UI (`/api/signoff`).

## Tools (`src/agent_tools.py`)

JSON in/out; every output carries its SHA-256 (`sha256` field over the canonical
output). Dev patients only (P1/P2/P4) — any other patient returns a sealed error.
No tool returns individual author labels or any P3/P5 data.

| Tool | Returns |
|---|---|
| `list_pairs(patient)` | v3 visit pairs and decisions for the patient |
| `pair_stats(patient, from_visit, to_visit)` | v3 decision row + per-visit run details |
| `qc_gate(patient, from_visit, to_visit)` | per-visit skip rates vs 0.25 threshold, PASS/BLOCK |
| `sample_cells(patient, visit, n)` | sampled M10 cell metrics (cell, area/circ/axis ratio, frames) |
| `rater_summary(patient, visit)` | aggregate spark-1.3 / open-weight rater counts and cannot_tell share |
| `render_and_sign(patient, from_visit, to_visit, narrative)` | see below |

`render_and_sign` is the fixed verification point: it collects the numbers that the
deterministic tools produce for that pair, extracts every number (digits or spelled
out) from the narrative, and rejects with `REJECTED_UNVERIFIED_NUMBER` if any
narrative number is not in a tool output of that run — or if any number appears in
the narrative at all, since numbers belong in the templated payload fields. Feedback
says what was wrong, never what the value should be. On a clean narrative it builds
the Checker payload, templates the report values directly from it, signs with the
pinned key, and re-verifies envelope + local audit before returning `PASS`.

## Agent loop (`src/agent.py`)

`muse-spark-1.3` function calling with `parallel_tool_calls: false`, at most 8 tool
calls per pair, one tool handled at a time. Paid model calls go through
`data/api_cache/`; a ledger (`logs/agent_ledger.json`) charges a conservative
estimated $0.02 per uncached model call and stops before passing the $3 cap.
Every model/tool/final step is appended to `logs/audit_trail.jsonl` with
input/output SHA-256 hashes. Three rejected narratives → `NEEDS_HUMAN`.
A passing report is saved to `logs/agent_runs/<run_id>/report.md` (+ `envelope.json`)
with final status `AWAITING_SIGNOFF` — it is not approved until researcher sign-off.

Offline behaviour is covered by `tests/test_agent.py` with a mock model: a planted
unverified number is rejected, three consecutive rejections give `NEEDS_HUMAN`, and
`python -m src.agent verify <run_id>` re-runs all checks on a finished run
(re-derives the render, re-verifies the envelope, checks trail hashes).

## Live run on the 21 dev pairs

All 21 pairs (P1: 10, P2: 9, P4: 2) were run live:

| Outcome | Count |
|---|---|
| Pairs completed | 21/21 |
| Final reports passed (`AWAITING_SIGNOFF`) | 21 |
| `NEEDS_HUMAN` | 0 |
| Tool calls (total, 3 per pair) | 63 |
| Narrative rejections | 0 |
| Model calls (uncached) / ledger | 63 / $1.26 of $3 cap |

Per pair the model called `pair_stats`, then `qc_gate`, then `render_and_sign`.

## One full trace (demo, run `P1_0w_2w`)

Audit-trail steps (hashes truncated to 12 chars; full entries in
`logs/audit_trail.jsonl`, verified with `uv run python -m src.agent verify P1_0w_2w`
→ `VERIFIED: P1_0w_2w … final=AWAITING_SIGNOFF`):

1. model → `pair_stats {"patient": "P1", "from_visit": "0w", "to_visit": "2w"}`
   (out# 3cd32f0f59a1)
2. tool `pair_stats` → `{"status": "OK", "decision": "exceeds_RCV", …}` (out# 02a47a5d903f)
3. model → `qc_gate` (out# 5f8645459426)
4. tool `qc_gate` → `{"status": "PASS", "threshold": 0.25, …}` (out# 585eab190dd4)
5. model → `render_and_sign` with narrative “Treatment initiation shows increase
   exceeding threshold with quality checks passing.” (out# 68bd5839bf32)
6. tool `render_and_sign` → `{"status": "PASS"}` — payload templated
   (delta +0.1541 vs RCV95 0.0416), signed and re-verified inside the tool
   (out# 8575de21cf78)
7. final → `AWAITING_SIGNOFF`, tool_calls=3, rejections=0 (out# 96fc773fd17e)

The signed report waits in `logs/agent_runs/P1_0w_2w/report.md` for researcher
sign-off in the UI; it is not treated as approved by the agent.

## P-24 goal-driven loop (checks inside tools, refusal ladder)

The user message now states the goal and the rules only; no prompt
names a tool order. Ordering lives inside the tools:
`render_and_sign` refuses (`REFUSED_MISSING_PREREQUISITES`, with a
message the model can act on) unless `pair_stats` and `qc_gate` ran
for that pair in this run. Planted faults — table hash mismatch,
narrative with a digit, paraphrased clinical advice
(`REFUSED_CLINICAL_ADVICE`), a QC-blocked pair written as a change
(`REFUSED_QC_NO_DECISION`, reason codes such as `HIGH_SKIP_RATE`
returned by `qc_gate`), and a wrong patient id — each end refused or
`NEEDS_HUMAN`, never signed (`tests/test_agent.py`, fake model, no
network). Every refusal is counted per run and logged as a `refusal`
trail entry; at 3 the run ends `NEEDS_HUMAN` ("refusal ladder"). On
an indeterminate pair the model may inspect with `sample_cells` and
`rater_summary`, then sign a no-decision report stating the reason.

Off vs on (same fake-model script, 21 pairs + planted faults;
reference checklist `ground_truth/audit_checklist.json`, synthesised
and read only by `tools/agent_eval.py` — no tool or prompt reaches
it). A wrong report is a signed report the checklist forbids:

| Mode | Wrong reports signed | Correct signed | Refusals | Escalations (NEEDS_HUMAN) | Tool calls |
|---|---|---|---|---|---|
| checks off | 9 | 13 | 9 | 3 | 79 |
| checks on | 0 | 13 | 36 | 12 | 97 |

With checks off, all 8 indeterminate pairs were signed as real
changes and the advice narrative was signed; with checks on, none
was. Detail: `logs/agent_eval_off_vs_on.json`.

Real run (ledger capped at $3 total): ledger before $1.26 / 63
calls; 14 of 21 pairs completed (all `AWAITING_SIGNOFF`) before the
ledger reached exactly $3.00 / 150 calls and stopped before the
next call (real-run spend $1.74; the remaining 7 pairs were not
run). Every indeterminate run inspected first — the saved full
trace `logs/agent_traces/P1_10w_14w.json` shows
`list_pairs → pair_stats → qc_gate → sample_cells → rater_summary →
sample_cells → rater_summary → render_and_sign`, not the old
three-step path. Across the 14 runs: 2 single refusals (each
recovered on retry), 0 escalations. Summary:
`logs/agent_eval_real_run.json`.

