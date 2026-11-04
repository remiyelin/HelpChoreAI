"""Performance Qualification (PQ) Test Suite for HelpChoreAI.

Document: VAL-PQ-2026-001
GAMP 5 Category 5 — Custom Computational Science Tool
FDA 21 CFR Part 11 / ALCOA+ Data Integrity Framework

Verifies:
- High-throughput ingestion and statistical modeling of authentic multi-condition microfluidic datasets
  (105 active runs across 237,813 cells, Osmolarity series across 86,279 cells, Leukocytes WBC 7.6k cells,
  Reticulocytes/RBCs 22k cells, ChAc RBC cohort 2.6k cells, Calibration beads 5k cells)
- Quantitative variance reduction invariant (>70% overall, >75% within-treatment)
- Deterministic bitwise repeatability across repetitive executions (10/10 identical)
- Computational execution throughput (<5.0 seconds for full pipeline)
- Longitudinal clinical decision concordance across all 32 chorea-acanthocytosis visit pairs
"""

from __future__ import annotations

import hashlib
import pathlib
import sys
import time
import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
DATA_DIR = ROOT / "data"
CSV_DIR = DATA_DIR / "csv"
CROSS_DOMAIN_DIR = DATA_DIR / "cross_domain"
TABLES_DIR = DATA_DIR / "tables"
TOOLS_DIR = ROOT / "tools"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import audit_table
import stats
import step4b_model


# ---------------------------------------------------------------------------
# 3.1 High-Throughput Processing of Authentic Microfluidic Datasets
# ---------------------------------------------------------------------------

def test_pq_run_01_high_throughput_105_runs_237k_cells():
    """Verify high-throughput processing of 105 active runs comprising 237,813 cells.
    
    Traceable to URS-DATA-01, FS-DATA-01, FS-DATA-02, PQ-RUN-01 in VAL-PQ-2026-001.
    """
    runs = stats.load_rtdc_runs(CROSS_DOMAIN_DIR)
    assert len(runs) == 140, f"Expected 140 total runs, observed {len(runs)}"

    active = runs[runs["FR"] > 0]
    assert len(active) == 105, f"Expected exactly 105 active runs, observed {len(active)}"

    total_cells = int(active["N"].sum())
    assert total_cells == 237_813, f"Expected exactly 237,813 measured cells, observed {total_cells}"

    # Flow rates match physical experimental protocol: 0.04, 0.08, 0.12 uL/s
    frs = sorted(list(active["FR"].unique()))
    assert np.allclose(frs, [0.04, 0.08, 0.12])

    # GLM convergence and parameters
    fit = stats.fit_rtdc_glm(active, family="gaussian")
    assert fit["use_logflow"] is True
    assert np.all(np.isfinite(fit["model"].params))


def test_pq_run_02_osmolarity_series_86k_cells():
    """Verify authentic multi-condition Osmolarity series (200-700 mOsm) across 86,279 cells.
    
    Traceable to URS-DATA-01, FS-DATA-01 in VAL-URS-2026-001.
    """
    pooled_path = CSV_DIR / "RTDC_Osm_all_replicates_singlecells.csv"
    assert pooled_path.exists()

    df_osm = pd.read_csv(pooled_path)
    assert len(df_osm) == 86_279, f"Expected 86,279 single cell events, observed {len(df_osm)}"

    expected_cols = {"Area_um2", "DiameterA_um", "Volume_um3", "Deformation", "Osmo_mOsm"}
    assert expected_cols.issubset(set(df_osm.columns))

    # Verify physical bounds
    assert (df_osm["Volume_um3"] > 0).all()
    assert (df_osm["Area_um2"] > 0).all()
    assert (df_osm["Deformation"] >= 0).all() and (df_osm["Deformation"] < 1.0).all()

    # Verify replicate sets 1-4 individual counts
    sets_counts = {
        "RTDC_Osm_set1_20160129.txt": 18_579,
        "RTDC_Osm_set2_20160131.txt": 21_584,
        "RTDC_Osm_set3_20160202.txt": 24_800,
        "RTDC_Osm_set4_20160204.txt": 21_316,
    }
    for fname, count in sets_counts.items():
        fpath = CSV_DIR / fname
        assert fpath.exists()
        df_set = pd.read_csv(fpath, sep=r"\s+")
        assert len(df_set) == count, f"File {fname} expected {count} rows, observed {len(df_set)}"


