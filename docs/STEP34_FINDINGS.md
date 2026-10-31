# Step 3+4 Findings — Classifier, Adjudication, Flow Standardization, RCV

Code: `src/step34_model.py`. Outputs: `data/tables/cell_features_M10.csv` (1,944 kept cells),
`data/tables/adjudication_queue.csv` (961 rows), `data/tables/per_visit_adjusted.csv`,
`data/tables/visit_pairs_decisions.csv` (21 consecutive visit pairs). Full log: `docs/step34_output.txt`.

## Step 3 — contour classifier (honest weak result)

Features per cell from Offline pickles (RestrictedUnpickler only): Area mean/std, circularity
mean/std, axis ratio, n_frames. Logistic regression, leave-one-patient-out (LOPO) vs author `health`:
balanced accuracy 0.58 (P2) / 0.60 (P1) / 0.71 (P4, n=87); Cohen's kappa vs author 0.15-0.37;
overall LOPO disagreement 39.1%. Conclusion: pickle summary features do NOT reproduce the human
health label — the classifier is a triage/prioritization device only. The adjudication queue
(bottom-20% confidence + all disagreements, 961/1,944 cells) is therefore a core component,
not an accessory, and the 39% disagreement rate feeds RCV as the label-uncertainty component
until double-rater kappa/AC1 from Step 3b replaces it. P4 contributes only 87 usable M10 cells
(one visit pickle set) — patient-level generalization claims are prohibited.

## Step 4 — flow standardization + RCV/MDC95 (preliminary, method frozen for Step 4b review)

Method: pooled Bernoulli logistic model logit P(health=1) ~ flow + flow^2 (coef flow -14.0),
each run's fraction ratio-adjusted to reference flow 0.016 uL/s, visit value = kept-cell-weighted
mean. RCV95 per pair = 1.96*sqrt(var_a+var_b), var = phi_patient * p(1-p)/N_kept + label_var,
phi (post-flow residual overdispersion): P1 2.15, P2 5.57, P4 2.54; label_var from Step 3
disagreement. QC indeterminate if either visit mean skip rate >0.25 or N_kept<500.

Result over 21 consecutive visit pairs:
- Naive binomial-only (raw): 14/21 pairs "exceed".
- After flow standardization + RCV + QC: **4 exceeds, 9 within, 8 indeterminate_QC**.
- Surviving exceeds: P1 0w->2w (+0.153), P1 2w->4w (-0.088), P1 4w->6w (+0.112), P2 12w->18w (-0.127).
- The 8 indeterminate pairs cluster in late visits where skip rate exceeds 0.25 — the audit
  correctly refuses to decide on degraded runs instead of calling large deltas (e.g. P1 29w->53w
  raw -0.222) real.

## Limitations to fix in Step 4b/5 (do not over-claim)

1. Flow model is pooled without patient intercepts and uses a ratio adjustment — replace with
   patient-intercept binomial GLM (or mixed model per authors' lme4 approach) and bootstrap RCV.
2. Label uncertainty uses classifier-vs-author disagreement as a proxy until human double-rating
   (kappa/Gwet AC1) is measured in the adjudication UI.
3. Treatment context (dasatinib/lithium periods from the paper) is not yet joined to visit pairs;
   no pair may be described as natural progression.
4. SAM 3.1 audit still blocked: sandbox cannot read the local Muse Code
   auth file (access denied), and Muse Code login is not a Meta Model API key. Live check runs once
   `META_MODEL_API_KEY` is exported (harness: `src/sam_audit.py`).
