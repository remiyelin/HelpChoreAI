# Step 3b Findings — Pixel/Texture vs Contour-Only (src/step3b_pixel_model.py)

Data: all 961 adjudication-queue cells, real 200x40 grayscale crops (coverage 961/961,
`tools/verify_coverage.py` passes). Features per cell from the crop + author contour mask:
interior intensity (mean/std/p10/p90), dark-crescent (darkest-20% mean, crescent contrast),
radial profile (inner/mid/outer ring means, center-edge diff), edge gradient (boundary-band
gradient magnitude), texture (Laplacian variance, histogram entropy) — alongside the Step 3
base features (area/circularity/axis/n_frames) and contour roughness/solidity.
Protocol: leave-one-patient-out logistic regression vs author `health`, identical to
`src/step3_contour_check.py`. Full log: `docs/step3b_output.txt`; features:
`data/tables/cell_pixel_features.csv`.

## Result (LOPO Cohen kappa, mean over P1/P2/P4)

| Features | kappa per patient | mean kappa | mean balanced acc |
|---|---|---|---|
| BASE (area/circ/axis/frames) | 0.337 / 0.179 / 0.570 | 0.362 | 0.683 |
| BASE+CONTOUR (rough/solid) | 0.341 / 0.179 / 0.448 | 0.323 | 0.663 |
| PIXEL ONLY | 0.150 / 0.092 / 0.487 | 0.243 | 0.619 |
| BASE+CONTOUR+PIXEL | 0.349 / 0.196 / 0.448 | 0.331 | 0.667 |

## Interpretation

- Pixel/texture features carry real signal on their own (kappa 0.243, balanced accuracy
  0.619), comparable to the published contour-only baseline (kappa 0.243 on the full
  M10 cohort, `src/step3_contour_check.py`).
- Adding pixels to base+contour does **not** materially improve LOPO kappa
  (0.323 -> 0.331, +0.008), and the combined model stays below BASE alone on this
  queue cohort (0.362). The dark-crescent/radial information is largely redundant
  with area/circularity summaries at this crop resolution (200x40).
- Like-for-like caveat: the 0.243 contour baseline was measured on all 1,944 kept
  M10 cells; the queue cohort (961 low-confidence/disagreeing cells) is harder and
  selected, so cross-cohort kappa values are not directly interchangeable. The
  valid comparison is within-cohort (table above).
- Conclusion unchanged: the classifier is a triage/prioritization device for human
  adjudication, never ground truth. Human second-rater labels (kappa/Gwet AC1 in
  the overlay UI) remain the label-uncertainty source for RCV.
