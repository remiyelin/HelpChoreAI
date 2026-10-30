"""Stats v3 durable tests: unpenalised GLM sanity + simulation-validated null rate."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import step4b_model

ROOT = Path(__file__).resolve().parent.parent


def test_glm_coefficients_finite_and_flow_slope_negative():
    runs = pd.read_csv(ROOT / "data" / "tables" / "per_run.csv").dropna(subset=["frac_health1"])
    model, patients, use_logflow, (aic0, aic1) = step4b_model.fit_glm(runs)
    assert np.all(np.isfinite(model.params)), "GLM coefficients must be finite"
    assert use_logflow and aic1 < aic0 - 2, "log(flow) must earn its place by AIC > 2"
    assert float(model.params[-1]) < 0, "flow slope must be negative (higher flow -> fewer healthy)"


def test_logit_standardisation_moves_toward_reference():
    # A run observed above the patient mean at very high flow must shift DOWN toward
    # the reference-flow prediction under a negative flow slope (direction check).
    runs = pd.read_csv(ROOT / "data" / "tables" / "per_run.csv").dropna(subset=["frac_health1"])
    model, patients, use_logflow, _ = step4b_model.fit_glm(runs)
    hi = runs.sort_values("flow_ul_s").iloc[[-1]].copy()
    adj = step4b_model.standardise(hi, model, patients, use_logflow)
    eta_ref = step4b_model.eta(model, patients, use_logflow, step4b_model.REF_FLOW, hi.iloc[0].patient)
    eta_run = step4b_model.eta(model, patients, use_logflow, float(hi.iloc[0].flow_ul_s), hi.iloc[0].patient)
    assert eta_ref > eta_run  # negative slope: lower flow -> higher log-odds
    assert np.isfinite(adj.frac_adj.iloc[0]) and 0 < adj.frac_adj.iloc[0] < 1


def test_final_rule_null_false_exceed_rate():
    sim = json.loads((ROOT / "data" / "tables" / "simulation_rcv.json").read_text())
    rate = sim["null_false_exceed_rate"]["bootstrap_flowadj"]
    assert rate <= 0.07, f"final rule null false-exceed rate {rate} exceeds the 0.07 bar"
    assert rate < sim["null_false_exceed_rate"]["naive_binomial"] / 3