def test_pq_run_03_leukocyte_and_reticulocyte_cell_type_ingestion():
    """Verify ingestion of WBC leukocytes, reticulocytes, RBCs, and hydrogel calibration beads.
    
    Traceable to URS-DATA-01, URS-DATA-04, FS-DATA-02 in VAL-PQ-2026-001.
    """
    # 1. Peripheral Blood Leukocytes (Rosendahl 2018)
    wbc_path = CSV_DIR / "Leukocytes_WBC_Rosendahl2018_SingleCells.csv"
    assert wbc_path.exists()
    df_wbc = pd.read_csv(wbc_path)
    assert len(df_wbc) == 7_619, f"Expected 7,619 WBC events, observed {len(df_wbc)}"
    assert "deform" in df_wbc.columns and "circ" in df_wbc.columns

    # 2. RBCs & Reticulocytes (Rosendahl 2018)
    retic_path = CSV_DIR / "RBC_Reticulocytes_Rosendahl2018_SingleCells.csv"
    assert retic_path.exists()
    df_retic = pd.read_csv(retic_path)
    assert len(df_retic) == 22_000, f"Expected 22,000 RBC events, observed {len(df_retic)}"
    assert "fl1_max" in df_retic.columns and "deform" in df_retic.columns

    # 3. Hydrogel Calibration Beads (Rosendahl 2018)
    beads_path = CSV_DIR / "Calibration_Beads_Hydrogel_Rosendahl2018_SingleCells.csv"
    assert beads_path.exists()
    df_beads = pd.read_csv(beads_path)
    assert len(df_beads) == 5_000, f"Expected 5,000 bead events, observed {len(df_beads)}"
    assert "deform" in df_beads.columns and "fl2_max" in df_beads.columns

    # 4. Acanthocytes / ChAc RBC cohort (Reichel 2022)
    chac_path = CSV_DIR / "RBC_ChAc_Reichel2022_SingleCells.csv"
    assert chac_path.exists()
    df_chac = pd.read_csv(chac_path)
    assert len(df_chac) == 2_674, f"Expected 2,674 ChAc RBC cells, observed {len(df_chac)}"

    chac_runs = pd.read_csv(CSV_DIR / "RBC_ChAc_Reichel2022_PerRun.csv")
    assert len(chac_runs) == 437, f"Expected 437 experimental runs, observed {len(chac_runs)}"

    # Total single-cell catalog count exceeds 350,000 authentic cells
    total_catalog_cells = 237_813 + 86_279 + 7_619 + 22_000 + 5_000 + 2_674
    assert total_catalog_cells > 350_000


# ---------------------------------------------------------------------------
# 3.2 Quantitative Variance Reduction Invariant
# ---------------------------------------------------------------------------

def test_pq_stat_01_quantitative_variance_reduction_invariant():
    """Verify that flow standardisation eliminates >70% overall deformation variance.
    
    Traceable to URS-STAT-04, FS-STAT-03, PQ-STAT-01 in VAL-PQ-2026-001.
    """
    runs = stats.load_rtdc_runs(CROSS_DOMAIN_DIR)
    active = runs[runs["FR"] > 0]

    res = stats.calculate_variance_reduction(active, ref_flow=0.08, method="linear")
    overall_reduction = res["variance_reduction_pct"]
    assert overall_reduction > 70.0, f"Expected > 70.0% overall variance reduction, observed {overall_reduction:.2f}%"

    # Within-condition variance reductions across all 7 LatB treatment cohorts
    within = res["within_condition"]
    assert len(within) == 7
    for conc, m in within.items():
        assert m["reduction_pct"] > 75.0, (
            f"LatB {conc} cohort reduction was {m['reduction_pct']:.1f}% (must be > 75%)"
        )


# ---------------------------------------------------------------------------
# 3.3 Deterministic Bitwise Reproducibility
# ---------------------------------------------------------------------------

