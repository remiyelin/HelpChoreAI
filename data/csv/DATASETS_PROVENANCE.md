# Data Provenance and Checksum Catalog

**Written with**: ALCOA+ principles in mind. This is not a validated GxP record.  
**Target Repository**: `HelpChoreAI`  
**Directory**: `data/csv/`  
**Manifest File**: `data/csv/MANIFEST_CSV_DATASETS.sha256`  
**Verification Tool**: `tools/fetch_csv_datasets.py`  
**Date Generated**: 2026-11-02  
**Status**: Public datasets. 13 files are instrument measurements or tables extracted from them; 5 are derived or example files (the three Reichel 2022 tables are computed by HelpChoreAI's own code, and two small files are example files from dclab's test folder). See the Role column.

---

## 1. Summary

This file lists where each table in `data/csv/` comes from, its licence, its size and its SHA-256 checksum.

### 1.1 What Is Measured and What Is Not
No values were simulated or invented for these files. Two points need care: (a) the three `RBC_ChAc_Reichel2022_*` tables are computed by HelpChoreAI's code from the Reichel et al. 2022 recordings (the same tables as in `data/tables/`), not taken from the authors; (b) `RBC_Leukocytes_WholeBlood_Muller2021_SingleCells.csv` (18 events) and `RTDC_Isoelastic_YoungsModulus_Lookup.csv` (20 points) come from example files in dclab's software test folder, and the isoelastic points are computed values, not measurements. `RTDC_Osm_all_replicates_singlecells.csv` repeats the four `RTDC_Osm_set*` files in one table, so its rows are not additional cells.

### 1.2 ALCOA+ Data Integrity Framework Alignment
- **Attributable**: Each file names its source repository and publication.
- **Legible**: Delivered as open, platform-independent UTF-8 tabular formats (`.csv` and `.txt`) with standardized header nomenclatures.
- **Contemporaneous**: Not claimed. Original acquisition times are only as recorded in the source files.
- **Original**: Values are copied from the source files without smoothing or imputation; the Reichel tables are derived (see 1.1).
- **Accurate**: Row counts and checksums are checked by `tools/fetch_csv_datasets.py`; values were not re-validated against the publications.
- **Complete**: All experimental replicates, treatment doses, and un-gated flow regimes documented.
- **Consistent**: Pinned cryptographic SHA-256 digests ensure byte-for-byte reproducibility across runs and environments.
- **Enduring**: Open standards accessible without proprietary software locks or deprecated binaries.
- **Available**: Offline-verifiable via `python tools/fetch_csv_datasets.py` requiring zero external cloud dependencies once downloaded.

---

## 2. Integrated Datasets Inventory & Biophysical Parameter Matrix

