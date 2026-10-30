# Decisions

## P-06 pilot (SAM spicule recovery) — GO, with two conditions

**Decision: GO** for the full 961-cell batch in the **raw** setting, conditional on
(1) the solidity convention fix below and (2) the step checker's visual check of the
contact sheet. Pilot evidence (`src/sam_pilot.py`, `data/tables/pilot_sam.csv`,
sheet `docs/media/sam_pilot_sheet.png`, panels in CSV row order):

- Masks follow the cells: IoU vs author contour >= 0.6 for **20/20** cells in both
  settings (raw mean 0.824, 4x mean 0.818). The contact sheet shows the amber mask
  on the target cell in all 20 panels, following concave/crescent shapes that the
  convex hull bridges. Upscaling 4x does **not** help (slightly worse), so the full
  batch should use raw 200x40/48 crops — this also keeps the call count at 961.
- Concept prompts on 4x crops: "red blood cell" found **0/6** cells; "cell" found
  5/6 (1 mask each). Concept prompting is not a substitute for the box prompt here.
- Repeatability (segmentation noise model): 10 repeated box prompts returned
  **identical masks** (IoU 1.000, solidity difference 0.000 on all 10). Documented
  run-to-run variation was not observed; SAM's contribution to the noise budget is
  ~0 at this setting, so repeats in the full batch are unnecessary.
- Confidence: `metadata.include_confidence` was honoured (mean ~0.90, all masks).
- Spicule signal in the pilot is **not yet visible**: SAM solidity is ~1.0 in both
  author classes (health=0: 1.016, health=1: 1.003), convexity defects >1px average
  1.7 vs 2.0, roughness 1.122 vs 1.132 (n=10 each — underpowered by design). The
  full-batch LOPO (BASE vs BASE+SAM shape vs SAM only) is the actual test; the pilot
  only certifies that the masks are valid enough to run it.

**Condition 1 (solidity convention):** pilot solidity slightly exceeds 1.0 in some
cells (range 0.92–1.05) because mask area is a pixel count while hull area is a
supersampled polygon area. For the full batch, hull area must be the filled hull
**pixel count on the same grid** so solidity <= 1 by construction.

**Condition 2 (budget):** pilot spend was 72 new SAM calls (62 planned batch calls
+ 7 zero-mask concept re-attempts on the cached rerun + 3 one-cell probes during
development; cap was 75). At the documented $2.50 per 1,000 images that is ~$0.18
of image charges (actual billing not visible from the API). The full batch needs
961 new calls (~$2.40 at the same rate) — approve explicitly before it runs.

Full-batch design (Steps 2–4, not yet run): raw-setting box prompts on all 961
queue cells, SAM shape features (area, perimeter, solidity, defects, roughness,
confidence), LOPO BASE vs BASE+SAM vs SAM-only, `docs/SAM_SPICULES.md`, commit
`fix(geometry): correct contour fill; SAM IoU re-measured from cache` follow-up.
Awaiting the step checker's go after inspecting the contact sheet and this ledger.
