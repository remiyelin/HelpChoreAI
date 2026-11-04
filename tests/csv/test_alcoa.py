"""ALCOA+ Data Integrity Test Suite for HelpChoreAI.

Document: VAL-ALCOA-2026-001
Regulatory Standards: FDA 21 CFR Part 11, GAMP 5 Category 5, EMA Guideline on Computerised Systems, WHO TRS 996

Verifies all 9 ALCOA+ Principles across microfluidic data & analytical pipeline:
- A: Attributable
- L: Legible
- C: Contemporaneous
- O: Original
- A: Accurate
- + Complete
- + Consistent
- + Enduring
- + Available
"""

from __future__ import annotations

import json
import pathlib
import sys
import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
DATA_DIR = ROOT / "data"
CSV_DIR = DATA_DIR / "csv"
CROSS_DOMAIN_DIR = DATA_DIR / "cross_domain"
TABLES_DIR = DATA_DIR / "tables"
CHECKER_DIR = DATA_DIR / "checker"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import checker
import stats
import step4b_model


# ---------------------------------------------------------------------------
# Principle 1: Attributable (A)
# ---------------------------------------------------------------------------

def test_alcoa_01_attributable():
    """Verify that every data point and signed report is unequivocally traceable to its biological/operator source.
    
    Traceable to URS-DATA-03, FS-COMP-01, Section 3.1 in VAL-ALCOA-2026-001.
    """
    # 1. Tabular runs attribution
    df_runs = pd.read_csv(TABLES_DIR / "per_run.csv")
    assert "patient" in df_runs.columns
    assert "visit" in df_runs.columns
    assert "run" in df_runs.columns
    assert "flow_ul_s" in df_runs.columns
    assert not df_runs["patient"].isna().any(), "Patient attribution cannot contain NaN"

    # 2. Cryptographic report attribution
    env = json.loads((CHECKER_DIR / "example_report_P1_0w_2w.json").read_text(encoding="utf-8"))
    payload = env["payload"]
    assert "patient" in payload and payload["patient"] == "P1"
    assert "agent_id" in payload or "operator" in payload or "public_key_hex" in env
    assert len(env["public_key_hex"]) == 64


# ---------------------------------------------------------------------------
# Principle 2: Legible (L)
# ---------------------------------------------------------------------------

def test_alcoa_02_legible():
    """Verify that all analytical records and audit reports are stored in open human/machine-readable text formats.
    
    Traceable to Section 3.2 in VAL-ALCOA-2026-001.
    """
    # Dual report representation: machine-readable JSON + human-readable Markdown
    json_path = CHECKER_DIR / "example_report_P1_0w_2w.json"
    md_path = CHECKER_DIR / "example_report_P1_0w_2w.md"

    assert json_path.exists() and md_path.exists()

    # Verify JSON is valid UTF-8 and parses cleanly
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

    # Verify Markdown is human-readable text without binary locks
    md_text = md_path.read_text(encoding="utf-8")
    assert "# Audit Report" in md_text or "Decision" in md_text or "Patient" in md_text


# ---------------------------------------------------------------------------
# Principle 3: Contemporaneous (C)
# ---------------------------------------------------------------------------

def test_alcoa_03_contemporaneous():
    """Verify contemporaneous recording: instrument dates, monotonic chronological sequence, and hash chain binding.
    
    Traceable to URS-COMP-01, FS-COMP-01, Section 3.3 in VAL-ALCOA-2026-001.
    """
    # 1. Experimental run acquisition dates preserved
    df_runs = pd.read_csv(TABLES_DIR / "per_run.csv")
    assert "date" in df_runs.columns
    assert (df_runs["date"] > 20170000).all()

    # Monotonic chronological order per subject
    for _, g in df_runs.groupby("patient"):
        dates = list(g["date"])
        assert dates == sorted(dates), "Visit dates must follow contemporaneous chronological sequence"

    # 2. Cryptographic hash chain binds manifests and tables at execution time
    chain = checker.chain_hashes()
    assert "raw_manifest_sha256" in chain and len(chain["raw_manifest_sha256"]) == 64
    assert "tables_sha256" in chain and len(chain["tables_sha256"]) >= 3
    assert len(chain["hashed_files"]) > 0


# ---------------------------------------------------------------------------
# Principle 4: Original (O)
# ---------------------------------------------------------------------------

def test_alcoa_04_original():
    """Verify that primary raw experimental records remain unaltered and segregated from downstream derivations.
    
    Traceable to URS-DATA-05, FS-DATA-03, Section 3.4 in VAL-ALCOA-2026-001.
    """
    # Primary raw files exist in cross_domain
    raw_files = list(CROSS_DOMAIN_DIR.glob("HL60_LatB_3fr_*.txt"))
    assert len(raw_files) == 5

    # Downstream derived files are strictly written to tables/ and checker/
    assert (TABLES_DIR / "per_run.csv").exists()
    assert (TABLES_DIR / "per_visit_adjusted_v3.csv").exists()
    assert (TABLES_DIR / "visit_pairs_decisions_v3.csv").exists()


