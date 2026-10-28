# Step 2 Findings — Measurand, Flow, Noise, Contours/SAM

Measurand (option a): primary = `health==1` fraction among `shape!=0`; secondary = deformed
fraction `shape in {1,2,3,5,7}` among `shape!=0`; QC = skip rate `shape==0` share.
Tables: `data/tables/per_run.csv` (437 runs), `data/tables/per_visit.csv` (24 visits).
Code: `src/step2_analysis.py` (project env: `uv run python src/step2_analysis.py`).

## Hand-check (independent implementations, 100% match)

Run P1 0w M10 (flow 0.016): Python and an independent Node recount both give
total=146, kept=136, health1=43 (0.3161764706), deformed=114 (0.8382352941).

## Flow-rate effects (run-level Spearman, dev pooled per patient)

- Deformed fraction rises strongly with flow in all patients (rho +0.74..+0.84, p<1e-10):
  median deformed goes ~0.28-0.42 (low flow tertile) to ~0.89-0.93 (high). This is hydrodynamic
  state, not biology — raw deformed comparisons across unmatched flows are invalid.
- Primary health fraction FALLS with flow (rho -0.50..-0.62, p<1e-6): median ~0.43-0.50 (low)
  to ~0.31-0.33 (high). Even the primary measurand needs flow standardization (Step 4), and
  flow is confounded with velocity, so adjustment must be pre-registered, not exploratory.
- Skip rate vs flow: weak/inconsistent (P1 rho +0.09 ns; P2 +0.16 p=0.03; P4 -0.08 ns).

## Run-to-run noise vs binomial counting noise (overdispersion phi = var_obs/var_binom)

- Deformed: phi ~8-60 in nearly every visit — run-to-run variance dwarfs counting noise,
  consistent with the flow sweep inside each visit (runs are ordered flow ramps, not replicates).
- Health: phi ~1.1-12 — real overdispersion beyond counting noise in most visits, so RCV must
  include a run-level variance component; binomial-only bands would be far too narrow.
- QC: 22/437 runs have n_kept<30 and 2 runs are entirely skipped (n_kept=0, NaN fractions,
  excluded from correlations). Minimum-count and all-skip rules are mandatory in Step 4.
- Visit skip-rate rises in later P1/P2 visits (means up to ~0.43) — a protocol/QC drift signal
  to carry as a covariate, not silently pooled away.

## Frames <-> contours (verified with restricted unpickler, numpy-only)

- `Offline/M10_results.p` (Python-2 pickle) loads ONLY via `RestrictedUnpickler`
  (numpy allowlist, `encoding='latin1'`); keys: Frames, pos_x, pos_y, Contours, Area, x_ax, y_ax, circularity.
- For P1 0w M10: 146 tracked cells == 146 Results rows; sum(len(Frames)) == sum(len(Contours)) == 15,953.
  Per-cell contour lists align 1:1 with per-cell frame lists.
- The Online `*_contours.txt` has 15,116 blocks for the same run (837 fewer than the pickle) and
  frame numbering starts at 1949 in the sampled block — the .txt stream is not the authoritative
  per-cell source; use the pickle for SAM ground truth.

## SAM 3.1 audit status: BLOCKED (honest blocker)

No Meta Model API credentials exist in this environment (`META_MODEL_API_KEY` unset) and no
ffmpeg/opencv frame extraction is installed, so no SAM masks were generated and no IoU is claimed.
Harness: `src/sam_audit.py` (refuses to run without credentials; ground-truth side ready).
Unblock: provision Meta Model API key + claim hackathon credits, then
`uv run --with opencv-python python src/sam_audit.py --patient P1 --visit 0w --run M10 --cells 20`.

## Step 3/4 inputs locked by this step

1. Flow standardization is required for BOTH endpoints; deformed is secondary/QC only.
2. RCV components: binomial counting + run-level overdispersion (phi>1) + rater uncertainty (Step 3).
3. QC gates: n_kept>=30 per run (proposed), all-skip run exclusion, per-visit skip-rate reporting.
