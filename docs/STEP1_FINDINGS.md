# Step 1 Findings — Ingest & Provenance (empirical, from real files)

Dataset: Reichel et al. 2022, Figshare Collection 5793482 (doi:10.6084/m9.figshare.c.5793482),
authors' code: gitlab.gwdg.de/freiche/changes-in-blood-cell-deformability-in-chorea-acanthocytosis-and-effects-of-treatment-with-dasatinib-or-lithium
All patient references below use P1..P5 only. Initials from source filenames were renamed at ingest and are never stored.

## What was executed

- `tools/figshare_ingest.mjs` (Node, HTTP Range + ZIP64 central-directory parser over concatenated split parts)
  and `tools/figshare_ingest.py` (equivalent fallback for an external terminal).
- Figshare totals: 24 articles, ~413.6 GB. Shape archives: P1 6 parts / 108.8 GB / 2077 entries;
  holdout manifests sealed for P3 (1510 entries, 91.5 GB) and P5 (entry count + hashes in
  `data/fetch_manifest/holdout_P*_manifest.json`). Holdout entry names are stored only as SHA-256; no holdout content was fetched from Figshare.
- Extracted (dev only, 474 fetch-log records with SHA-256 in `data/fetch_manifest/fetch_log.json`):
  P1: 213 Results files; P2: 188; P4: 57; plus per-archive `channel_size.txt`, first-visit
  `Cell_tracking_new.py` + `shape_selector_Ac.py`, and 3 contour samples per patient.
- Sandbox note: Windows `git clone` failed (schannel SEC_E_NO_CREDENTIALS) and `python.exe` is a Store stub;
  Node `fetch` (OpenSSL) works and was used. `uv` 0.11.19 is available for a real Python env in later steps.

## Holdout integrity disclosure

During GitLab discovery (before Figshare sealing), the authors' `result_summaries/*_results_MCFM.tsv`
files in the public GitLab repo were opened at schema/aggregate-count level for all five patients,
including the two holdout patients. No Figshare holdout content was read, no tuning used those
aggregates, and GitLab summaries are excluded from all development decisions going forward.
The sealed unit is the Figshare extraction; this incident is logged here permanently.

## Exact shape taxonomy (shape_selector_Ac.py, lines 837-838 + GUI buttons 839-870)

| code | label | authors' deformed set (notebooks) |
|---|---|---|
| 0 | skipped cell | excluded ("leave out skipped cells") |
| 1 | parachute | deformed |
| 2 | slipper | deformed |
| 3 | asym. parachute | deformed |
| 4 | discocyte / undeformed | not deformed |
| 5 | multilobe | deformed |
| 6 | tumbler | not deformed |
| 7 | undefined deformed | deformed |

Orthogonal second label `health`: 0 = Healthy, 1 = Unhealthy (separate radio buttons; selecting
health deselects shape buttons in the GUI, but saved rows carry both fields). Empirically every
shape 1-7 occurs with both health values, so `health` is an independent rater judgement
(the "Ac" acanthocyte/abnormal flag), NOT derivable from shape class. Results file format
(`Results/results_M<run>_<flow>.txt`, header `# number, shape, velocity, health`):
`cell_no, shape, velocity_mm_s, health` — velocity is recomputed and overwritten on save
(`get_shape_and_save`), flow in the filename is the pump setting in uL/s (e.g. 0.016).

## Empirical label statistics (dev, extracted Results files)

- P1: 11 visits (0w,2w,4w,6w,8w,10w,14w,20w,24w,29w,53w), 23,939 rows, skipped 21.1%.
- P2: 10 visits (0w..51w), 22,145 rows, skipped 20.0%.
- P4: 3 visits (0w,9w,18w), 6,150 rows, skipped 16.4%.
- Skipped (shape 0) rows are ~1/5 of all rows and are almost always health 0 — they must be
  excluded from denominators (authors do this) and the skip rate itself reported per run as QC.
- Flow settings per patient span 0.0010-0.040 uL/s but filenames mix formats (`0.014` vs `0.0140`,
  P4 also `0.019`, `0.021`) — flow must be parsed numerically, never string-matched.
- P1 visit 29w has 40 runs vs 8-22 elsewhere (contains a nested other-patient Online folder in the
  source archive; ingest skips nested other-patient entries — see `skipped_nested_other_patient`).

## Frames <-> contours <-> results mapping

- `*_contours.txt` (Online, per run `M<run>_<flow>ul_s_contours.txt`): blocks headed
  `Contour in frame <n>` followed by (x,y) pixel points. One run sample: 15,116 contour blocks
  vs 146 labelled cells in its Results file — contours are per-frame observations along tracks,
  not per-cell records.
- `Cell_tracking_new.py` builds the per-cell tracks (Frames, pos_x, pos_y, Area, axes,
  circularity, Contours) saved as `Offline/M<run>_results.p` pickles; `shape_selector_Ac.py`
  loads those pickles, displays each tracked cell from the `.avi`, and writes one Results row
  per tracked cell (row index = cell number in the pickle). Cell number order therefore maps
  Results row -> pickle cell index -> its frame list -> contour blocks in those frames.
- `channel_size.txt` (first visit of P1): `wb=11.12, wt=9.85, h=10.41` (um) — ~10x10 um channel
  confirmed empirically, with per-archive width variation to record per visit in Step 2.
- Copies of both .py files are stored per-visit inside each archive (Python 2, Tkinter GUI,
  `PIX=0.34 um`, frame rate from `*camera.ini`, velocity filter sigma/v_max=5 mm/s defaults in
  the selector; `velocity_filter` in the shipped file has a known operator-precedence quirk at
  line 129 — do not reuse velocity code without review).

## Implications for Step 2 (decisions needed)

1. Measurand definition must choose: (a) `health==1` fraction among non-skipped cells
   (rater abnormal/acanthocyte flag), (b) authors' deformed fraction (shapes 1,2,3,5,7),
   or (c) both reported with (a) primary. The pinned plan wording ("spiculated/abnormal")
   maps most honestly to (a) with (b) as the flow-standardized secondary endpoint.
2. Denominators exclude shape 0; skip-rate QC threshold must be pre-registered.
3. Flow standardization should use the numeric filename flow + per-cell velocity jointly;
   velocity itself is flow-dependent, so the RCV model must not treat them as independent.
