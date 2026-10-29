# Live Multi-Model Benchmark (cached, real data)

Cells: 30 stratified queue cells across P1/P2/P4 with real frames. SAM 3.1 OK 30/30; IoU vs author contour mean 0.82, median 0.825, range 0.693-0.916, fraction >= 0.80: 0.667. Median SAM/author mask-area ratio: 0.829. Note: the author contour is a convex hull that can include MOG2 shadow pixels, so IoU < 1 even for a perfect mask; cached masks predate the PromptBox half-open (+1 px) fix, which applies to future calls only.

Muse Spark 1.3 visual check OK 30/30 (free-text descriptions retained in the CSV only; keyword scoring of them was invalid and has been removed — structured second-rater results: docs/RATERS.md).

Visit pairs: 21. Cloud narrative (muse-spark-1.3, digit-free enforced) + Checker/local audit vs Baseten open-weight audit parity: 21/21.

New (uncached) API calls this run: 0. All calls cached in data/api_cache/; reruns are free. Failures, if any, are recorded as BLOCKED in the CSVs — never replaced with fabricated passes.

Detail: data/tables/live_benchmark_cells.csv, data/tables/live_benchmark_pairs.csv. Reproduce: `uv run python src/run_live_benchmark.py` (cache hits make it $0).

## Old vs new SAM numbers (P-03 re-measurement, 0 new API calls)

| Metric | Old (buggy rasterizer) | New (geometry.py, from cache) |
|---|---|---|
| IoU mean | 0.140 | 0.820 |
| IoU median | 0.126 | 0.825 |
| IoU range | 0.047–0.325 | 0.693–0.916 |
| Share IoU >= 0.80 | 0.000 | 0.667 |
| Median SAM/author area ratio | — | 0.829 |

Visual proof: docs/media/p03_overlay_1..3.png (amber SAM mask on the cell, teal author
contour around it), left untracked for the step checker.

## What was wrong and how we found it

The 29 Oct audit found that the ray-casting rasterizer used for both masks divided by
`max(y[j]-y[i], 1e-9)`: for edges with negative dy the sign is lost, so polygons
over-filled severalfold (a 13x9 ellipse of ~358 px rasterized as ~1,787 px in the
audit's instance; 536 px vs 368 px analytic in our regression pin). Even a perfect SAM
mask could only score ~0.08 against such a reference, so the reported IoU 0.14 measured
the rasterizer, not SAM. The square-vs-itself unit test could not see it (identical
over-fills cancel). The fix is a single geometry module: author contours are filled with
`cv2.drawContours(-1)` at 4x supersampling (plain 1x fill adds a full boundary ring,
~+10% on 20-px cells), SAM masks are rebuilt from their cached row spans — never
ray-cast as polygons — and IoU is computed outside the cache. Re-measured from the same
cached masks (0 new calls), SAM 3.1 actually agrees well with the author contours
(mean IoU 0.820); its masks cover a median 83% of the hull area, consistent with the
hull including non-cell shadow pixels. A second bug fixed for future calls: PromptBox
is half-open, so box prompts were 1 px too small on the right/bottom (~4–5% of a cell);
the cached masks above still carry the old box. Alignment check
(`tools/check_alignment.py`, 50 random cells): inside-contour grey is darker than the
3-px ring in the served orientation for 50/50 cells (mean difference −19.0 vs −11.3
grey levels unflipped; the sign fraction alone saturates because crops are
cell-dominated, the effect size is the discriminating statistic).

## Removed figure (P-05)

An earlier version of this document and the UI reported "Spark vs author agreement
0.429" from keyword-matching free-text descriptions. That figure was invalid: all 16
texts scored as "spicules present" actually denied spicules, and no text affirmed
them. It has been removed everywhere and replaced by the structured second-rater
protocol in docs/RATERS.md (enforced JSON schema, cannot_tell kept separate).
