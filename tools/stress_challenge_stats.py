#!/usr/bin/env python3
"""Empirical Challenger stress-testing harness for src/stats.py.

Executes 4 comprehensive empirical challenges:
1. Permutation Test (Null Hypothesis Collapse)
2. Per-Replicate Stability (All 5 Dates)
3. Variance Reduction Invariance (Across Reference Flow Rates)
4. Numerical Boundaries & Defensive Robustness
"""
import sys
import pathlib
import json
import numpy as np
import pandas as pd

# Add src to sys.path
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import stats

DATA_DIR = ROOT / "data" / "cross_domain"


def run_permutation_tests(active_runs: pd.DataFrame, n_perms: int = 1000, seed: int = 42):
    print("=" * 80)
    print(f"CHALLENGE 1: PERMUTATION TEST (NULL HYPOTHESIS COLLAPSE, N={n_perms})")
    print("=" * 80)
    rng = np.random.default_rng(seed)

    # Real observed values
    real_fit_gauss = stats.fit_rtdc_glm(active_runs, family="gaussian")
    real_fit_binom = stats.fit_rtdc_glm(active_runs, family="binomial")
    real_spearman_rho, real_spearman_p = stats.compute_spearman(active_runs["FR"], active_runs["MedD"])

    print(f"Real Observed (Gaussian GLM): Delta AIC = {real_fit_gauss['delta_aic']:.4f}, slope b = {real_fit_gauss['flow_slope']:.6f}, p = {real_fit_gauss['p_value']:.2e}")
    print(f"Real Observed (Binomial GLM): Delta AIC = {real_fit_binom['delta_aic']:.4f}, slope b = {real_fit_binom['flow_slope']:.6f}, p = {real_fit_binom['p_value']:.2e}")
    print(f"Real Observed (Spearman):     rho = {real_spearman_rho:.4f}, p = {real_spearman_p:.2e}")
    print("-" * 80)

    # Global permutation (shuffling FR across all 105 runs)
    null_delta_aic_gauss = []
    null_slopes_gauss = []
    null_pvals_gauss = []
    null_delta_aic_binom = []
    null_slopes_binom = []
    null_rhos = []

    for i in range(n_perms):
        shuffled = active_runs.copy()
        shuffled["FR"] = rng.permutation(shuffled["FR"].to_numpy())

        # Fit Gaussian GLM
        fit_g = stats.fit_rtdc_glm(shuffled, family="gaussian")
        null_delta_aic_gauss.append(fit_g["delta_aic"])
        null_slopes_gauss.append(fit_g["flow_slope"])
        null_pvals_gauss.append(fit_g["p_value"])

        # Fit Binomial GLM
        fit_b = stats.fit_rtdc_glm(shuffled, family="binomial")
        null_delta_aic_binom.append(fit_b["delta_aic"])
        null_slopes_binom.append(fit_b["flow_slope"])

        # Spearman
        rho, _ = stats.compute_spearman(shuffled["FR"], shuffled["MedD"])
        null_rhos.append(rho)

    null_delta_aic_gauss = np.array(null_delta_aic_gauss)
    null_slopes_gauss = np.array(null_slopes_gauss)
    null_pvals_gauss = np.array(null_pvals_gauss)
    null_delta_aic_binom = np.array(null_delta_aic_binom)
    null_rhos = np.array(null_rhos)

    print("--- Global Permutation Results (Across All Runs) ---")
    print(f"Gaussian Null Delta AIC: mean = {null_delta_aic_gauss.mean():.4f}, median = {np.median(null_delta_aic_gauss):.4f}, max = {null_delta_aic_gauss.max():.4f}")
    fp_gauss = np.mean(null_delta_aic_gauss > 2.0)
    print(f"Gaussian Null False Positive Rate (Delta AIC > 2.0): {fp_gauss * 100:.2f}% ({np.sum(null_delta_aic_gauss > 2.0)} / {n_perms})")
    p_emp_gauss = np.mean(null_delta_aic_gauss >= real_fit_gauss["delta_aic"])
    print(f"Gaussian Empirical p-value: p_emp < {1.0 / n_perms:.4f} (actual count >= real: {np.sum(null_delta_aic_gauss >= real_fit_gauss['delta_aic'])})")
    print(f"Gaussian Null Slope b: mean = {null_slopes_gauss.mean():.6f}, std = {null_slopes_gauss.std():.6f}, 95% range = [{np.percentile(null_slopes_gauss, 2.5):.6f}, {np.percentile(null_slopes_gauss, 97.5):.6f}] vs Real b = {real_fit_gauss['flow_slope']:.6f}")

    print(f"Binomial Null Delta AIC: mean = {null_delta_aic_binom.mean():.4f}, median = {np.median(null_delta_aic_binom):.4f}, max = {null_delta_aic_binom.max():.4f}")
    fp_binom = np.mean(null_delta_aic_binom > 2.0)
    print(f"Binomial Null False Positive Rate (Delta AIC > 2.0): {fp_binom * 100:.2f}% ({np.sum(null_delta_aic_binom > 2.0)} / {n_perms})")
    p_emp_binom = np.mean(null_delta_aic_binom >= real_fit_binom["delta_aic"])
    print(f"Binomial Empirical p-value: p_emp < {1.0 / n_perms:.4f} (actual count >= real: {np.sum(null_delta_aic_binom >= real_fit_binom['delta_aic'])})")

    print(f"Spearman Null rho: mean = {null_rhos.mean():.4f}, std = {null_rhos.std():.4f}, max = {null_rhos.max():.4f} vs Real rho = {real_spearman_rho:.4f}")

    # Stratified permutation (shuffling within each date)
    strat_delta_aic_gauss = []
    strat_slopes_gauss = []
    for i in range(n_perms):
        shuffled = active_runs.copy()
        shuffled["FR"] = shuffled.groupby("Date")["FR"].transform(lambda s: rng.permutation(s.to_numpy()))
        fit_g = stats.fit_rtdc_glm(shuffled, family="gaussian")
        strat_delta_aic_gauss.append(fit_g["delta_aic"])
        strat_slopes_gauss.append(fit_g["flow_slope"])

    strat_delta_aic_gauss = np.array(strat_delta_aic_gauss)
    strat_slopes_gauss = np.array(strat_slopes_gauss)
    print("\n--- Stratified Permutation Results (Within Each Date Cluster) ---")
    print(f"Stratified Null Delta AIC: mean = {strat_delta_aic_gauss.mean():.4f}, median = {np.median(strat_delta_aic_gauss):.4f}, max = {strat_delta_aic_gauss.max():.4f}")
    fp_strat = np.mean(strat_delta_aic_gauss > 2.0)
    print(f"Stratified Null False Positive Rate (Delta AIC > 2.0): {fp_strat * 100:.2f}% ({np.sum(strat_delta_aic_gauss > 2.0)} / {n_perms})")
    print(f"Stratified Null Slope b: mean = {strat_slopes_gauss.mean():.6f}, std = {strat_slopes_gauss.std():.6f}")

    return {
        "global_gauss": {
            "mean_delta_aic": float(null_delta_aic_gauss.mean()),
            "median_delta_aic": float(np.median(null_delta_aic_gauss)),
            "max_delta_aic": float(null_delta_aic_gauss.max()),
            "fp_rate": float(fp_gauss),
            "p_emp": float(p_emp_gauss),
            "slope_mean": float(null_slopes_gauss.mean()),
            "slope_std": float(null_slopes_gauss.std()),
            "slope_ci95": [float(np.percentile(null_slopes_gauss, 2.5)), float(np.percentile(null_slopes_gauss, 97.5))],
        },
        "stratified_gauss": {
            "mean_delta_aic": float(strat_delta_aic_gauss.mean()),
            "median_delta_aic": float(np.median(strat_delta_aic_gauss)),
            "max_delta_aic": float(strat_delta_aic_gauss.max()),
            "fp_rate": float(fp_strat),
            "slope_mean": float(strat_slopes_gauss.mean()),
            "slope_std": float(strat_slopes_gauss.std()),
        }
    }


