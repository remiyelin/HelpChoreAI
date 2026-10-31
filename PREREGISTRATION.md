# Pre-registration — Holdout Evaluation (P-11)

Frozen **before** any sealed holdout data (P3/P5) is touched. This task made
0 API calls and did not fetch, open, or list any P3/P5 data file. All
predictions below are derived strictly from the dev findings (P1/P2/P4)
cited inline. The Unseal Log at the bottom is reserved for P-12.

## 1. Frozen code

- Frozen commit (HEAD of this pre-registration step, pipeline as evaluated):
  `f6aa1e1c91326f0ac9fb7eb13056aa667b2f10e4`
  (`feat(agent): verifiable audit agent with in-tool checks and human escalation`)
- Pipeline entry points at that commit: `src/step4b_model.py` (v3 statistics),
  `src/checker.py` (pinned-key Checker on the v3 tables), `src/rater_spark.py`
  + `src/meta_api.py` (cloud rater), `src/rater_open.py` (open-weight rater),
  `src/sam_full_batch.py` (SAM shape features), `src/agent.py` /
  `src/agent_tools.py` (verifiable audit agent).
- This pre-registration is committed on top of the frozen commit; any later
  pipeline change requires a new pre-registration amendment, recorded below
  the Unseal Log, never a silent edit to the frozen sections.

## 2. Measurand and flow standardisation (frozen)

- Measurand: `health==1` fraction among `shape!=0`, per run, kept-cell weighted
  per visit.
- Reference flow rate: **0.016 µL/s**.
- Model: **unpenalised binomial GLM** (statsmodels) on run-level counts
  (successes = `n_health1`, trials = `n_kept`):
  `logit(p) = patient intercept + b * log(flow)`.
  The log-flow term is retained (dev: ΔAIC = 913 vs no-flow, slope
  b = −0.322). No penalisation, no probability-ratio adjustment.
- Standardisation: each run is shifted to the reference flow on the
  **log-odds** scale (`eta_ref − eta_run`); visit value is the kept-cell
  weighted mean of standardised runs.

## 3. Uncertainty (frozen)

- **Cluster bootstrap**: run-level clusters resampled **within visit**,
  kept-cell weighted, **B = 2000**, **seed 20261026**.
- Visit variance is the bootstrap variance of the standardised visit fraction.
  The label-variance term is excluded from the RCV (sensitivity column only).

## 4. QC and decision rule (frozen)

- QC gate: a visit is QC-blocked when its skip rate **> 0.25** (skip rate
  ≤ 0.25 passes); pairs touching a QC-blocked visit are `indeterminate_QC`.
- RCV95 for a pair = `t(0.975, df = runs_a + runs_b − 2) * sqrt(var_a + var_b)`
  (few-cluster t calibration with run-count degrees of freedom; dev
  simulation false-exceeds rate 0.064 at nominal 0.05, vs 0.322 for the
  naive binomial rule).
- Decision: `exceeds_RCV` if `|delta_adj| > RCV95`, else `within_RCV`;
  QC-blocked pairs are `indeterminate_QC` regardless of the delta.

## 5. Second-rater and auditor protocols (frozen)

- Cloud rater: `muse-spark-1.3`, the exact `RATER_PROMPT` and enforced
  `RATER_SCHEMA` of P-05, up to 3 upscaled (4x) track frames per cell,
  `cannot_tell` never mapped to a label.
- Open-weight rater: `meta-models/muse-spark-open` via Baseten, identical
  prompt/schema/images (P-09); `message.content` only, Python schema
  validation, one retry on invalid JSON, then null.
- Reports: Checker-signed (pinned key `data/checker/public_key.hex`),
  Baseten audit fail-closed to BLOCK, agent loop of P-10 with in-tool
  verification and `AWAITING_SIGNOFF` until researcher sign-off.
- SAM shape: SAM 3.1 raw box prompts, same-grid solidity (≤ 1 by
  construction), features as in `docs/SAM_SPICULES.md`.

