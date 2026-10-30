# Statistical Validation (v3)

## Method (what changed and why)

The v2 "GLM" was an L2-penalised sklearn logistic regression fitted on
cell-expanded rows with raw `flow + flow^2` features: penalisation shrinks the
coefficients, and the model we described in prose was not the model we ran.
v3 (`src/step4b_model.py`) fits an **unpenalised binomial GLM** (statsmodels)
on run-level counts (successes = `n_health1`, trials = `n_kept`):
`logit(p) = patient intercept + b*log(flow)`. The log-flow term is kept only
because it improves AIC by far more than 2 (3745.4 vs 4658.4, ΔAIC = 913);
the fitted slope is **b = -0.322** (higher flow → lower healthy fraction).
Each run is standardised to the reference flow (0.016 µL/s) by shifting its
observed **log-odds** by `eta_ref - eta_run` — never by a probability ratio.
Visit uncertainty is the cluster bootstrap of runs within visit
(kept-cell weighted, B=2000, seed 20261026). The RCV multiplier is
`t(0.975, df = runs_a + runs_b - 2)` instead of 1.96 (calibration, below).
The 0.391 label-variance term (Step 3 classifier-vs-author disagreement) is
**removed from the RCV and from the UI planner**: it is not measurement noise
of a visit fraction. It survives only as the `RCV95_sensitivity` column.

## Simulation validation (`src/simulate_rcv.py`, no API calls)

Null: every visit (>= 8 runs; all 24 qualify) split randomly in half 1,000
times (24,000 splits, bootstrap B=200 inside each evaluation). Power: the
same splits with +0.05 / +0.10 added to one half by resampling cell labels.

### Null false-"exceeds" rates (nominal 0.05)

| Rule | False-exceed rate |
|---|---|
| Naive binomial interval (pooled cells) | 0.322 |
| Run bootstrap, no flow adjustment | 0.062 |
| **Run bootstrap + flow adjustment (final v3 rule)** | **0.064** |

Reported as it is: with the normal 1.96 multiplier the final rule
false-exceeded at **0.084** — anti-conservative, because a visit half has only
4–11 runs and the bootstrap variance is itself noisy. The t multiplier with
run-count degrees of freedom is the standard few-cluster correction and
brings the rate to 0.064, close to nominal. The naive binomial interval is
unusable on this data (0.322): cells within a run are not independent, which
is the entire point of the cluster bootstrap.

### Power (detection rate over the same splits)

| Added change | Naive | Bootstrap raw | Bootstrap + flow (final) |
|---|---|---|---|
| +0.05 | 0.552 | 0.193 | 0.306 |
| +0.10 | 0.845 | 0.512 | 0.772 |

The naive rule's "power" is meaningless at a 0.322 false rate. Flow
adjustment roughly doubles power over the raw bootstrap at +0.10 (0.77 vs
0.51) — flow confounding was masking real changes. Even the final rule
detects a +0.05 fraction change only ~31% of the time at current run counts;
that, not the interval formula, is the binding constraint, and it is what the
run-count planner is for.

### QC sensitivity (21 pairs, decision counts)

| Skip-rate threshold | exceeds | within | indeterminate_QC |
|---|---|---|---|
| 0.20 | 6 | 7 | 8 |
| 0.25 (deployed) | 6 | 7 | 8 |
| 0.30 | 8 | 7 | 6 |

No pair changes decision between 0.20 and 0.25; at 0.30 two further pairs
become decidable (and both exceed). The 0.25 threshold is not load-bearing
for the current decisions, but 8 of 21 pairs remain QC-indeterminate at it —
data quality, not statistics, is the largest source of "no answer".

## v2 -> v3 decision changes

2 of 21 pairs changed, both `within_RCV -> exceeds_RCV` (removing the label
term shrank the RCV more than the t multiplier grew it):

| Pair | delta_adj (v3) | RCV95 v2 | RCV95 v3 |
|---|---|---|---|
| P1 8w -> 10w | -0.0903 | 0.0671 | 0.0529 |
| P2 0w -> 2w | +0.0392 | 0.0409 | 0.0339 |

Totals: v2 = 4 exceeds / 9 within / 8 indeterminate; v3 = 6 / 7 / 8.
At a calibrated 95% level, about **1 of the 21 pairs is expected to "exceed"
by chance** even if nothing changed anywhere (21 x 0.05 = 1.05; at the
simulated 0.064, ~1.3). Individual borderline "exceeds" calls — especially
P2 0w -> 2w, whose |delta| barely clears its RCV — should be read with that
base rate in mind.

## Scope note

The frozen Checker chain (signed reports, `/api/report`) still consumes the
v2 tables; v3 is the statistical source of truth for analysis and planning.
Re-pointing the Checker to v3 is a separate, deliberate step (it changes
signed payloads), listed as open in docs/AUDIT_2026-10-29.md.