def run_per_replicate_stability(active_runs: pd.DataFrame):
    print("\n" + "=" * 80)
    print("CHALLENGE 2: PER-REPLICATE STABILITY ACROSS ALL 5 INDIVIDUAL DATES")
    print("=" * 80)

    dates = sorted(active_runs["Date"].unique())
    results = {}

    print(f"{'Date':<10} | {'Runs':<5} | {'Gauss b':<10} | {'Gauss SE':<10} | {'Gauss p':<12} | {'Gauss dAIC':<10} | {'Binom b':<10} | {'Binom p':<12} | {'Spearman rho':<12} | {'Spearman p':<12}")
    print("-" * 115)

    slopes_gauss = []
    for d in dates:
        sub = active_runs[active_runs["Date"] == d].copy()
        n_runs = len(sub)

        # Fit single-replicate Gaussian GLM
        fit_g = stats.fit_rtdc_glm(sub, cluster_col="Date", family="gaussian")
        b_g = fit_g["flow_slope"]
        p_g = fit_g["p_value"]
        daic_g = fit_g["delta_aic"]
        se_g = fit_g["model"].bse[-1]

        # Fit single-replicate Binomial GLM
        fit_b = stats.fit_rtdc_glm(sub, cluster_col="Date", family="binomial")
        b_b = fit_b["flow_slope"]
        p_b = fit_b["p_value"]

        # Spearman
        rho, p_rho = stats.compute_spearman(sub["FR"], sub["MedD"])

        slopes_gauss.append(b_g)
        results[int(d)] = {
            "n_runs": n_runs,
            "gauss_b": float(b_g),
            "gauss_se": float(se_g),
            "gauss_p": float(p_g),
            "gauss_delta_aic": float(daic_g),
            "binom_b": float(b_b),
            "binom_p": float(p_b),
            "spearman_rho": float(rho),
            "spearman_p": float(p_rho)
        }

        print(f"{d:<10} | {n_runs:<5} | {b_g:<+10.6f} | {se_g:<10.6f} | {p_g:<12.2e} | {daic_g:<10.2f} | {b_b:<+10.6f} | {p_b:<12.2e} | {rho:<+12.4f} | {p_rho:<12.2e}")

    slopes_gauss = np.array(slopes_gauss)
    all_positive = bool(np.all(slopes_gauss > 0))
    cv_slopes = float(slopes_gauss.std() / slopes_gauss.mean())

    print("-" * 115)
    print(f"All 5 individual replicates show flow slope b > 0: {all_positive}")
    print(f"Gaussian flow slope across 5 dates: mean = {slopes_gauss.mean():.6f}, std = {slopes_gauss.std():.6f}, CV = {cv_slopes * 100:.2f}%")
    print(f"Range: [{slopes_gauss.min():.6f}, {slopes_gauss.max():.6f}]")

    return {
        "dates": results,
        "all_positive": all_positive,
        "mean_b": float(slopes_gauss.mean()),
        "std_b": float(slopes_gauss.std()),
        "cv_b": cv_slopes
    }