## 6. Pre-registered predictions for the holdout (P3/P5)

Stated before unsealing, as explicit ranges. "Visit"/"pair" refer to the
holdout visits and visit pairs as defined by the frozen pipeline.

**(a) Flow slope.** Dev: health fraction falls with flow in every dev patient
(run-level Spearman rho −0.50…−0.62, p < 1e-6; GLM slope −0.322).
Prediction: **80–100%** of holdout visits exhibit a negative within-visit
flow slope, and the pooled holdout GLM slope is negative, in
**−0.60…−0.10**.

**(b) Variance reduction.** Dev: health overdispersion phi ~1.1–12 before
adjustment; post-flow phi 2.15–5.57 (reduced, not eliminated), and flow
adjustment roughly doubled bootstrap power at +0.10 (0.77 vs 0.51).
Prediction: flow adjustment reduces within-visit overdispersion/variance in
**60–90%** of holdout visits, while residual phi stays > 1 in the majority
of visits.

**(c) Decision changes.** Dev: naive binomial calls 14/21 pairs "exceed" vs
6/21 under the frozen v3 rule + QC; 8/21 pairs are QC-indeterminate.
Prediction: the frozen-rule decision differs from the naive binomial
decision for **25–50%** of holdout pairs, and **20–50%** of holdout pairs
are `indeterminate_QC` at the 0.25 skip-rate gate. Of decidable pairs,
**20–45%** are `exceeds_RCV` (dev: 6/13 decidable).

**(d) Second-rater agreement** (vs author, cannot_tell excluded; dev values
in brackets). Cloud `muse-spark-1.3` [AC1 0.392, PABAK 0.334,
cannot_tell 0.438]: predicted holdout AC1 **0.10–0.65**, PABAK **0.05–0.60**,
cannot_tell **0.30–0.55**. Open-weight `muse-spark-open` [AC1 0.464,
PABAK 0.448, cannot_tell 0.275]: predicted holdout AC1 **0.20–0.70**,
PABAK **0.20–0.65**, cannot_tell **0.15–0.40**. Head-to-head cloud vs
open-weight agreement is predicted at AC1 **0.55–0.90** on both-rated
cells (dev 0.772).

**(e) SAM 3.1 spicule concavity.** Dev (960 cells): SAM solidity
health=1 **0.940** vs health=0 **0.954** (difference −0.014); convexity
defects >1px 1.97 vs 1.37 (+0.60); BASE+SAM raised LOPO kappa over BASE
in every dev patient.
Prediction: on the holdout, mean SAM solidity for health=1 cells is lower
than for health=0 cells by **0.005–0.025**, mean convexity defects are
higher for health=1 by **0.3–0.9**, and BASE+SAM LOPO kappa is **not
worse** than BASE alone.

## Unseal Log

- **Unsealed:** 2026-10-31T12:37:09Z (single unsealing, P-12), at commit
  `b01455134a88cdeab348ae55120c4fde73297029` (tag `eval-v1`; frozen pipeline
  commit `f6aa1e1c91326f0ac9fb7eb13056aa667b2f10e4`). No changes to `src/` or
  `tools/` (`git diff eval-v1 -- src/ tools/` is empty).
- **Ingest:** only `Results/*.txt` label files for P3/P5 via HTTP Range from
  the Figshare collection ZIPs (no AVI archives); hashes of all 239
  downloaded files are in `data/fetch_manifest/fetch_log_holdout.json`.
  Paid API calls: $0.
- **Holdout size:** 239 runs, 13 visits, 11 visit pairs
  (P3: 167 runs, 9 visits, 8 pairs; P5: 72 runs, 4 visits, 3 pairs).
  Decisions in `data/tables/sealed_results.csv`; run/visit tables in
  `data/tables/per_run_holdout.csv` / `per_visit_holdout.csv`.