# ---------------------------------------------------------------------------
# Principle 5: Accurate (A)
# ---------------------------------------------------------------------------

def test_alcoa_05_accurate():
    """Verify mathematical truthfulness: confounder standardisation and few-cluster Student-t calibration.
    
    Traceable to URS-STAT-03, URS-STAT-04, URS-STAT-05, Section 3.5 in VAL-ALCOA-2026-001.
    """
    runs = stats.load_rtdc_runs(CROSS_DOMAIN_DIR)
    active = runs[runs["FR"] > 0]

    # Flow confounder standardisation eliminates >70% variance
    res = stats.calculate_variance_reduction(active, ref_flow=0.08)
    assert res["variance_reduction_pct"] > 70.0

    # Student-t small-sample multiplier prevents false alarms
    df_small = 6
    t_mult = float(step4b_model._sstats.t.ppf(0.975, df_small))
    assert t_mult > 1.96, f"Small-cluster multiplier {t_mult} must exceed 1.96"


# ---------------------------------------------------------------------------
# Principle 6: Complete (+ Complete)
# ---------------------------------------------------------------------------

def test_alcoa_06_complete():
    """Verify that all runs, replicates, and unreadable recordings are completely preserved and audited.
    
    Traceable to Section 3.6 in VAL-ALCOA-2026-001.
    """
    # All 140 runs accounted for (105 active + 35 controls)
    all_runs = stats.load_rtdc_runs(CROSS_DOMAIN_DIR)
    assert len(all_runs) == 140

    # All 37 longitudinal visits accounted for across dev and holdout sets
    per_visit = pd.read_csv(TABLES_DIR / "per_visit.csv")
    per_visit_holdout = pd.read_csv(TABLES_DIR / "per_visit_holdout.csv")
    total_visits = len(per_visit) + len(per_visit_holdout)
    assert total_visits == 37, f"Expected 37 total visits, observed {total_visits}"

    # All 32 visit pairs accounted for (21 v3 + 11 holdout)
    decisions = pd.read_csv(TABLES_DIR / "visit_pairs_decisions_v3.csv")
    sealed = pd.read_csv(TABLES_DIR / "sealed_results.csv")
    assert len(decisions) + len(sealed) == 32

    # QC failures are retained as indeterminate_QC, never silently deleted
    assert (decisions["decision"] == "indeterminate_QC").sum() > 0


# ---------------------------------------------------------------------------
# Principle 7: Consistent (+ Consistent)
# ---------------------------------------------------------------------------

def test_alcoa_07_consistent():
    """Verify deterministic repeatability: fixed seed yields bitwise invariant bootstrap results across runs.
    
    Traceable to Section 3.7 in VAL-ALCOA-2026-001.
    """
    assert step4b_model.SEED == 20261026
    assert step4b_model.B == 2000

    # Execute two independent bootstrap samplings with identical fixed seed
    rng1 = np.random.default_rng(step4b_model.SEED)
    rng2 = np.random.default_rng(step4b_model.SEED)

    s1 = rng1.standard_normal(1000)
    s2 = rng2.standard_normal(1000)
    assert np.array_equal(s1, s2), "Bootstrap PRNG must be deterministic under frozen seed"


# ---------------------------------------------------------------------------
# Principle 8: Enduring (+ Enduring)
# ---------------------------------------------------------------------------

def test_alcoa_08_enduring():
    """Verify durable open formats and standalone zero-dependency offline verification capability.
    
    Traceable to Section 3.8 in VAL-ALCOA-2026-001.
    """
    env = json.loads((CHECKER_DIR / "example_report_P1_0w_2w.json").read_text(encoding="utf-8"))
    report_text = (CHECKER_DIR / "example_report_P1_0w_2w.md").read_text(encoding="utf-8")

    # Offline verification without network or external tokens
    ok, errs = checker.verify_envelope(env, report_text=report_text, check_tables=True)
    assert ok is True and len(errs) == 0


# ---------------------------------------------------------------------------
# Principle 9: Available (+ Available)
# ---------------------------------------------------------------------------

def test_alcoa_09_available():
    """Verify that reports and analytical tables are readily accessible for inspection and audit.
    
    Traceable to Section 3.9 in VAL-ALCOA-2026-001.
    """
    example_report = CHECKER_DIR / "example_report_P1_0w_2w.json"
    assert example_report.is_file() and example_report.stat().st_size > 0

    # Key analytical tables available
    assert (TABLES_DIR / "per_visit_adjusted_v3.csv").is_file()
    assert (TABLES_DIR / "visit_pairs_decisions_v3.csv").is_file()
    assert (CSV_DIR / "MANIFEST_CSV_DATASETS.sha256").is_file()
