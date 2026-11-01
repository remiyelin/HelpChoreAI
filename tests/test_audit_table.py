"""The general table tool must equal the frozen pipeline on the real tables and find what was planted in the synthetic one."""
import subprocess
import sys
from pathlib import Path
import pandas as pd
import pytest
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import audit_table as tool

T = ROOT / "data" / "tables"
EXAMPLE = ROOT / "examples" / "synthetic_other_lab.csv"


def real_table(name):
    r = pd.read_csv(T / name)
    return pd.DataFrame({"subject": r.patient, "visit": r.visit, "visit_order": r.date, "run": r.run, "marked": r.n_health1.fillna(0).astype(int),
                         "rated": r.n_kept, "total": r.n_total, "disturbance": r.flow_ul_s})


@pytest.mark.parametrize("runs,frozen", [("per_run.csv", "visit_pairs_decisions_v3.csv"), ("per_run_holdout.csv", "sealed_results.csv")])
def test_equals_the_frozen_results(runs, frozen):
    got, _v, info = tool.audit(real_table(runs), reference=0.016, unreadable_rule="frozen")
    want = pd.read_csv(T / frozen)
    assert len(got) == len(want)
    m = got.merge(want, left_on=["subject", "from", "to"], right_on=["patient", "from", "to"])
    assert len(m) == len(want)
    assert (m.corrected_change - m.delta_adj).abs().max() < 1e-9
    assert (m.wobble - m.RCV95).abs().max() < 1e-9
    assert (m.normal_change - m.delta_raw).abs().max() < 1e-9
    assert (m.decision_x == m.decision_y).all()
    assert info["corrected"] and abs(info["slope"] + 0.322) < 0.001


def test_finds_what_was_planted():
    pairs, _v, info = tool.audit(tool.load(EXAMPLE))
    d = {(r.subject, r.to): r.decision for r in pairs.rename(columns={"from": "frm"}).itertuples()}
    assert d[("S1", "visit3")] == "exceeds_RCV"            # planted real rise
    assert d[("S2", "visit3")] == "within_RCV"             # planted false alarm from a long wait
    assert d[("S2", "visit4")] == d[("S2", "visit5")] == "indeterminate_QC"  # planted bad recording
    alarm = pairs[(pairs.subject == "S2") & (pairs.to == "visit3")].iloc[0]
    assert alarm.normal_says == "alarm"
    quiet = pairs[~pairs.to.isin(["visit3", "visit4", "visit5"]) | (pairs.subject == "S1")]
    assert (quiet[quiet.to != "visit3"].decision == "within_RCV").all()
    assert info["corrected"] and -0.45 < info["slope"] < -0.2


def test_no_recorded_disturbance_means_no_correction():
    df = tool.load(EXAMPLE).assign(disturbance=1)
    _p, _v, info = tool.audit(df)
    assert info["corrected"] is False and info["slope"] is None


@pytest.mark.parametrize("change,message", [
    (lambda d: d.drop(columns=["rated"]), "missing columns"),
    (lambda d: d.assign(disturbance=0), "disturbance must be above 0"),
    (lambda d: d.assign(marked=d.rated + 1), "marked <= rated"),
    (lambda d: pd.concat([d, d.iloc[[0]]]), "appears twice"),
    (lambda d: d.assign(subject="Jane Doe"), "never a name"),
    (lambda d: d.assign(visit="same"), "same subject, visit and run"),
])
def test_bad_tables_get_a_clear_message(tmp_path, change, message):
    p = tmp_path / "t.csv"
    change(pd.read_csv(EXAMPLE)).to_csv(p, index=False)
    with pytest.raises(tool.TableError, match=message):
        tool.load(p)


def test_command_line_runs_on_the_example(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "audit_table.py"), str(EXAMPLE), "--out", str(tmp_path)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "Research use only" in r.stdout and (tmp_path / "decisions.csv").exists() and (tmp_path / "summary.json").exists()
