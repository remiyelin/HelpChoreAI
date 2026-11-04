#!/usr/bin/env python3
"""Statistical calibration module for HelpChoreAI and cross-domain RT-DC analysis.

Exposes Step 4b v3 core routines (fit_glm, eta, standardise, flow_adjust_runs, REF_FLOW, B, SEED)
and provides biophysical microfluidics calibration helpers for flow-rate confounder adjustment,
Spearman rank correlation, and deformation variance reduction analysis.
"""
from __future__ import annotations

import pathlib
from typing import Any, Tuple, Dict, List
import numpy as np
import pandas as pd
from scipy import stats as _sstats
import statsmodels.api as sm

# Re-export core constants and functions from step4b_model
import step4b_model as _s4b

REF_FLOW: float = _s4b.REF_FLOW
B: int = _s4b.B
SEED: int = _s4b.SEED
LABEL_ERR: float = _s4b.LABEL_ERR
EPS: float = _s4b.EPS
TREATMENT: Dict[str, str] = _s4b.TREATMENT

fit_glm = _s4b.fit_glm
eta = _s4b.eta
standardise = _s4b.standardise
flow_adjust_runs = _s4b.flow_adjust_runs


# ---------------------------------------------------------------------------
# Cross-Domain RT-DC Biomechanical Calibration Helpers
# ---------------------------------------------------------------------------

def compute_spearman(
    flow_rates: pd.Series | np.ndarray | list[float],
    deformations: pd.Series | np.ndarray | list[float]
) -> Tuple[float, float]:
    """Compute Spearman rank correlation (rho, p_value) between flow rate and deformation.

    Parameters:
        flow_rates: Array-like of microfluidic flow rates (e.g. in uL/s).
        deformations: Array-like of cell deformation values (dimensionless, 1 - circularity).

    Returns:
        tuple (rho, p_value)
    """
    res = _sstats.spearmanr(flow_rates, deformations)
    return float(res.statistic if hasattr(res, "statistic") else res[0]), float(res.pvalue if hasattr(res, "pvalue") else res[1])


def fit_rtdc_glm(
    runs: pd.DataFrame,
    flow_col: str = "FR",
    deform_col: str = "MedD",
    cluster_col: str = "Date",
    family: str = "gaussian"
) -> Dict[str, Any]:
    """Fit GLM on RT-DC run table with cluster intercepts +/- log(flow).

    Evaluates whether log(flow) improves AIC by > 2.0 (HelpChoreAI's Step 4b model selection rule).

    Parameters:
        runs: DataFrame containing RT-DC flow runs.
        flow_col: Column name for flow rate (default: 'FR').
        deform_col: Column name for cell deformation (default: 'MedD').
        cluster_col: Column name for biological replicate/cluster (default: 'Date').
        family: 'gaussian' (standard for continuous MedD) or 'binomial' (only for a real
            proportion of cells; a median deformation is not one, and rounding it
            into counts inflates the AIC).

    Returns:
        Dict with keys:
            - 'model': fitted statsmodels GLMResults
            - 'use_logflow': bool indicating whether Delta AIC > 2.0
            - 'aic_m0': AIC of cluster-only baseline model
            - 'aic_m1': AIC of cluster + log(flow) model
            - 'delta_aic': aic_m0 - aic_m1 (> 2.0 indicates flow confounder significance)
            - 'flow_slope': estimated coefficient for log(flow)
            - 'p_value': p-value of log(flow) coefficient
            - 'clusters': list of unique cluster identifiers
            - 'family': model family string
    """
    d = runs[runs[flow_col] > 0].copy()
    clusters = sorted(d[cluster_col].unique())
    X0 = np.column_stack([(d[cluster_col] == c).astype(float) for c in clusters])
    logflow = np.log(d[flow_col].to_numpy(dtype=float))
    X1 = np.column_stack([X0, logflow])

    if family.lower() == "gaussian":
        y = d[deform_col].to_numpy(dtype=float)
        m0 = sm.GLM(y, X0, family=sm.families.Gaussian()).fit()
        m1 = sm.GLM(y, X1, family=sm.families.Gaussian()).fit()
    elif family.lower() == "binomial":
        # Requires 'N' column for total counts
        if "N" not in d.columns:
            raise ValueError("Binomial GLM requires 'N' (cell count) column in runs DataFrame.")
        k = np.round(d[deform_col] * d["N"]).astype(int)
        nk = d["N"] - k
        endog = np.column_stack([k, nk])
        m0 = sm.GLM(endog, X0, family=sm.families.Binomial()).fit()
        m1 = sm.GLM(endog, X1, family=sm.families.Binomial()).fit()
    else:
        raise ValueError(f"Unsupported family: {family}. Use 'gaussian' or 'binomial'.")

    aic_m0 = float(m0.aic)
    aic_m1 = float(m1.aic)
    delta_aic = float(aic_m0 - aic_m1)
    use_logflow = bool(delta_aic > 2.0)
    selected_model = m1 if use_logflow else m0

    return {
        "model": selected_model,
        "use_logflow": use_logflow,
        "aic_m0": aic_m0,
        "aic_m1": aic_m1,
        "delta_aic": delta_aic,
        "flow_slope": float(m1.params[-1]),
        "p_value": float(m1.pvalues[-1]),
        "clusters": clusters,
        "family": family.lower()
    }