def run_variance_reduction_invariance(active_runs: pd.DataFrame):
    print("\n" + "=" * 80)
    print("CHALLENGE 3: VARIANCE REDUCTION INVARIANCE ACROSS REFERENCE FLOW RATES")
    print("=" * 80)

    test_ref_flows = [0.01, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.50, 1.00]
    results = {}

    print(f"{'Ref Flow':<10} | {'Linear VarRaw':<14} | {'Linear VarAdj':<14} | {'Linear Red%':<12} | {'Logit VarRaw':<14} | {'Logit VarAdj':<14} | {'Logit Red%':<12}")
    print("-" * 96)

    linear_reds = []
    logit_reds = []

    for rf in test_ref_flows:
        res_lin = stats.calculate_variance_reduction(active_runs, ref_flow=rf, method="linear")
        res_log = stats.calculate_variance_reduction(active_runs, ref_flow=rf, method="logit")

        linear_reds.append(res_lin["variance_reduction_pct"])
        logit_reds.append(res_log["variance_reduction_pct"])

        results[rf] = {
            "linear": {
                "var_raw": res_lin["var_raw"],
                "var_adj": res_lin["var_adj"],
                "red_pct": res_lin["variance_reduction_pct"]
            },
            "logit": {
                "var_raw": res_log["var_raw"],
                "var_adj": res_log["var_adj"],
                "red_pct": res_log["variance_reduction_pct"]
            }
        }

        print(f"{rf:<10.3f} | {res_lin['var_raw']:<14.8f} | {res_lin['var_adj']:<14.8f} | {res_lin['variance_reduction_pct']:<12.4f}% | {res_log['var_raw']:<14.8f} | {res_log['var_adj']:<14.8f} | {res_log['variance_reduction_pct']:<12.4f}%")

    linear_reds = np.array(linear_reds)
    linear_variance_invariant = bool(np.allclose(linear_reds, linear_reds[0], atol=1e-8))

    print("-" * 96)
    print(f"Linear method variance reduction strictly invariant across ALL reference flow rates: {linear_variance_invariant}")
    print(f"Linear reduction value across all ref flows: {linear_reds[0]:.4f}%")
    print(f"Logit reduction range across [0.04, 0.12] uL/s: [{results[0.04]['logit']['red_pct']:.2f}%, {results[0.12]['logit']['red_pct']:.2f}%]")

    # Verify within-condition invariance
    print("\n--- Within-Condition Invariance Check (ref_flow=0.04 vs 0.08 vs 0.12) ---")
    for rf in [0.04, 0.08, 0.12]:
        res = stats.calculate_variance_reduction(active_runs, ref_flow=rf, method="linear")
        print(f"Ref Flow = {rf}:")
        for cond, metrics in res["within_condition"].items():
            print(f"  LatB {cond:5.3f} uM: raw={metrics['var_raw']:.7f} -> adj={metrics['var_adj']:.7f} (red={metrics['reduction_pct']:.2f}%)")

    return {
        "linear_invariant": linear_variance_invariant,
        "linear_pct": float(linear_reds[0]),
        "ref_flow_data": results
    }


