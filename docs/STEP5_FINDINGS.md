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

## Checker hardening + tamper benchmark (2026-10-31)

Pinned key: the public key is committed at `data/checker/public_key.hex`; the private key stays
git-ignored. `verify_envelope()` verifies only against the pinned key and refuses any envelope
whose `public_key_hex` differs — a forged envelope re-signed with an attacker key (fake delta
+0.25, `exceeds_RCV`) is rejected. Tracked-file chain: `chain_hashes()` hashes only files from
`git ls-files` (the git-ignored `fetch_log_step1.json` is excluded), lists the hashed paths in
`chain.hashed_files` inside the signed payload, points at the v3 decision table
(`visit_pairs_decisions_v3.csv` / `per_visit_adjusted_v3.csv`), and the payload carries
`report_sha256` (SHA-256 of the rendered report text). The committed example
`data/checker/example_report_P1_0w_2w.*` verifies on a fresh clone. `meta_api.baseten_audit`
asks the Baseten open-weight model (`meta-models/muse-spark-open-1026`, falling back to the
served `meta-models/muse-spark-open`) for strict JSON
`{"verdict": "PASS"|"BLOCK", "reasons": [...]}` and fails closed: anything unparseable or not
explicitly `PASS` is `BLOCK`. The local narrative rule also rejects spelled-out numbers
(one–twenty, thirty, etc.) and percent words (`percent`, `percentage`).

12-report tamper benchmark (3 clean, 3 altered numbers, 3 paraphrased clinical advice,
3 patient-identifier or spelled-out number; P1 example payload; 12 new billed Baseten calls,
served model `meta-models/muse-spark-open`; the `-1026` attempts 404'd and were not billed):

| Auditor | Sensitivity (tampered blocked, n=9) | Specificity (clean passed, n=3) |
|---|---|---|
| Local rule auditor | 0.667 (6/9) | 1.000 (3/3) |
| Baseten open-weight auditor | 0.889 (8/9) | 1.000 (3/3) |

Per category: local blocked 3/3 altered numbers, 0/3 paraphrased advice, 3/3 identifier/spelled-out;
Baseten blocked 3/3 altered numbers, 3/3 paraphrased advice, 2/3 identifier/spelled-out
(it passed the synthetic `XX (0w)` identifier case). Local misses are paraphrases that avoid
the banned phrases; Baseten catches those but missed the synthetic identifier.
