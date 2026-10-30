"""SAM tracking durable tests (no network): clip grouping/billing, record keying, budget math."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sam_tracking import group_clips, index_records
import pandas as pd


def _cells(rows):
    return pd.DataFrame(rows, columns=["patient", "date", "cell", "health", "f0", "f1", "track_len", "score", "visit"])


def test_group_clips_merges_overlaps_and_bills_min_50():
    cells = _cells([
        ["P1", "20170627", 1, 0, 100, 200, 101, 101, "0w"],
        ["P1", "20170627", 2, 1, 150, 260, 111, 111, "0w"],   # overlaps cell 1 -> same clip
        ["P1", "20170627", 3, 1, 5000, 5040, 41, 43, "0w"],   # separate, <50 frames -> billed 50
        ["P2", "20170711", 4, 0, 10, 60, 51, 51, "0w"],
    ])
    clips = group_clips(cells)
    assert len(clips) == 3
    merged = [c for c in clips if len(c["cells"]) == 2][0]
    assert merged["start"] == 95 and merged["end"] == 260 and merged["billed"] == 166
    assert min(c["billed"] for c in clips) == 50
    assert sum(c["billed"] for c in clips) == 166 + 50 + 56


def test_position_gate_catches_synthetic_drift_not_steady_track():
    import numpy as np
    rows = []
    for i in range(100):  # steady track: sub-pixel jitter only
        rows.append({"patient": "P1", "date": "20170627", "cell": 1, "author_health": 0,
                     "centroid_dist_px": 0.5 + (i % 3) * 0.2})
    for i in range(100):  # drifting (identity-lag) track: distance grows ~3 px/frame
        rows.append({"patient": "P1", "date": "20170627", "cell": 2, "author_health": 1,
                     "centroid_dist_px": float(3 * i)})
    for i in range(100):  # mostly good, brief 5-frame excursion (5% <= 10% tolerance)
        rows.append({"patient": "P1", "date": "20170627", "cell": 3, "author_health": 0,
                     "centroid_dist_px": 40.0 if 50 <= i < 55 else 0.4})
    from sam_tracking import position_gate
    g = position_gate(__import__("pandas").DataFrame(rows)).set_index("cell")
    assert bool(g.loc[2, "track_flagged"]) and g.loc[2, "frac_frames_over_thresh"] > 0.9
    assert not bool(g.loc[1, "track_flagged"]) and not bool(g.loc[3, "track_flagged"])


def test_index_records_keys_by_frame_and_id():
    recs = [{"frame": 3, "object_id": "2", "rows": []}, {"frame": 1, "object_id": "1", "rows": []},
            {"frame": 3, "object_id": "1", "rows": []}]
    idx = index_records(recs)
    assert set(idx) == {(3, "2"), (1, "1"), (3, "1")} and len(idx) == 3  # out-of-order safe
