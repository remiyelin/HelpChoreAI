# Open-weight reader: auditing an AI as a measuring instrument

Written and committed before any call of this experiment. Results are appended below the line and this part is not edited.

## Question

Cell by cell, Muse Spark Open agrees only weakly with the human rater (AC1 0.247 on 100 random cells). But a lab does not decide on one cell. It decides on the share of spiky cells in a visit. Errors on single cells may cancel out.

**If Muse Spark Open reads every cell of a visit, does its share follow the human share from visit to visit?**

This is the same question the project asks of the lab: can this reading be trusted, and when not?

## Method

- Model: `meta-models/muse-spark-open`, frozen prompt and schema (`RATER_PROMPT`, `RATER_SCHEMA`), reasoning effort low.
- Input: one frame per cell, the middle frame where it exists. Human labels are never sent.
- Cells: all kept cells of the labelled run in each dev visit (1,944 cells, 22 visits).
- Visit share: `yes / (yes + no)`. `cannot_tell` is excluded and reported.
- Human share: the mean human label on the same cells. Both read the same cells, so sampling noise cannot explain a gap.

## Measures, fixed in advance

1. Spearman correlation of AI and human visit shares, within patient (each patient's mean removed), because differences between patients would inflate an overall number.
2. Mean absolute error in points after a linear calibration fitted on the other patients (leave one patient out).
3. Direction: among consecutive visit pairs where the human share moves by at least 5 points, the share of pairs where the AI moves the same way.
4. Secondary: Spearman correlation between the model's `image_quality: poor` share and the unreadable-cell rate of the visit, as a first look at automated quality control.
5. Cell level, for context: agreement and AC1.

## Verdict rule, fixed in advance

- **Usable as a triage reader** only if within-patient Spearman is at least 0.5 **and** calibrated error is at most 8 points.
- **Not usable as a reader** otherwise. The result is reported either way.
- Only if dev passes: run the sealed patients with the calibration frozen on dev, same thresholds.

## Limits, known before running

- One frame per cell. The human rater saw the whole track.
- One labelled run per visit, about 99 cells, so a visit share is itself noisy.
- The thresholds are our judgement, not a standard.

## Budget

Pilot first, measure cost from reported tokens, then a hard stop in `tools/open_reader.py`.

---

## Results
