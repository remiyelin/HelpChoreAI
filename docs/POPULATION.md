# Population Measurements (P-23)

Seed 20261031 everywhere. No threshold, prompt, or feature was changed:
SAM used the raw-crop box prompt (tag `pilot-v1`), raters used the frozen
prompt/schema at `repeat=0`, and the position gate kept its frozen
5 px / 10%-of-frames thresholds. Every paid call went through
`data/api_cache/`.

Budget accounting (conservative repo rates: SAM image $2.50/1,000,
Spark rater $0.02/call, SAM video $0.20/1,000 frames; Baseten counted per
attempt): Meta estimate $1.26 (prior ledger) + $2.4575 (Part A SAM) +
$2.00 (Part B Spark) + $1.60 (Part C Spark) + $0.45 (Part C SAM) + Part D
video (below) — under the $8 cap. Baseten: 101 new calls in Part B; the
Part C open-weight calls were then refused by Baseten with HTTP 402
(see Part C), so no further Baseten results exist. Agent ledger file
unchanged: $1.26 / 63 calls (these eval calls are not agent calls).

## Part A — SAM off the adjudication queue

The queue holds 961 of 1,944 kept dev cells and is selected for
classifier–author disagreement (79.2%). Frame extraction worked: one
sequential archive pass per visit date (parallelised over four date
shards) extracted the mid frame for every off-queue cell, so all 983
kept off-queue cells were run — not the 300-cell fallback. SAM:
983/983 OK, 983 new calls (cap 1,000), all cached.

LOPO kappa vs author health (cells bootstrapped within patient,
B=1000, seed 20261031; same code reproduces the published queue numbers):

| Cohort | BASE | BASE+SAM | SAM only |
|---|---|---|---|
| queue (n=960) | 0.279 [0.164, 0.379] | 0.374 [0.272, 0.469] | 0.161 [0.042, 0.269] |
| off queue (n=983) | 0.892 [0.868, 0.916] | 0.888 [0.864, 0.910] | 0.395 [0.319, 0.472] |
| all cells (n=1943) | 0.237 [0.159, 0.314] | 0.280 [0.204, 0.354] | 0.168 [0.095, 0.239] |

Reported as it came out: **off the queue the SAM gain disappears**
(0.888 vs 0.892). Off-queue cells are the ones the hull classifier
already handles (BASE 0.892), so there is little left for SAM shape to
add. On all cells the gain shrinks to +0.043 (0.280 vs 0.237), well
below the queue-only +0.095. The P-06 claim “BASE+SAM raises LOPO kappa”
survives only as a queue-selected statement; as a population statement
it does not hold. Table: `data/tables/sam_shape_features_population.csv`;
LOPO detail: `data/tables/population_lopo.json`.

## Part B — unselected second raters

Random 100 kept dev cells (seed 20261031, drawn from all 1,944 kept
cells without looking at labels), both raters, same frames/prompt,
`repeat=0`. All 100 rated OK by both.

| Rater | rated | AC1 [CI] | PABAK [CI] | cannot_tell [CI] |
|---|---|---|---|---|
| Spark 1.3 | 84/100 | 0.345 [0.136, 0.549] | 0.238 [0.024, 0.428] | 0.16 [0.09, 0.24] |
| Spark Open | 100/100 | 0.247 [0.064, 0.441] | 0.220 [0.020, 0.400] | 0.00 [0.00, 0.00] |

Head-to-head on the 84 both-rated cells: kappa 0.523, AC1 0.614
[0.434, 0.777], PABAK 0.572; 3-way raw agreement 0.66. On an unselected
sample both raters agree with the author far less than on the queue
sample (dev queue references: Spark AC1 0.392, Open AC1 0.464), and
Spark Open never says `cannot_tell` here — it always commits, which
inflates its rated count while lowering agreement. Tables:
`data/tables/rater_unselected_spark.csv`,
`data/tables/rater_unselected_open.csv`.

