"""Published open-weight claims must follow from the committed result files."""
import csv
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "data" / "tables"


def test_parity_is_complete():
    rows = list(csv.DictReader(open(T / "open_weight_parity.csv", encoding="utf-8")))
    assert len(rows) == 21
    assert all(r["equal"] == "True" and r["signature_ok"] == "True" for r in rows)


def test_reader_verdict_follows_the_frozen_rule():
    s = json.loads((T / "open_reader_summary.json").read_text(encoding="utf-8"))
    usable = s["within_patient_spearman"] >= 0.5 and s["calibrated_mae_points"] <= 8
    assert s["verdict"] == ("usable as triage reader" if usable else "not usable as a reader")
    assert len(pd.read_csv(T / "open_reader_cells.csv")) == s["cells_read"]


def test_claim_counts_follow_the_result_tables():
    s = json.loads((T / "claim_check_summary.json").read_text(encoding="utf-8"))
    for f, block in (("claim_check_results.csv", s), ("claim_check_hard.csv", s["hard"])):
        d = pd.read_csv(T / f)
        bad, fair = d[d.want == "BLOCK"], d[d.want == "PASS"]
        assert block["spark_open_stopped"] == (bad.spark_open == "BLOCK").sum()
        assert block["spark_open_passed_fair"] == (fair.spark_open == "PASS").sum()
        assert block["word_list_stopped"] == (bad.word_list == "BLOCK").sum()
