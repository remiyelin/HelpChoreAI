# Submission text

**Project:** HelpChoreAI

**One line:** A quality check for medical research measurements: before anyone trusts a change, it asks if the change is real, noise, or a bad recording.

**Theme:** Push the Frontier

**Description (about 150 words):**

In very rare diseases, studies are small and one misread visit matters. HelpChoreAI audits a real measurement: the share of spiky red blood cells in people with VPS13A disease, from public microscope recordings.

We found that speed changes the number. Faster cells look less spiky, in all 37 visits, with the same effect in two patients we kept sealed. Across 32 visit pairs, a normal reading raises 19 alarms. Our rule confirms 5, rules out 4, refuses 10 because the recording was not good enough, and finds one change the normal reading missed.

SAM 3.1 draws the real cell edge. A Muse Spark agent writes each audit, but it cannot change a number. Muse Spark Open, on open weights, stops sentences that say more than the data. As a cell reader it failed our own audit, and we say so. Every report is signed, and your browser verifies it.

Any lab can run the same rule on its own table with one command. We publish what failed too. It treats no one. It stops a small study from fooling itself.

**Meta tools:** SAM 3.1, Muse Spark 1.3, Muse Spark Open, Muse Voice Transcribe, Muse Code

<!--open-result-->
Open weights: 21 of 21 reports signed in open-weight mode carry the same numbers as the cloud run.

On baseten: advice hidden in normal words stopped 12 of 12 (fixed rules 0 of 12); clean reports passed 12 of 12.
<!--/open-result-->

**Built during the hackathon:** All code in the repository, first commit 28 October 2026. The data is public (Reichel et al. 2022, CC BY 4.0).

**Research use only. Not medical advice.**

**Links**

- Repository: REPO_URL
- Live page: LIVE_URL
- Video: VIDEO_URL