def standardise_rtdc(
    runs: pd.DataFrame,
    ref_flow: float = 0.08,
    flow_col: str = "FR",
    deform_col: str = "MedD",
    cluster_col: str = "Date",
    method: str = "linear"
) -> pd.DataFrame:
    """Standardise RT-DC cell deformation measurements to a constant reference flow rate.

    Neutralizes hydrodynamic shear stress variation across microfluidic measurement runs.

    Parameters:
        runs: DataFrame containing RT-DC runs with flow > 0.
        ref_flow: Reference flow rate (default: 0.08 uL/s).
        flow_col: Column name for flow rate.
        deform_col: Column name for measured cell deformation.
        cluster_col: Column name for biological cluster/replicate.
        method: 'linear' (Gaussian subtraction) or 'logit' (logit-scale shift like Step 4b).

    Returns:
        DataFrame copy with new column:
            'MedD_adj': flow-standardized deformation at ref_flow.
    """
    d = runs[runs[flow_col] > 0].copy()
    flow = d[flow_col].to_numpy(dtype=float)
    log_flow_diff = np.log(flow) - np.log(ref_flow)

    if method == "linear":
        fit = fit_rtdc_glm(d, flow_col=flow_col, deform_col=deform_col, cluster_col=cluster_col, family="gaussian")
        b = fit["flow_slope"]
        d["MedD_adj"] = d[deform_col] - b * log_flow_diff
    elif method == "logit":
        fit = fit_rtdc_glm(d, flow_col=flow_col, deform_col=deform_col, cluster_col=cluster_col, family="binomial")
        b = fit["flow_slope"]
        p_obs = d[deform_col].clip(EPS, 1 - EPS)
        logit_obs = np.log(p_obs / (1 - p_obs))
        logit_adj = logit_obs - b * log_flow_diff
        d["MedD_adj"] = 1.0 / (1.0 + np.exp(-logit_adj))
    else:
        raise ValueError(f"Unknown method: {method}. Choose 'linear' or 'logit'.")

    return d


def calculate_variance_reduction(
    runs: pd.DataFrame,
    ref_flow: float = 0.08,
    flow_col: str = "FR",
    deform_col: str = "MedD",
    cluster_col: str = "Date",
    condition_col: str = "LatB_conc",
    method: str = "linear"
) -> Dict[str, Any]:
    """Calculate variance in cell deformation before vs after flow standardisation.

    Computes overall variance reduction across all runs, as well as condition-specific
    within-treatment variance reduction.

    Returns:
        Dict with keys:
            - 'var_raw': unadjusted variance
            - 'var_adj': standardized variance
            - 'variance_reduction_pct': overall percentage variance reduced
            - 'std_raw': raw standard deviation
            - 'std_adj': standardized standard deviation
            - 'within_condition': dict mapping condition value to dict of
              {'var_raw', 'var_adj', 'reduction_pct'}
    """
    adj_df = standardise_rtdc(
        runs, ref_flow=ref_flow, flow_col=flow_col, deform_col=deform_col,
        cluster_col=cluster_col, method=method
    )
    var_raw = float(adj_df[deform_col].var())
    var_adj = float(adj_df["MedD_adj"].var())
    pct_reduction = float((1.0 - var_adj / var_raw) * 100.0)

    within_condition = {}
    if condition_col in adj_df.columns:
        for cond, sub in adj_df.groupby(condition_col):
            v_raw = float(sub[deform_col].var())
            v_adj = float(sub["MedD_adj"].var())
            red = float((1.0 - v_adj / v_raw) * 100.0) if v_raw > 0 else 0.0
            within_condition[cond] = {
                "n_runs": len(sub),
                "var_raw": v_raw,
                "var_adj": v_adj,
                "reduction_pct": red
            }

    return {
        "var_raw": var_raw,
        "var_adj": var_adj,
        "variance_reduction_pct": pct_reduction,
        "std_raw": float(np.sqrt(var_raw)),
        "std_adj": float(np.sqrt(var_adj)),
        "within_condition": within_condition
    }


def load_rtdc_runs(data_dir: pathlib.Path | str | None = None) -> pd.DataFrame:
    """Load and concatenate all authentic RT-DC multi-flow-rate run files."""
    if data_dir is None:
        root = pathlib.Path(__file__).resolve().parent.parent
        data_dir = root / "data" / "cross_domain"
    else:
        data_dir = pathlib.Path(data_dir)

    run_files = sorted(list(data_dir.glob("HL60_LatB_3fr_*.txt")))
    if not run_files:
        raise FileNotFoundError(f"No HL60_LatB_3fr_*.txt files found in {data_dir}")

    dfs = [pd.read_csv(f, sep=r"\s+") for f in run_files]
    all_runs = pd.concat(dfs, ignore_index=True)
    return all_runs
