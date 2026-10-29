# Live Multi-Model Benchmark (cached, real data)

Cells: 30 stratified queue cells across P1/P2/P4 with real frames. SAM 3.1 OK 30/30; IoU vs author contour mean 0.14, median 0.126, range 0.047-0.325, fraction >= 0.80: 0.0.

Muse Spark 1.3 visual check OK 30/30; spicule-keyword vs author-health agreement 0.429 (n=21, keyword heuristic on free text, not a label).

Visit pairs: 21. Cloud narrative (muse-spark-1.3, digit-free enforced) + Checker/local audit vs Baseten open-weight audit parity: 21/21.

New (uncached) API calls this run: 29. All calls cached in data/api_cache/; reruns are free. Failures, if any, are recorded as BLOCKED in the CSVs — never replaced with fabricated passes.

Detail: data/tables/live_benchmark_cells.csv, data/tables/live_benchmark_pairs.csv. Reproduce: `uv run python src/run_live_benchmark.py` (cache hits make it $0).

## Interpretation (do not over-claim)

- SAM 3.1: the concept prompt ("red blood cell") returned zero masks on all 30 tiny
  200x48 grayscale crops; every IoU above uses the labelled box-prompt (author box)
  fallback. Even then, SAM masks agree poorly with author contours (mean IoU 0.140,
  max 0.325, none >= 0.80). SAM is therefore a visual aid in the overlay only; the
  author/human contour remains the measurement source. (Two bugs were found and
  fixed to measure this honestly: crops are 200x48 not 200x40, and the Windows
  Proactor event loop is unusable in this sandbox.)
- Muse Spark 1.3 visual check: free-text morphology descriptions match the author
  health label only 42.9% of the time via the spicule keyword heuristic (9/30 texts
  with no spicule mention either way). It is a second pair of eyes for the human
  reviewer, not a labeler.
- Audit parity: on all 21 visit pairs the Baseten open-weight auditor's verdict
  matched the local Checker + rule-auditor verdict (21/21, all PASS on untampered
  signed reports). Parity is on clean reports; tamper cases remain blocked by the
  local gate (see Checker tests).