- **Frozen pipeline applied unchanged:** unpenalised binomial GLM retained
  log-flow (AIC 1623.2 vs 1999.9 patient-only); standardised to 0.016 µL/s;
  cluster bootstrap B=2000, seed 20261026; QC skip-rate gate 0.25;
  t-calibrated RCV95. Decisions: 8 `within_RCV`, 0 `exceeds_RCV`,
  3 `indeterminate_QC` (each indeterminate pair touches a visit with skip
  rate 0.297–0.407).

Prediction scorecard (ranges frozen in §6; reported as observed, nothing
re-fitted or re-worded to force a match):

- **(a) Flow slope — MET.** 13/13 visits (100%) show a negative within-visit
  flow slope (predicted 80–100%); pooled holdout GLM slope −0.322
  (predicted −0.60…−0.10).
- **(b) Variance reduction — NOT MET.** Flow adjustment reduced
  overdispersion in 13/13 visits (100%), above the predicted 60–90% range.
  Residual adjusted phi stayed > 1 in 7/13 visits (53.8%), consistent with
  the "majority" sub-expectation, but the headline share missed the range.
- **(c) Decision changes — NOT MET (mixed).** Frozen vs naive decisions
  differ for 5/11 pairs (45.5%; predicted 25–50% — met);
  `indeterminate_QC` 3/11 (27.3%; predicted 20–50% — met); but
  `exceeds_RCV` among decidable pairs is 0/8 (0%), below the predicted
  20–45% — not met. The three largest adjusted changes (+0.174, −0.154,
  −0.144) all sit in QC-blocked pairs, so the frozen rule returns no
  decidable "exceeds" on this holdout.
- **(d) Second-rater agreement — UNMEASURED.** Held uncalled to preserve
  API budget ($0 paid calls in this step); no holdout rater number is
  claimed. Dev reference only: cloud AC1 0.392, open-weight AC1 0.464.
- **(e) SAM spicule concavity — UNMEASURED.** Held uncalled for the same
  budget reason (no SAM run on holdout cells); no holdout SAM number is
  claimed. Dev reference only: solidity difference −0.014, defects +0.60.

## Post-unsealing reproducibility note (2026-10-31, P-22)

`src/step12_holdout_eval.py` was committed after unsealing and calls only
functions frozen at eval-v1 (`src/step4b_model.py`: `fit_glm`,
`standardise`, and the frozen `REF_FLOW`/`B`/`SEED`/`TREATMENT` constants),
unchanged. It recreates `data/tables/sealed_results.csv` from
`per_run_holdout.csv` in memory to 6 decimals (test:
`tests/test_holdout_eval.py`, skipped when the holdout data is absent);
the committed file itself is not regenerated.

## Scorecard update — predictions (d) and (e) measured (2026-11-01, P-23)

Measured under the frozen §6 ranges and the same code
(`src/population_eval.py` Part C; detail in `docs/POPULATION.md`).

- **(d) Second-rater agreement — NOT MET as a joint prediction.**
  Cloud `muse-spark-1.3` (80 cells, 40/40 by author label): AC1 0.518
  (frozen 0.10–0.65 — in range), PABAK 0.454 (0.05–0.60 — in range),
  cannot_tell 0.175 (0.30–0.55 — **below range**). Open-weight
  `muse-spark-open`: all 80 calls BLOCKED (Baseten HTTP 402), so the
  open-weight and head-to-head predictions are UNMEASURED, not met.
- **(e) SAM 3.1 spicule concavity — NOT MET.** On 180 holdout cells:
  mean solidity health=1 0.9429 vs health=0 0.9454 (difference −0.0025;
  frozen −0.005…−0.025 — direction right, magnitude below range);
  convexity defects >1px 1.982 vs 1.464 (+0.518; frozen 0.3–0.9 — in
  range); BASE+SAM LOPO kappa −0.052 vs BASE 0.033 — BASE+SAM is
  worse, so “not worse than BASE” fails.
