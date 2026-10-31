# HelpChoreAI

**HelpChoreAI: A verifiable biophysical measurement & protocol-variance auditing workstation for microfluidic RBC recordings in chorea-acanthocytosis (VPS13A disease).**

## The problem

Deformability cytometry measures peripheral target engagement, but hydrodynamic
shear stretches cells (confounding health readouts) and laboratory protocol
drift (waiting time, high skip rates) causes false alarms in naive binomial
statistics. In our dev data the naive binomial rule false-alarms at 32.2%,
and raw health fractions fall with flow in every patient — a flow artefact
that looks exactly like a treatment effect if you do not adjust for it.

## What we built

A four-view workstation over the Reichel et al. (2022) microfluidic RBC
recordings (Figshare Collection 5793482, CC BY 4.0), running from
`uv run python src/server.py` at http://127.0.0.1:8765.

- **View 1 — Visit-pair setup.** Pick a patient and consecutive visits with
  dasatinib/lithium treatment timeline context; every pair carries its raw
  and flow-adjusted change, RCV95 band, and QC decision.
- **View 2 — Per-cell overlay review.** 961 real microfluidic frames
  extracted via HTTP Range, with author contours, SAM 3.1 spicule recovery
  (SAM masks find the concavities convex hulls erase: solidity 0.940 vs
  0.954 by author class), and a live human second-rater whose
  Cohen kappa / Gwet AC1 against the author updates as you label.
- **View 3 — RCV decision (default view).** Unpenalised log-flow binomial
  GLM standardisation to 0.016 µL/s with a run-cluster-bootstrap,
  t-calibrated RCV95 and a skip-rate QC gate (skip rate > 0.25 refuses to
  decide). Simulation proves this cuts the false-alarm rate from 32.2% to
  6.4%. A Naive vs Flow-adjusted toggle shows what the naive reading would
  have called.
- **View 4 — Verified report.** Numbers are templated only from an
  Ed25519-signed Checker payload (public key pinned and committed, private
  key git-ignored); a fail-closed open-weight compliance auditor on Baseten
  (`meta-models/muse-spark-open`) must explicitly PASS; and the verifiable
  tool-calling audit agent (P-10) runs verification inside its deterministic
  tools, escalates to `NEEDS_HUMAN` after three rejected narratives, and
  leaves every passing report `AWAITING_SIGNOFF` for researcher sign-off
  bound to the report hashes.

Two structured second-rater protocols run the same prompt and JSON schema:
cloud `muse-spark-1.3` (author AC1 0.392, cannot_tell 43.8%) and open-weight
`muse-spark-open` (AC1 0.464, cannot_tell 27.5%; head-to-head AC1 0.772).
A 12-report tamper benchmark: local auditor sensitivity 0.667, Baseten
open-weight auditor 0.889 (3/3 paraphrased clinical advice caught), both at
specificity 1.000.

## Holdout validation

The pipeline was frozen and its predictions pre-registered before any
holdout data was touched (`PREREGISTRATION.md`, `git tag eval-v1`), then
unsealed exactly once on P3 and P5 (239 runs, 13 visits, 11 pairs, $0 API
spend). Results: **100% of visits showed a negative flow slope** (pooled
slope −0.322, prediction MET), flow adjustment reduced overdispersion in
100% of visits (predicted 60–90%, NOT MET — reported as missed), and the
QC gate blocked all three dramatic late swings (+17.4%, −15.4%, −14.4%)
from being called treatment effects, returning 8 within_RCV / 0 exceeds /
3 indeterminate_QC. Rater and SAM holdout endpoints were deliberately held
uncalled to preserve budget. Nothing was re-fitted to force a match.

## Meta AI tooling

| Tool | Use in HelpChoreAI |
|---|---|
| SAM 3.1 | Spicule-recovery masks, video tracking audit, IoU vs author hulls |
| Muse Spark 1.3 | Structured second rater, report narratives, agent function calling |
| Muse Spark Open (Baseten) | Fail-closed compliance auditor, open-weight second rater |
| Muse Voice Transcribe | Hands-free overlay review notes |
| Muse | Development of this repository |

All paid calls go through the cache in `data/api_cache/` — reruns are free,
and every integration reports BLOCKED rather than fabricating a result when
a key or model is unavailable.

## Built during the hackathon vs pre-hackathon exploration

- **Built during the hackathon (26 Oct – 4 Nov 2026):** everything in this
  repository — ingest, flow/RCV statistics, Checker, raters, SAM audits,
  the four-view UI, the audit agent, pre-registration and holdout
  evaluation (first commit 28 Oct 2026; see `docs/` and git history).
- **Pre-hackathon exploration (upstream, not ours):** the Reichel et al.
  (2022) dataset, tracker and analysis notebooks on Figshare, which we
  ingest and audit. No HelpChoreAI code predates the hackathon.

## Limitations

Research prototype on one dataset (five patients; three dev, two holdout).
The classifier and both raters are triage devices, never ground truth;
statistical power for a +0.05 fraction change is only ~0.31 at current run
counts, and 3 of 11 holdout pairs were QC-indeterminate. SAM/rater holdout
endpoints are unmeasured. Model-cost figures in run ledgers are stated
estimates where the API does not expose billing.

## Research use only

Research use only. RBC morphology is a peripheral target-engagement marker,
not a measure of central nervous system progression. Every result must be
reviewed by a qualified researcher using the per-cell visual overlay.
Nothing here is medical advice.

## Licence and attribution

Code: MIT (see `LICENSE`). Data: Reichel et al. 2022, Figshare Collection
5793482, CC BY 4.0 (see `ATTRIBUTION.md`). Copy `.env.example` to `.env`
for live model keys; `.env`, private keys and the initials map are
git-ignored and must never be committed.