| # | Dataset File | Biological System / Cell Type | Experimental Conditions / Confounders | Source Repository & DOI / URL | License | File Size (Bytes) | Row Count | Single-Cell Events | Measured Physical Parameters |
|---|---|---|---|---|---|---|---|---|---|
| **1** | `RTDC_Osm_set1_20160129.txt` | Human Promyelocytic Leukemia (HL60) | Osmolarity series: 200, 250, 300, 400, 500, 600, 700 mOsm; 20x20 µm channel; Q = 0.04 µL/s | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 1,018,492 | 18,579 | 18,579 | Osmolarity (mOsm), Cross-sectional Area (µm²), Diameter (µm), Volume (µm³), Deformation |
| **2** | `RTDC_Osm_set2_20160131.txt` | Human Promyelocytic Leukemia (HL60) | Osmolarity series: 200, 250, 300, 400, 500, 600, 700 mOsm; Replicate 2; Q = 0.04 µL/s | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 1,183,168 | 21,584 | 21,584 | Osmolarity (mOsm), Cross-sectional Area (µm²), Diameter (µm), Volume (µm³), Deformation |
| **3** | `RTDC_Osm_set3_20160202.txt` | Human Promyelocytic Leukemia (HL60) | Osmolarity series: 200, 250, 300, 400, 500, 600, 700 mOsm; Replicate 3; Q = 0.04 µL/s | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 1,359,110 | 24,800 | 24,800 | Osmolarity (mOsm), Cross-sectional Area (µm²), Diameter (µm), Volume (µm³), Deformation |
| **4** | `RTDC_Osm_set4_20160204.txt` | Human Promyelocytic Leukemia (HL60) | Osmolarity series: 200, 250, 300, 400, 500, 600, 700 mOsm; Replicate 4; Q = 0.04 µL/s | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 1,168,957 | 21,316 | 21,316 | Osmolarity (mOsm), Cross-sectional Area (µm²), Diameter (µm), Volume (µm³), Deformation |
| **5** | `RTDC_Osm_all_replicates_singlecells.csv` | Human Promyelocytic Leukemia (HL60) | Pooled 4-day biological replicates across 200–700 mOsm osmotic gradients | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 5,748,012 | 86,279 | 86,279 | Replicate Set, Date, Osmolarity, Area, Diameter, Volume, Deformation |
| **6** | `Osm_RTDC_Medians_Summary.csv` | Human Promyelocytic Leukemia (HL60) | Replicate-level median summary across osmolarities | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 3,103 | 28 | Summary (86,279 cells) | Osmolarity, Date, Replicate, Median Deformation, Median Diameter, Median Volume, Cell Counts |
| **7** | `RBC_ChAc_Reichel2022_SingleCells.csv` | Human Red Blood Cells (Erythrocytes / Acanthocytes) | 5 ChAc patients (P1–P5), 37 visits; computed by HelpChoreAI from the recordings (`data/tables/cell_features_M10.csv`) | Figshare Collection 5793482 / [10.6084/m9.figshare.c.5793482](https://doi.org/10.6084/m9.figshare.c.5793482) | CC BY 4.0 | 326,058 | 2,674 | 2,674 | Cross-sectional area mean/std, Circularity mean/std, Axis/Aspect ratio, Rater label `health` (0 = healthy, 1 = unhealthy / acanthocyte), Frame count |
| **8** | `RBC_ChAc_Reichel2022_PerRun.csv` | Human Red Blood Cells (Erythrocytes / Acanthocytes) | 437 runs across 37 visits; flow rate 0.001–0.04 µL/s, not controlled; computed by HelpChoreAI (`data/tables/per_run.csv`) | Figshare Collection 5793482 / [10.6084/m9.figshare.c.5793482](https://doi.org/10.6084/m9.figshare.c.5793482) | CC BY 4.0 | 40,516 | 437 | 437 runs | Volumetric flow rate (`flow_ul_s`), Total events, Kept events, Skipped events, Deformed cell count, Fraction deformed |
| **9** | `RBC_ChAc_Reichel2022_PixelFeatures.csv` | Human Red Blood Cells (Erythrocytes) | Pixel features computed by HelpChoreAI (`data/tables/cell_pixel_features.csv`) | Figshare Collection 5793482 / [10.6084/m9.figshare.c.5793482](https://doi.org/10.6084/m9.figshare.c.5793482) | CC BY 4.0 | 384,277 | 961 | 961 | 29 pixel-level morphometric parameters: area, circularity, perimeter, axis ratio, convex hull area |
| **10** | `RBC_Reticulocytes_Rosendahl2018_SingleCells.csv` | Human Erythrocytes & Reticulocytes | Whole blood; Syto13 RNA fluorescence; 20x20 µm channel; Q = 0.02 µL/s (sample: 0.005, sheath: 0.015); CellCarrier buffer | DCOR package `figshare-7771184-v2` / [10.6084/m9.figshare.7771184.v2](https://doi.org/10.6084/m9.figshare.7771184.v2) | CC0 1.0 (Public Domain) | 3,962,568 | 22,000 | 22,000 | Convex Area, Measured Area, Circularity, Deformation ($1 - \text{circ}$), Brightness average/SD, Syto13 FL1 fluorescence (RNA marker), Aspect ratio, Bounding box size |
| **11** | `RBC_Leukocytes_WholeBlood_Muller2021_SingleCells.csv` | Human Whole Blood (Erythrocytes + Leukocytes) | Example file `fmt-hdf5_image-mask-blood_2021.zip` from dclab's software test folder (`tests/data`); 18 events, for software testing | GitHub `DC-analysis/dclab` | dclab repository licence (GPL-2.0 unless a directory states otherwise); not CC0 or MIT | 3,892 | 18 | 18 | Area (µm²), Convex Area, Deformation, Circularity, Aspect ratio, Inertia ratio, Average brightness, Position, Frame |
| **12** | `Leukocytes_WBC_Rosendahl2018_SingleCells.csv` | Human Peripheral Blood Leukocytes (Neutrophils, Monocytes, Lymphocytes) | Channel 20x20 µm; Q = 0.06 µL/s (sample: 0.015, sheath: 0.045); CellCarrierB buffer; flash duration 2.0 µs; frame rate 3,200 fps | DCOR package `figshare-7771184-v2` / [10.6084/m9.figshare.7771184.v2](https://doi.org/10.6084/m9.figshare.7771184.v2) | CC0 1.0 (Public Domain) | 1,489,173 | 7,619 | 7,619 | Area convex, Area measured, Area ratio (porosity), Aspect ratio, Brightness average/SD, Circularity, Deformation, Inertia ratio, Position x/y, Bounding box size |
| **13** | `Calibration_Beads_Hydrogel_Rosendahl2018_SingleCells.csv` | Standard Polyacrylamide Hydrogel Calibration Beads | Constant batch elasticity; stepped flow rates; Channel 20x20 µm; Q = 0.06 µL/s; CellCarrierB buffer | DCOR package `figshare-7771184-v2` / [10.6084/m9.figshare.7771184.v2](https://doi.org/10.6084/m9.figshare.7771184.v2) | CC0 1.0 (Public Domain) | 1,029,918 | 5,000 | 5,000 | Convex area, Measured area, Area ratio, Aspect ratio, Circularity, Deformation, FL1/FL2/FL3 fluorescence, Inertia ratio, Bounding box size |
| **14** | `HL60_Leukocyte_LatB_MultiFlow_Runs.csv` | Human Promyelocytic Leukemia Cells (HL60) | Latrunculin B actin perturbation (0–0.1 µM); multi-flow rates Q = 0.04, 0.08, 0.12 µL/s; 5 biological replicates | Figshare [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) / GitHub `dicarlo-lab/metadeformability` | CC0 1.0 (Public Domain) | 19,098 | 140 | 105 active runs (237,813 cells) | Volumetric flow rate (`FR`), LatB concentration, Cell count (`N`), Median size (`MedS`), Median deformation (`MedD`), StDev deformation, Relative deformation (`RD`) |
| **15** | `HL60_Leukocyte_LatB_Titration_SingleCells.csv` | Human Promyelocytic Leukemia Cells (HL60) | Latrunculin B actin perturbation dose-response (0, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1 µM); Q = 0.04 µL/s | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 684,921 | 12,331 | 12,331 | LatB dose (µM), Area (µm²), Diameter (µm), Volume (µm³), Deformation |
| **16** | `HL60_Leukocyte_Strain_300mOsm_SingleCells.csv` | Human Promyelocytic Leukemia Cells (HL60) | Isotonic 300 mOsm benchmark; Channel 20x20 µm; Q = 0.04 µL/s | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 651,338 | 2,188 | 2,188 | Convex Area (px), Measured Area (px), Area (µm²), Circularity, Deformation, Young's Modulus ($E$, kPa), Aspect ratio, Volume (µm³) |
| **17** | `LatB_RTDC_Medians_Summary.csv` | Human Promyelocytic Leukemia Cells (HL60) | Replicate-level LatB titration medians across 5 independent experiment dates | Di Carlo Lab MetaDeformability / [10.6084/m9.figshare.11704119.v2](https://doi.org/10.6084/m9.figshare.11704119.v2) | CC0 1.0 (Public Domain) | 3,758 | 35 | Summary (81,894 cells) | LatB dose, Date, Replicate, Median Deformation, Median Diameter, Median Volume, Cell count |
| **18** | `RTDC_Isoelastic_YoungsModulus_Lookup.csv` | Computed reference values, not measurements | Example file `example_isoelastics.txt` from dclab's software test folder; isoelastic lines of the kind described by Mietke et al. 2015 | GitHub `DC-analysis/dclab` (theory: [10.1016/j.bpj.2015.09.006](https://doi.org/10.1016/j.bpj.2015.09.006)) | dclab repository licence (GPL-2.0 unless a directory states otherwise); not CC0 or MIT | 1,067 | 20 | Computed reference | Area (µm²), Deformation ($D$), Young's Modulus ($E$, kPa) |

---

## 3. Cryptographic Checksum Manifest (SHA-256)

Verified exact SHA-256 digests matching `MANIFEST_CSV_DATASETS.sha256`:

```
ef166153717702fa7ba26e3eb3b044f6e2bf12daa894d5688b4c443873c945f6  Calibration_Beads_Hydrogel_Rosendahl2018_SingleCells.csv
3173bcb8911df4b3cca0ff1eace3dbdf5c43ef8057cb9bf5d4cb084db80c570f  HL60_Leukocyte_LatB_MultiFlow_Runs.csv
a7e501c160beb9c3af0b25d8586b56cbd35cfd9d836a7b6fc9f02776c438af3c  HL60_Leukocyte_LatB_Titration_SingleCells.csv
26f96b4dac9db75414dd5e1bb43de318f29f92a860c8ee36909694a0c69fda87  HL60_Leukocyte_Strain_300mOsm_SingleCells.csv
1d64f342f89b206693774888bb1f3fd0a53de1e04cebede1d4e791440b2e9616  LatB_RTDC_Medians_Summary.csv
20bbba48df58a115a192d062e7bb9fa2bd635a9a833d165bf16e6df23159581d  Leukocytes_WBC_Rosendahl2018_SingleCells.csv
b4eed403639fbd19cfe1795a3a0a3d0ca008fad233161c07f48fec3c4874c43c  Osm_RTDC_Medians_Summary.csv
169bfb9c36c75263ac77a3119c5838fbec33ebd0122144d3fab0bfffd648f064  RBC_ChAc_Reichel2022_PerRun.csv
6121df99688cd870179d81a93c65030fc792bd9acf3392ce773674a792588485  RBC_ChAc_Reichel2022_PixelFeatures.csv
6e8d1a8d661e067a249221ad55dfe747eb81acfc1ab2de9595138c323ab6127b  RBC_ChAc_Reichel2022_SingleCells.csv
061ef3612d7d6008608826be7cbad52b5a540b7223410f382639e9383b4a6cb1  RBC_Leukocytes_WholeBlood_Muller2021_SingleCells.csv
9e61525e26f6feb1e3c6738631a7611c926bb8cc7988a047bde6cac92c764284  RBC_Reticulocytes_Rosendahl2018_SingleCells.csv
55279c6fd7990c93d01ed8bb70a1fa61f8588dae6e8bad0b90f32690e7f7af84  RTDC_Isoelastic_YoungsModulus_Lookup.csv
4e81b7cbbfd1cbbec970ee78822e368a90cca9fa5a7626c431bc4f5f94d5155c  RTDC_Osm_all_replicates_singlecells.csv
a29bc7f40b13aba168267d37ce2b3d8e382a8f2f99e7fa7fa6d59b9a94029c7e  RTDC_Osm_set1_20160129.txt
816ea14b4bf431213072bef26aabb41bc03d744d58033aec2b8990c3120d6eaa  RTDC_Osm_set2_20160131.txt
b9997e48d71ddb8f909be2ff461e49fd9d60998925ca242c781dc460345f08ce  RTDC_Osm_set3_20160202.txt
0aa9b9cb51c1de1d884c04573da6070a2d467e90344b88b5ef1ce8305361e966  RTDC_Osm_set4_20160204.txt
```

---

## 4. Primary Citations and Open Repository Records

1. **Osmolarity & Actin Perturbation Series**:
   - Urbanska, M., Muñoz, H. E., Bagnall, J. S., Otto, O., Manalis, S. R., Di Carlo, D., & Guck, J. (2020). *A comparison of microfluidic methods for high-throughput cell deformability measurements*. **Nature Methods**, 17(6), 587–593. DOI: `10.1038/s41592-020-0818-8`. Data Repository: Figshare DOI `10.6084/m9.figshare.11704119.v2`.
2. **Chorea-Acanthocytosis Erythrocyte Cohort**:
   - Reichel, F., Kräter, M., Jacobi, A., et al. (2022). Dataset of microfluidic red blood cell recordings in chorea-acanthocytosis (VPS13A disease); see `ATTRIBUTION.md`. Data Collection: Figshare Collection `5793482`, DOI: `10.6084/m9.figshare.c.5793482`, CC BY 4.0. The three tables here are computed from it by HelpChoreAI.
3. **Leukocyte & Reticulocyte Reference Data**:
   - Rosendahl, P., Plak, K., Jacobi, A., et al. (2018). *Real-time fluorescence and deformability cytometry*. **Nature Methods**, 15(5), 355–358. DOI: `10.1038/nmeth.4639`. DCOR package `figshare-7771184-v2` ("Real-time deformability cytometry reference data"), DOI: `10.6084/m9.figshare.7771184.v2`, CC0 1.0 (checked on DCOR and Figshare, 4 Nov 2026).
4. **Analytical Isoelastic Deformability Theory**:
   - Mietke, A., Otto, O., Girardo, S., Rosendahl, P., Taubenberger, A., Golfier, S., Ulbricht, E., & Guck, J. (2015). *Extracting cell stiffness from real-time deformability cytometry: theory and experiment*. **Biophysical Journal**, 109(10), 2023–2036. DOI: `10.1016/j.bpj.2015.09.006`.
5. **dclab software (source of two example files)**:
   - dclab, Python library for deformability cytometry data. GitHub: `DC-analysis/dclab`. Licence: GPL-2.0 for the repository unless a directory states otherwise.

---

## 5. Verification Protocol

To independently verify all datasets and cryptographic checksums in a clean terminal session:

```bash
python tools/fetch_csv_datasets.py
```

*Expected Terminal Result*:
```
========================================================
=== DATASET CHECKSUM AND ROW-COUNT CHECK ===
========================================================
All 18 datasets passed verification and integrity checks.
Successfully finished fetching and verifying all microfluidic datasets!
```
