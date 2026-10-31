# Attribution

## Dataset

Reichel et al. (2022). Microfluidic red blood cell recordings for
chorea-acanthocytosis (VPS13A disease) research, including the authors'
cell-tracking outputs and analysis notebooks (fig2/fig4 treatment context).

- Source: Figshare Collection 5793482
- DOI: 10.6084/m9.figshare.c.5793482
- Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)

HelpChoreAI ingests this data via HTTP Range requests
(`tools/figshare_ingest.py` / `.mjs`), records download hashes in
`data/fetch_manifest/`, and de-identifies patient codes to P1–P5 locally.
Extracted raw data (`data/dev/`, `data/frames/`, `data/api_cache/`) is
git-ignored and re-fetchable from the source above; derived tables in
`data/tables/` are computed by the pipelines in `src/` from that data.

## Software

HelpChoreAI code is released under the MIT License (see `LICENSE`).
Model services are provided by Meta AI (SAM 3.1, Muse Spark 1.3,
Muse Voice Transcribe) and by Baseten (`meta-models/muse-spark-open`);
their outputs are cached locally and are not redistributed as datasets.