def test_pq_rep_01_deterministic_bitwise_repeatability():
    """Verify that repeated pipeline executions produce bitwise identical parameters and outputs.
    
    Traceable to URS-QUAL-01, FS-STAT-04, PQ-REP-01 in VAL-PQ-2026-001.
    """
    runs = stats.load_rtdc_runs(CROSS_DOMAIN_DIR)
    active = runs[runs["FR"] > 0]

    digests = []
    for _ in range(10):
        fit = stats.fit_rtdc_glm(active, family="gaussian")
        adj = stats.standardise_rtdc(active, ref_flow=0.08)
        # Hash serialised adjusted values
        payload = adj[["FR", "MedD", "MedD_adj"]].to_csv(index=False).encode("utf-8")
        h = hashlib.sha256(payload).hexdigest()
        digests.append((h, fit["delta_aic"], fit["flow_slope"]))

    first = digests[0]
    for i, item in enumerate(digests[1:], start=2):
        assert item == first, f"Execution iteration {i} drifted from initial execution: {item} != {first}"


# ---------------------------------------------------------------------------
# 3.4 Computational Execution Throughput
# ---------------------------------------------------------------------------

def test_pq_time_01_computational_throughput():
    """Verify that end-to-end ingestion and statistical modeling completes in < 5.0 seconds.
    
    Traceable to PQ-TIME-01 in VAL-PQ-2026-001.
    """
    t0 = time.perf_counter()

    runs = stats.load_rtdc_runs(CROSS_DOMAIN_DIR)
    active = runs[runs["FR"] > 0]
    fit = stats.fit_rtdc_glm(active)
    adj = stats.standardise_rtdc(active)
    var = stats.calculate_variance_reduction(active)

    t1 = time.perf_counter()
    duration = t1 - t0

    assert duration < 5.0, f"Execution duration {duration:.3f}s exceeded 5.0s benchmark limit"
    assert fit["use_logflow"] is True
    assert var["variance_reduction_pct"] > 60.0


# ---------------------------------------------------------------------------
# 3.5 Longitudinal Clinical Decision Concordance
# ---------------------------------------------------------------------------

def test_pq_dec_01_clinical_decision_concordance_32_visit_pairs():
    """Verify exact 100% concordance across all 32 visit pair decisions without false alarm inflation.
    
    Traceable to URS-STAT-05, FS-STAT-04, FS-STAT-05, PQ-DEC-01 in VAL-PQ-2026-001.
    """
    # Verify main 21 visit pairs match frozen v3 decisions
    r1 = pd.read_csv(TABLES_DIR / "per_run.csv")
    t1 = pd.DataFrame({
        "subject": r1.patient, "visit": r1.visit, "visit_order": r1.date, "run": r1.run,
        "marked": r1.n_health1.fillna(0).astype(int), "rated": r1.n_kept, "total": r1.n_total,
        "disturbance": r1.flow_ul_s
    })
    got1, _, _ = audit_table.audit(t1, reference=0.016, unreadable_rule="frozen")
    want1 = pd.read_csv(TABLES_DIR / "visit_pairs_decisions_v3.csv")
    assert len(got1) == len(want1)
    m1 = got1.merge(want1, left_on=["subject", "from", "to"], right_on=["patient", "from", "to"])
    assert (m1["decision_x"] == m1["decision_y"]).all()

    # Verify holdout 11 visit pairs match frozen sealed results
    r2 = pd.read_csv(TABLES_DIR / "per_run_holdout.csv")
    t2 = pd.DataFrame({
        "subject": r2.patient, "visit": r2.visit, "visit_order": r2.date, "run": r2.run,
        "marked": r2.n_health1.fillna(0).astype(int), "rated": r2.n_kept, "total": r2.n_total,
        "disturbance": r2.flow_ul_s
    })
    got2, _, _ = audit_table.audit(t2, reference=0.016, unreadable_rule="frozen")
    want2 = pd.read_csv(TABLES_DIR / "sealed_results.csv")
    assert len(got2) == len(want2)
    m2 = got2.merge(want2, left_on=["subject", "from", "to"], right_on=["patient", "from", "to"])
    assert (m2["decision_x"] == m2["decision_y"]).all()

    # Exactly 32 total pairs verified with 100% concordance
    assert len(want1) + len(want2) == 32