def run_numerical_boundary_tests(active_runs: pd.DataFrame):
    print("\n" + "=" * 80)
    print("CHALLENGE 4: NUMERICAL BOUNDARIES & DEFENSIVE ERROR HANDLING")
    print("=" * 80)

    findings = []

    # Test 1: Zero / Negative flow rates only
    print("Test 4.1: Dataset with zero/negative flow rates only...")
    zero_runs = pd.DataFrame({
        "FR": [0.0, 0.0, -0.05],
        "MedD": [0.05, 0.06, 0.04],
        "Date": ["D1", "D1", "D2"],
        "N": [100, 100, 100]
    })
    try:
        stats.fit_rtdc_glm(zero_runs)
        findings.append(("Zero flow rates only", "UNEXPECTED_PASS", "Did not raise error when all FR <= 0"))
        print("  -> UNEXPECTED PASS")
    except Exception as e:
        findings.append(("Zero flow rates only", "RAISED_EXCEPTION", f"{type(e).__name__}: {str(e)}"))
        print(f"  -> Caught {type(e).__name__}: {str(e)[:80]}")

    # Test 2: Extreme flow rates (1e-12 and 1e12)
    print("\nTest 4.2: Extreme flow rates (1e-12 and 1e12)...")
    extreme_runs = active_runs.copy()
    extreme_runs.loc[0, "FR"] = 1e-12
    extreme_runs.loc[1, "FR"] = 1e12
    try:
        fit_ext = stats.fit_rtdc_glm(extreme_runs)
        adj_ext = stats.standardise_rtdc(extreme_runs, ref_flow=0.08)
        min_adj = adj_ext["MedD_adj"].min()
        max_adj = adj_ext["MedD_adj"].max()
        findings.append(("Extreme flow rates", "NUMERICAL_STABILITY", f"Fit slope={fit_ext['flow_slope']:.4f}, min MedD_adj={min_adj:.4f}, max MedD_adj={max_adj:.4f}"))
        print(f"  -> Successfully fit. b={fit_ext['flow_slope']:.4f}. MedD_adj range: [{min_adj:.4f}, {max_adj:.4f}]")
        if min_adj < 0:
            print("  -> NOTE: Linear subtraction produces negative deformation for extreme flow rate 1e12.")
    except Exception as e:
        findings.append(("Extreme flow rates", "ERROR", f"{type(e).__name__}: {str(e)}"))
        print(f"  -> Failed: {type(e).__name__}: {str(e)}")

    # Test 3: ref_flow <= 0 in standardise_rtdc
    print("\nTest 4.3: ref_flow <= 0 in standardise_rtdc...")
    try:
        adj_zero_rf = stats.standardise_rtdc(active_runs, ref_flow=0.0)
        has_nan_inf = np.isinf(adj_zero_rf["MedD_adj"]).any() or np.isnan(adj_zero_rf["MedD_adj"]).any()
        findings.append(("ref_flow <= 0 in standardise", "NAN_OR_INF_RETURNED" if has_nan_inf else "UNEXPECTED", f"Returns NaN/Inf={has_nan_inf} without raising ValueError"))
        print(f"  -> Result contains NaN/Inf: {has_nan_inf} (No explicit ValueError raised for ref_flow <= 0)")
    except Exception as e:
        findings.append(("ref_flow <= 0 in standardise", "EXCEPTION", f"{type(e).__name__}: {str(e)}"))
        print(f"  -> Raised {type(e).__name__}: {str(e)}")

    # Test 4: Single-row DataFrame
    print("\nTest 4.4: Single-row DataFrame in fit_rtdc_glm...")
    single_row = active_runs.iloc[:1].copy()
    try:
        stats.fit_rtdc_glm(single_row)
        findings.append(("Single-row DataFrame", "UNEXPECTED_PASS", "Did not raise error on n=1"))
        print("  -> UNEXPECTED PASS")
    except Exception as e:
        findings.append(("Single-row DataFrame", "RAISED_EXCEPTION", f"{type(e).__name__}: {str(e)}"))
        print(f"  -> Caught {type(e).__name__}: {str(e)[:80]}")

    # Test 5: Missing columns
    print("\nTest 4.5: Missing columns...")
    missing_cols = ["FR", "MedD", "Date"]
    for col in missing_cols:
        dropped = active_runs.drop(columns=[col])
        try:
            stats.fit_rtdc_glm(dropped)
            findings.append((f"Missing column '{col}'", "UNEXPECTED_PASS", "No KeyError"))
            print(f"  -> Missing {col}: UNEXPECTED PASS")
        except KeyError as e:
            findings.append((f"Missing column '{col}'", "KEY_ERROR_RAISED", f"Clean KeyError on missing {col}"))
            print(f"  -> Missing {col}: Clean KeyError caught ({e})")
        except Exception as e:
            findings.append((f"Missing column '{col}'", "OTHER_EXCEPTION", f"{type(e).__name__}: {str(e)}"))
            print(f"  -> Missing {col}: Caught {type(e).__name__}: {str(e)}")

    # Test 6: Zero variance in deformation (var_raw == 0)
    print("\nTest 4.6: Zero variance in deformation (all MedD identical)...")
    const_deform = active_runs.copy()
    const_deform["MedD"] = 0.05
    try:
        res_const = stats.calculate_variance_reduction(const_deform)
        findings.append(("Zero variance deformation", "RETURNED_RESULT", f"Returned var_raw={res_const['var_raw']}"))
        print(f"  -> Returned result: var_raw={res_const['var_raw']}, var_adj={res_const['var_adj']}, red_pct={res_const['variance_reduction_pct']}")
    except Exception as e:
        findings.append(("Zero variance deformation", "RAISED_EXCEPTION", f"{type(e).__name__}: {str(e)}"))
        print(f"  -> Caught {type(e).__name__}: {str(e)}")

    # Test 7: compute_spearman edge cases
    print("\nTest 4.7: compute_spearman boundary cases...")
    # Empty
    try:
        rho_emp, p_emp = stats.compute_spearman([], [])
        print(f"  -> Empty arrays: rho={rho_emp}, p={p_emp}")
        findings.append(("compute_spearman empty", "RESULT", f"rho={rho_emp}, p={p_emp}"))
    except Exception as e:
        print(f"  -> Empty arrays raised: {type(e).__name__}: {str(e)}")
        findings.append(("compute_spearman empty", "EXCEPTION", f"{type(e).__name__}"))

    # Constant
    rho_c, p_c = stats.compute_spearman([0.04, 0.08, 0.12], [0.05, 0.05, 0.05])
    print(f"  -> Constant deformation: rho={rho_c}, p={p_c}")
    findings.append(("compute_spearman constant", "RESULT", f"rho={rho_c}, p={p_c} (NaN expected due to zero variance)"))

    return findings


def main():
    print("Loading RT-DC dataset...")
    runs = stats.load_rtdc_runs(DATA_DIR)
    active = runs[runs["FR"] > 0].copy()
    print(f"Loaded {len(runs)} total runs, {len(active)} active runs, {int(active['N'].sum())} cells.")

    perm_results = run_permutation_tests(active, n_perms=1000, seed=42)
    rep_results = run_per_replicate_stability(active)
    var_results = run_variance_reduction_invariance(active)
    bound_results = run_numerical_boundary_tests(active)

    summary = {
        "permutation_test": perm_results,
        "per_replicate_stability": rep_results,
        "variance_reduction_invariance": var_results,
        "boundary_tests": bound_results
    }

    out_file = ROOT / "tools" / "stress_challenge_results.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nAll challenge results saved to {out_file}")


if __name__ == "__main__":
    main()
