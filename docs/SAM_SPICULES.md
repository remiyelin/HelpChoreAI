# SAM 3.1 Spicule Recovery (P-06)

Question: the lab's author contours are convex hulls (`cv2.convexHull`,
`take_ConvHull = True` in the authors' tracker), so hull solidity is ~1 by
construction and spicules are erased. SAM 3.1 masks are not convexity-constrained.
Do SAM mask shape features recover a health signal the hull features miss?

## Method

- Pilot (20 queue cells, 10 author health=1 / 10 health=0): box prompt with
  half-open geometry (`max+1`, P-03 fix) and `metadata.include_confidence="true"`,
  on the raw 200x40/48 crop and on a 4x nearest-neighbour upscale; concept prompts
  on 4x crops of 6 cells; 10 repeats in the better setting. Go decision and its
  conditions: `DECISIONS.md` (repo root and `docs/`). Contact sheet:
  `docs/media/sam_pilot_sheet.png` (tracked; panels in `pilot_sam.csv` row order) —
  all 20 masks sit on their target cell and follow concave crescent shapes.
- Full batch (`src/sam_full_batch.py`): raw-setting box prompt on all 961 queue
  cells, reusing the 20 pilot raw calls from cache. Per mask, in original-pixel
  units: area, perimeter, solidity, convexity defects deeper than 1 px, boundary
  roughness, SAM confidence, IoU vs the author hull. Solidity's hull area is the
  filled convex hull **on the same 1x pixel grid** as the mask (Condition 1), so
  solidity <= 1 by construction — verified: max 0.990 over 960 masks.
- LOPO logistic regression vs author `health` on the 960 SAM-OK cells (same cells
  for every model): BASE (hull features: contour-shoelace area, circularity, axis
  ratio, n frames) vs SAM shape only vs BASE+SAM. Bootstrap 95% CI for mean kappa
  resamples cells within patient (B=1000, seed 42).

## Pilot results

| Setting | Mean IoU vs hull | IoU >= 0.6 | Notes |
|---|---|---|---|
| Raw crop | 0.824 | 20/20 | better setting; used for the batch |
| 4x upscale | 0.818 | 20/20 | no benefit |

Concept prompts on 4x: "red blood cell" 0/6 cells found, "cell" 5/6. Repeats:
10/10 identical masks (IoU 1.000, solidity Δ 0.000) — SAM box prompting was
deterministic in practice; no repeat term is needed in the noise model.

## Full-batch results (960/961 cells; 1 BLOCKED by an HTTP 500, recorded, excluded)

| Model | Mean kappa [95% CI] | P1 κ / AC1 / PABAK / bal.acc | P2 κ / AC1 / PABAK / bal.acc | P4 κ / AC1 / PABAK / bal.acc |
|---|---|---|---|---|
| BASE (hull) | 0.279 [0.169, 0.378] | 0.318 / 0.343 / 0.328 / 0.657 | 0.108 / 0.213 / 0.164 / 0.555 | 0.412 / 0.420 / 0.412 / 0.718 |
| SAM only | 0.161 [0.038, 0.284] | 0.166 / 0.198 / 0.178 / 0.582 | 0.163 / 0.160 / 0.150 / 0.589 | 0.153 / 0.308 / 0.236 / 0.573 |
| BASE+SAM | **0.374 [0.270, 0.466]** | 0.338 / 0.353 / 0.344 / 0.668 | 0.214 / 0.293 / 0.254 / 0.610 | 0.570 / 0.605 / 0.588 / 0.789 |

Group means (SAM-OK cells): solidity health=1 **0.940** vs health=0 **0.954**;
convexity defects >1px **1.97 vs 1.37**; roughness **1.130 vs 1.105**; mean IoU
vs hull 0.835 vs 0.849; mean SAM confidence ~0.90 in both classes.

## Plain statement of the result

Yes — with the stated uncertainty. SAM mask shape features carry a real
spicule-related signal that the convex-hull contours erase: author-unhealthy
cells have measurably less solid, more defect-bearing SAM masks. Adding SAM shape
to the hull baseline raises LOPO mean kappa from 0.279 to 0.374, with an
improvement in **every** held-out patient (P1 +0.020, P2 +0.106, P4 +0.158).
SAM features alone (0.161) are weaker than the hull baseline, so SAM complements
rather than replaces the lab features. The bootstrap CIs of BASE and BASE+SAM
overlap ([0.169, 0.378] vs [0.270, 0.466]), so the gain is suggestive, not
proven at 95% on mean kappa alone; the consistent per-patient direction is the
stronger evidence. The classifier remains a triage device, never ground truth.
One SAM feature is `sam_iou_author` (mask-vs-hull disagreement), which is itself
part of the shape signal and uses no label information.

## Ledger

Pilot: 72 new SAM calls (cap 75). Full batch: **939 new calls** (cap 941; the 20
pilot raw cells and later the whole LOPO rerun were cache hits). At the
documented $2.50 per 1,000 images, the batch is ~$2.35 of image charges (actual
billing is not visible from the API). Every call is cached in `data/api_cache/`;
reruns are free.
