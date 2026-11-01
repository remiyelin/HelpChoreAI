# HelpChoreAI

**A quality check for medical research measurements. Before anyone trusts a change, it asks if the change is real, noise, or a bad recording.**

![One patient: stable near 20%, then 38%, then back](docs/media/video/thumb.png)

- Live page: LIVE_URL
- Video: VIDEO_URL

Hackathon theme: **Push the Frontier**, "accelerate a scientific experiment".

Research use only. Not medical advice. It diagnoses nothing and treats no one.

## What it tells a lab

VPS13A disease is a very rare neurodegenerative disorder. People with it have spiky red blood cells. Small studies follow the share of spiky cells from visit to visit, using a microscope and a narrow channel. In a study this small, one misread visit matters.

HelpChoreAI answers three questions before anyone interprets a change:

1. Was the recording good enough?
2. Is the change bigger than the normal wobble of this measurement?
3. How many runs does the next visit need?

The statistics decide. AI does the looking, the writing and the checking. AI cannot change the numbers.

## Results

Data: Reichel et al. 2022, five patients. Three were used to build the method (dev). Two were sealed until the code and five predictions were frozen under git tag `eval-v1`.

| Finding | Number | Who |
|---|---|---|
| Faster flow, fewer spiky cells, in every visit | 37 of 37 visits | dev and sealed |
| Same effect on sealed patients | slope −0.32 in both (95% CI −0.36 to −0.28, and −0.37 to −0.27) | dev, sealed |
| A normal reading raises many alarms | 19 alarms in 32 visit pairs | dev and sealed |
| What the rule does with them | 5 confirmed, 4 ruled out, 10 refused | dev and sealed |
| A change the normal reading missed | 1 | dev |
| Smallest change this protocol can call | about 4 points (median band ±3.9) | dev and sealed |
| The tracker stores outlines that cannot show spikes | 2,673 of 2,673 cells fully convex | dev |
| Signed reports that verify on a fresh clone | 21 of 21 | dev |
| Tool checks stop wrong reports, scripted model | 9 signed with checks off, 0 with checks on | dev |

<!--open-result-->
Open weights: 16 of 21 reports signed in open-weight mode carry the same numbers as the cloud run.
<!--/open-result-->

## What did not work

- SAM shape gave little classifier gain on all cells (kappa 0.237 to 0.280) and none on sealed patients (0.033 to −0.052, 180 cells). An early gain of 0.28 to 0.37 existed only on a hard, selected subset.
- AI raters agree only weakly with the human on 100 random cells (AC1 0.345 for Muse Spark 1.3, 0.247 for Muse Spark Open).
- In video mode SAM kept cells in view, but spiky and smooth cells were no longer different in shape. So we track on video and measure on single frames.
- Five predictions were frozen before unsealing. One held fully, four missed at least in part. See the scorecards in [PREREGISTRATION.md](PREREGISTRATION.md) and [docs/POPULATION.md](docs/POPULATION.md).

## Meta tools

| Tool | What it does here |
|---|---|
| SAM 3.1 | Draws the real cell edge from a box prompt (about 2,200 cached calls). Video tracking, with a position gate for identity lag |
| Muse Spark 1.3 | Audit agent with tool calling; second rater with an enforced schema (about 335 cached calls, plus agent turns) |
| Muse Spark Open | Open-weight rater, agent and language auditor, through OpenAI-compatible hosts (about 470 cached calls). See [docs/OPEN_WEIGHT.md](docs/OPEN_WEIGHT.md) |
| Muse Voice Transcribe | Hands-free review notes in the local tool |
| Muse Code | Wrote most of this repository |

## Built during the hackathon

All code in this repository was written during the event. First commit: 28 October 2026. See `git log`.

## Before the hackathon

- Third party: the Reichel et al. 2022 dataset and its tracker outputs, and the published papers we read.
- Ours: from 16 to 25 October we read papers, planned the work and explored the public dataset. Those notes, templates and scripts are not in this repository, and no file in it is identical to any of them.

## Where else this could work

Built for one rare disease. The method fits any lab that measures the same sample many times, records what might disturb the measurement, and compares visits. Candidates: other blood cell shape tests, stored blood quality, imaging flow cytometry, manual cell counts.

None of these has been tested. The −0.32 slope belongs to this device and this label. Each new setting needs its own calibration.

## Limits

- Five patients, one lab, one human rater.
- The label pools two kinds of spiky cell, acanthocytes and echinocytes.
- The false-alarm simulation (0.322 to 0.064) splits runs within one visit. It does not cover day-to-day variation.
- Power is 0.31 for a 5-point change and 0.77 for a 10-point change at current run counts.
- We measured that speed changes the reading, not why.
- Whether red cell shape tracks the disease in the brain is unknown. This makes the marker honest, not meaningful.

## Run it

```bash
git clone <this repository>
cd HelpChoreAI
uv sync
uv run pytest -q
```

Verify a signed report. No key needed, nothing is written:

```bash
uv run python -m src.agent verify P1_0w_2w
```

Open the page locally:

```bash
python -m http.server 8000 --directory web
```

The page replays signed results and calls no model. The local tool with sign-off and voice notes runs with `uv run python src/server.py` on port 8765. Live model calls need keys in `.env` (see `.env.example`).

Raw data is not in the repository. `tools/figshare_ingest.py` fetches it from the public source.

## Licence and attribution

Code: MIT, see [LICENSE](LICENSE). Data: Reichel et al. 2022, Figshare Collection 5793482, CC BY 4.0. See [ATTRIBUTION.md](ATTRIBUTION.md).
