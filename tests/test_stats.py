"""Durable Step 4b invariants. Run: uv run pytest tests/ -q"""
import pathlib
import pandas as pd

T = pathlib.Path(__file__).parent.parent / "data" / "tables"

def test_decisions_v2_shape_and_counts():
    d = pd.read_csv(T / "visit_pairs_decisions_v2.csv")
    assert len(d) == 21
    assert set(d.decision) <= {"exceeds_RCV", "within_RCV", "indeterminate_QC"}
    assert set(d.patient) == {"P1", "P2", "P4"}
    assert d.treatment.str.contains("dasatinib|lithium").all()

def test_adjusted_visits_cover_all_pairs():
    v = pd.read_csv(T / "per_visit_adjusted_v2.csv")
    assert len(v) == 24
    assert v.frac_adj.between(0, 1).all()
    assert (v.n_kept > 0).all()
