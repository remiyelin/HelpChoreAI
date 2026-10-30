# SAM 3.1 Video Tracking vs the Lab Tracker (P-06b)

## Method

20 queue cells (10 author health=1, 10 health=0) with known pickle transits
(`Frames`/`pos_x`/`pos_y`/`Contours`), chosen among 40–170-frame tracks under a
3,000-billed-frame budget (`src/sam_tracking.py`). Consecutive AVI frames
(transit plus 5 lead-in frames; extractor `--range` mode) were rendered as
MPEG-4 clips in the served (flipped) orientation at full strip size; cells
crossing in the same window share one request (17 requests incl. probes, each
with <= 16 objects — here 1–2). Prompt per cell: one half-open box (`max+1`)
from the author contour on its first transit frame, `propagation_direction:
"forward"`, `include_confidence: "true"`. Per tracked frame: SAM mask centroid
vs pickle `pos_x/pos_y`, IoU vs the author contour (`geometry.py`), solidity
and convexity defects (same-grid hull). Records were keyed by (frame, object
id) because stream output can arrive out of order; ids were never joined
across clips or re-entries.

Demo: `docs/media/sam_tracking_demo.mp4` (~10 s, best-tracked clip: median
centroid distance 0.28 px) and `docs/media/sam_tracking_keyframes.png` (6
keyframes; amber = SAM mask, teal = author contour; the strip also contains an
untracked dark cell that is not the prompted object).

## Track agreement (1,598 author frames, 20 cells)

| Group | Median centroid distance (px) | Share within 2 px | Frames lost | Solidity min (median) | Solidity median (median) |
|---|---|---|---|---|---|
| author health=0 (10 cells) | 1.11 | 0.683 | 0 / 860 | 0.929 | 0.961 |
| author health=1 (10 cells) | 0.66 | 0.801 | 0 / 738 | 0.927 | 0.959 |
| Overall | 0.81 | 0.742 | 0 / 1,598 | — | — |

Overall median per-frame IoU vs the author contour: 0.804. Per-cell detail:
`data/tables/sam_tracking_cells.csv`; per-frame: `sam_tracking_frames.csv`.

The averages hide a bimodal outcome. **17 of 20 cells track excellently**
(median distance <= 3.3 px, most at 100% of frames within 2 px). **3 of 20 fail
catastrophically** (median distance 95–317 px): in those clips the SAM mask
advances at almost exactly half the cell's speed from the first frame on, so
the lag grows linearly (diagnosed on the worst cell: SAM frame k matches the
lab position at ~k/2; fps metadata and frame duplication do not change it —
it is a tracker motion failure, not an indexing error in this pipeline). Cell
speed does not explain the failures (a 7.3 px/frame cell failed while an
11.6 px/frame cell tracked at 0.48 px), so the likely cause is object-identity
confusion with channel features or a second object in those clips; the masks
themselves remain cell-shaped and high-solidity even while lagging. SAM never
dropped a track (0 frames lost): it always returns a confident mask, including
when it is hundreds of pixels behind — any downstream use must gate on
agreement with an independent position signal, not on SAM confidence.

Solidity along the transit is essentially identical between author classes in
the tracked masks (min ~0.93, median ~0.96 in both): unlike the per-frame
box-prompt masks (P-06), video-propagated masks show **no** health separation
in solidity. Propagated masks are temporally smoothed, which plausibly erases
exactly the transient concavities that carry the spicule signal.

## Cost

Billed frames are taken from each response's `usage.video_frames_processed`:
**1,581 frames** for the 15 batch clips; 1,833 including the two diagnostic
probes (fps-20 and frame-duplicated re-encodings of the probe clip). At the
documented $0.20 per 1,000 frames that is **$0.32 ($0.37 with probes)** —
within the 3,000-frame / $1 limits. Uploads are cached by content hash and all
tracking responses are cached in `data/api_cache/`; reruns are free.

## Limitations

- 3/20 catastrophic identity lags, unpredictable from cell speed; a production
  tracker would need a per-frame agreement gate or re-prompting (re-prompting
  mid-transit was out of scope and would add billed frames).
- Solidity from propagated masks does not reproduce the P-06 per-frame
  box-prompt signal; do not substitute video tracking for per-frame
  segmentation in the shape analysis.
- One prompt per cell at its first transit frame; cells entering together in
  the same clip share a request, and ids are only meaningful inside that clip.
- Clips are MPEG-4 renders of 40–48 px tall strips upscaled only for the demo;
  SAM received the native resolution (no minimum-size guidance is documented).
