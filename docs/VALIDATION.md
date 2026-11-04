# Validation status

**Validation-ready, not validated.** HelpChoreAI is a research tool. It gives no medical advice and is not meant for clinical decisions or regulatory submissions. The files below follow the structure of GAMP 5, 21 CFR Part 11 and ALCOA+ so that a lab that wants to use the tool in a regulated setting has a starting point. Each requirement maps to an automated test. Nobody independent has reviewed or approved them, and none of them is signed. A lab's own quality unit would own any real validation.

## What is here

| Part | Files | What it does |
|---|---|---|
| Requirements and design | `docs/csv/URS.md`, `docs/csv/FS.md` | User requirements, risk list (RISK-01…05), functional specification |
| Traceability | `docs/csv/TRACEABILITY_MATRIX.md` | Each requirement → specification → automated test |
| Qualification drafts | `docs/csv/IQ_PROTOCOL_REPORT.md`, `OQ_PROTOCOL_REPORT.md`, `PQ_PROTOCOL_REPORT.md` | Installation, operation and performance checks and their results |
| Data integrity | `docs/csv/ALCOA_PLUS_ASSESSMENT.md` | Self-assessment against the nine ALCOA+ principles |
| Tests | `tests/csv/`, `tests/test_csv_validation.py`, `tests/test_cross_domain.py` | The automated checks the documents point to |
| Second dataset | `CROSS_DOMAIN_EVIDENCE.md`, `data/cross_domain/` | Positive control on public RT-DC data (below) |
| Data catalogue | `data/csv/`, `data/csv/DATASETS_PROVENANCE.md` | 18 public tables with source, licence, size and SHA-256 |

## Positive control on a second dataset

HL60 cells (a human leukaemia cell line) from the public MetaDeformability study (Urbanska et al., *Nature Methods* 2020; CC0): 105 runs, 237,813 cells. In RT-DC, higher flow gives higher deformation, and in this study flow was set on purpose to 0.04, 0.08 and 0.12 µL/s in every dose. So the right answer is known before the test.

- HelpChoreAI's frozen flow rule found that dependence with the correct sign: Spearman ρ = +0.86, ΔAIC = 141.9 > 2, slope b > 0.
- The fitted flow term explains 73.5% of the run-to-run variance (82–97% within each dose). This is in-sample, and flow is the only thing varied within a dose, so a large share is expected. It shows the rule works on a known effect. It does not mean that flow should be removed from RT-DC data. The usual practice there is to measure at one flow rate or convert to Young's modulus.
- The open-weight auditor passed five method sentences from RT-DC papers and blocked one clinical sentence written for the test. This is a sanity check only. The harder test is in [CLAIM_CHECK.md](CLAIM_CHECK.md).

## How to check

```bash
uv sync
uv run pytest -q
```

Results on 4 November 2026:

| Where | Result |
|---|---|
| Developer machine, with the API key and the local reply cache | 197 passed |
| Clean copy without key, reply cache or private files (as a fresh clone) | 190 passed, 7 skipped |

The 7 skips are 5 live auditor tests, which need `BASETEN_API_KEY` or the reply cache, and 2 tests that need the raw recordings in `data/dev` and `data/frames`. Those can be downloaded again with `tools/figshare_ingest.py`.

## Corrections made on 4 November 2026

The first draft of these files, written with an AI coding agent on 2 November, overstated several things. On review:

- The OQ and PQ "observed results" for the variance check listed LatB doses that are not in the data, and variances that did not match the code. They were recomputed with `stats.calculate_variance_reduction`, and the reports say so.
- A binomial model fitted to median deformation was removed. A median is not a proportion of cells, and turning it into counts inflated ΔAIC (1,385).
- "Artifactual variance", "universally generalizable" and "certified fully compliant" were removed. So were "approved" status lines and signature claims.
- "Zero synthetic data" was replaced by a file-by-file provenance list. Three tables are computed by HelpChoreAI from the Reichel et al. 2022 recordings. Two small files are example files from dclab's software tests (GPL-2.0), not CC0 or MIT data.
- Live model tests now skip, instead of failing, on a clone without a key.

Test counts and dates inside the qualification drafts are as recorded on 2 November. Run `pytest` for the current suite.

## Limits

- Five patients and one human rater in the main dataset. The positive control uses a different cell type and instrument.
- One flow slope for all LatB doses; whether the slope changes with dose was not tested.
- The other OQ and PQ figures (beyond the variance and model-selection checks) were not re-derived one by one. The automated tests are the reference.
