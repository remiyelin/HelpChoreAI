"""Step 6 durable tests: kappa/AC1 math + real contour availability. Run: uv run pytest tests/ -q"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import server

def test_kappa_perfect_agreement():
    r = server.kappa_ac1([0, 1, 1, 0, 1], [0, 1, 1, 0, 1])
    assert r["n"] == 5 and r["kappa"] == 1.0 and r["ac1"] == 1.0 and r["agreement"] == 1.0

def test_kappa_empty_is_null_not_fake():
    r = server.kappa_ac1([], [])
    assert r["n"] == 0 and r["kappa"] is None

def test_real_contour_loads_for_known_cell():
    c = server.cell_contour("P1", "20170627", 0)
    assert c is not None and len(c["points"]) >= 3 and c["n_frames"] > 0

def test_real_frame_png_for_sample_cell():
    got = server.frame_png("P1", "20170627", 4, crop=True)
    assert got is not None
    png, info = got
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and info["frame"] > 0 and len(info["contour_crop"]) >= 3

def test_longitudinal_qc_flag_present():
    import pandas as pd
    v = pd.read_csv(server.TABLES / "per_visit_adjusted_v2.csv")
    assert "var" in v.columns and (v.skip_rate > 0.25).any()

def test_live_status_never_claims_live_without_keys(monkeypatch):
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    s = server.live_status()
    assert s["sam_3_1"].startswith("OFFLINE") and s["open_weight_auditor"].startswith("OFFLINE")
