# Attribution

## Dataset

Reichel et al. (2022). Microfluidic red blood cell recordings for
chorea-acanthocytosis (VPS13A disease) research, including the authors'
cell-tracking outputs and analysis notebooks.

- Source: Figshare Collection 5793482
- DOI: 10.6084/m9.figshare.c.5793482
- Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)

HelpChoreAI ingests this data with HTTP Range requests
(`tools/figshare_ingest.py`, `.mjs`), records download hashes in
`data/fetch_manifest/`, and de-identifies patient codes to P1–P5 locally.
Raw data (`data/dev/`, `data/frames/`) is git-ignored and can be fetched
again from the source above. Tables in `data/tables/` are computed from it
by the code in `src/` and `tools/`. The public page shows a small selection
of microscope frames from this dataset.

## Software

HelpChoreAI code is released under the MIT License (see `LICENSE`).

Fonts in `web/fonts/` are Newsreader, IBM Plex Sans and IBM Plex Mono, under
the SIL Open Font License 1.1.

## Models

- Meta Model API: SAM 3.1, Muse Spark 1.3.
- Muse Spark Open, open weights, through OpenAI-compatible hosts. Each host
  tested is listed in `docs/OPEN_WEIGHT.md`.

Model responses are cached in `data/api_cache/`, which is git-ignored and
cannot be fetched again from Figshare. The public page shows a small selection
of them: cell outlines, audit verdicts and report narratives.

## AI tools used to build and check this repository

- Muse Code (`muse-wonder-1.0`) wrote most of the code.
- Claude Code wrote the static demo pack, the public interface, the video clip
  tools and the final documents, and audited the repository.
- Antigravity and Gemini checked the steps and reviewed results.

## Influences

The agent's verification pattern was learned from the public repository
`meta-models/legal-agent-workshop`. That repository has no licence, so no code
was copied from it. Nothing here implies endorsement by Meta or by any host.
