# Step 4b + Step 5 Findings

## Step 4b (src/step4b_model.py, log docs/step4b_output.txt)
Patient-intercept Bernoulli GLM logit P(health=1) ~ flow + flow^2 + patient; ratio adjustment to
0.016 uL/s retaining patient intercept. Cluster bootstrap (cluster=run, within visit, B=400, seed=42)
+ Step-3 label variance -> RCV95. Treatment joined from authors' notebooks (fig2/fig4):
P1,P2,P3 dasatinib; P4,P5 lithium; first visit = day 0. Result unchanged vs Step 4:
21 pairs -> 4 exceeds_RCV, 9 within_RCV, 8 indeterminate_QC. The P1 29w->53w raw -0.2220 /
adjusted -0.2181 pair remains indeterminate_QC (skip gate) — the demo's blocking example.

## Step 3 contour check (src/step3_contour_check.py)
Roughness (perimeter/(2*sqrt(pi*area))) + solidity (area/hull) from raw Contours:
LOPO kappa mean 0.243 (base) -> 0.237 (base+contour); balanced accuracy 0.629 -> 0.627.
No improvement. Triage conclusion stands: classifier prioritizes human review, never ground truth.

## Step 5 Checker (src/checker.py, tests/test_checker.py, tests/test_stats.py)
Chain: fetch-manifest SHA-256 -> canonical table SHA-256s -> payload SHA-256 -> Ed25519 signature.
Templated report renders numbers only from payload; narrative slots reject digits.
Auditor (local rule implementation of the open-weight contract) blocks banned clinical-advice
phrases, missing disclaimer, altered/missing payload numbers, non-P-code identifiers.
Open-weight auditor (meta-models/muse-spark-open-1026 on Baseten) returns BLOCKED without
BASETEN_API_KEY — by design it never silently approves.
Demo: P1 0w->2w envelope verifies + audits clean (data/checker/example_report_P1_0w_2w.md).
Tests: `uv run pytest tests/ -q` -> 8 passed (untampered verifies + save/load roundtrip;
tampered number fails; tampered decision fails; digits-in-narrative rejected;
clinical-advice+missing-disclaimer blocked; open-weight blocked without credentials;
Step 4b table invariants).
Private key lives in data/checker/private_key.pem (local demo key; do not commit to public repo —
rotate/provision per deployment).
