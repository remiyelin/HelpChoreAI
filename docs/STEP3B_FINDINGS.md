# Step 3b Findings — Pixel/Texture vs Contour-Only (src/step3b_pixel_model.py)

Data: all 961 adjudication-queue cells, real 200x48 grayscale crops (coverage 961/961).
Author masks: `geometry.fill_contour` (P-03 fix). BASE area: per-frame contour shoelace
(P-04 fix, see below). LOPO logistic regression vs author `health`. Full log:
`docs/step3b_output.txt`; features: `data/tables/cell_pixel_features.csv`.

## New LOPO table (correct masks + contour area)

| Model | Held-out | kappa | Gwet AC1 | PABAK | bal. acc | n |
|---|---|---|---|---|---|---|
| BASE | P1 | 0.327 | 0.351 | 0.336 | 0.662 | 467 |
| BASE | P2 | 0.111 | 0.214 | 0.165 | 0.556 | 460 |
| BASE | P4 | 0.412 | 0.420 | 0.412 | 0.718 | 34 |
| PIXEL ONLY | P1 | 0.233 | 0.290 | 0.251 | 0.614 | 467 |
| PIXEL ONLY | P2 | 0.027 | 0.118 | 0.074 | 0.514 | 460 |
| PIXEL ONLY | P4 | 0.153 | 0.308 | 0.235 | 0.573 | 34 |
| BASE+PIXEL | P1 | 0.384 | 0.406 | 0.392 | 0.690 | 467 |
| BASE+PIXEL | P2 | 0.163 | 0.258 | 0.213 | 0.583 | 460 |
| BASE+PIXEL | P4 | 0.284 | 0.414 | 0.353 | 0.636 | 34 |

Mean kappa (bootstrap 95% CI, resampling cells within patient, B=1000, seed 42):
BASE **0.283** [0.176, 0.394]; PIXEL ONLY **0.138** [0.019, 0.252];
BASE+PIXEL **0.277** [0.169, 0.396]. Adding pixels to BASE changes mean kappa by
-0.006 with fully overlapping CIs: pixel information does not improve LOPO
agreement. Triage-only conclusion unchanged.

## Old vs new, and why the old table was invalid

| Model | Old mean kappa | New mean kappa |
|---|---|---|
| BASE | 0.362 | 0.283 |
| PIXEL ONLY | 0.243 | 0.138 |
| BASE+PIXEL (old: BASE+CONTOUR+PIXEL) | 0.331 | 0.277 |

The old numbers were invalid for two independent reasons. (1) Pixel features were
extracted inside masks from the buggy ray-casting rasterizer (P-03): it over-filled
contours severalfold, so "interior" intensity/radial/edge features sampled mostly
background and hull exterior. (2) BASE `area_mean` came from the pickle `Area` field,
which the authors' tracker corrupts: `Cell_tracking_new.py` appends `contourArea`
twice per frame when 2+ cells are present (lines 293-294) and then indexes the
doubled list with the single-cell sort order (line 304), misaligning area to cells.
Replacing it with per-frame contour shoelace area changed `area_mean` by >5% for
**321 of 2,674 cells (12.0%)** (P1 167/1374, P2 118/1075, P4 36/225; median change
0 — single-cell frames were unaffected; max relative change 0.87).

## Coverage note

2 of 24 visits have no M10 features: P2 2017-10-04 (12w) and P4 2017-11-07 (9w).
Reason for both: **missing pickle** — the Results .txt file is present exactly once
(not an ambiguity skip), but no `*Offline__M10_results.p` was extracted for those
visits, so `load_cells` never sees them. Their visit-level fractions still enter
Step 4 through `per_run.csv`; only per-cell features/classifier rows are absent.