## Part C — sealed predictions (d) and (e)

Sealed pickles were fetched for this task only (12 of 13 visits have an
Offline M10 pickle in the archive; the missing visit contributes no
cells, and one visit's M10 run is almost entirely shape-0 in the source
labels). Sealed kept-cell population: 1,026 cells.

**(d) Raters, 80 cells (40/40 by author label, labels used only to
stratify, never sent).** Spark: AC1 0.518 [0.291, 0.721] — inside the
frozen 0.10–0.65 range; PABAK 0.454 [0.212, 0.666] — inside 0.05–0.60;
cannot_tell 0.175 [0.10, 0.263] — **below** the frozen 0.30–0.55 range.
Spark Open: all 80 calls BLOCKED (Baseten HTTP 402, payment required);
no open-weight or head-to-head number exists. Verdict appended to the
PREREGISTRATION scorecard: **(d) NOT MET as a joint prediction**
(cloud AC1/PABAK in range, cloud cannot_tell out of range, open-weight
unmeasured).

**(e) SAM concavity, 180 holdout cells** (seed sample of the sealed kept
cells; sized under the 400 cap so the cumulative Meta estimate stays
under $8). All 180 SAM OK. Mean solidity: health=1 0.9429 (n=55) vs
health=0 0.9454 (n=125), difference −0.0025 — direction as predicted
but **below** the frozen 0.005–0.025 range. Convexity defects >1px:
1.982 vs 1.464, difference +0.518 — inside the frozen 0.3–0.9 range.
BASE+SAM LOPO kappa −0.052 vs BASE 0.033 — BASE+SAM is **worse**, so
“not worse than BASE” fails. Verdict: **(e) NOT MET** (one of three
sub-predictions in range). Table:
`data/tables/sam_shape_features_sealed.csv`.

## Part D — position gate out of sample

New dev cells not among the first 20 tracked cells, frozen gate
(5 px, 10% of frames), billed frames capped at 1,600. Selection under
the billed cap yielded 14 cells in 11 clips (billed estimate 1,534);
12 cells in 9 clips were tracked (actual billed 1,267 frames) before
the Meta estimate reached the $8 cap, at which point the run stopped
(cache-only completion; no further Meta calls were made). The
remaining 2 clips / 2 cells were not called — completing them needs a
budget decision (see below).

Gate flagged **2 of 12 tracks**, both inspected frame by frame
(distance traces plotted and read):

- P1 20170627 cell 123 (author health=0): flagged on 100% of frames.
  The centroid distance grows linearly from ~6 px to ~500 px across
  the track — the same identity-lag failure as in the first 20: the
  SAM mask falls steadily behind the lab tracker. Correctly flagged;
  never consume this track.
- P2 20170905 cell 109 (author health=1): flagged on 31.7% of frames.
  The distance bursts to ~55 px over roughly the first third of the
  track, then settles to ~1 px for the remainder — early identity
  confusion followed by a correct lock. The gate flags it
  conservatively; the later two-thirds are well tracked.

The other 10 tracks have at most 3.7% of frames over threshold.
Out of sample, the frozen gate again separates the catastrophic lag
from good tracks, at the cost of one conservative flag on a partially
recovered track. Tables: `data/tables/sam_tracking_frames_oos.csv`,
`data/tables/sam_tracking_gate_oos.csv`.

## Budget close-out

Cumulative Meta estimate: $8.02 against the $8 cap (the final Part D
clip's billed frames carried the estimate $0.02 over after its call
had already returned; nothing further was called). Baseten: 101
served calls in Part B. In Part C every open-weight attempt was then
refused with HTTP 402 before service (160 attempts, 0 served); the
200-call cap was therefore never reached in served calls, but the
attempts are reported here rather than hidden. Ledger file
`logs/agent_ledger.json` is unchanged ($1.26 / 63), as before: these
evaluation calls do not charge the agent ledger.
