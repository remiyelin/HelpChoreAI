#!/usr/bin/env python3
"""P-10 deterministic audit-agent tools. JSON in/out; every output carries its SHA-256.

Verification lives here, not in the model: render_and_sign templates numbers from the
signed Checker payload and rejects any narrative number that no tool output of this
run produced. No tool returns individual author labels, and no P3/P5 data is served
(dev patients only: P1/P2/P4). Ground-truth tables stay read-only inputs.
"""
import hashlib, json, re, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import checker

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "data" / "tables"
DEV_PATIENTS = {"P1", "P2", "P4"}

WORD_NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
                "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
                "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                "hundred": 100, "thousand": 1000}


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()


def _seal(obj: dict) -> dict:
    out = dict(obj)
    out["sha256"] = hashlib.sha256(_canon(out)).hexdigest()
    return out


def _guard(patient):
    if patient not in DEV_PATIENTS:
        return _seal({"status": "ERROR", "error": "patient_not_in_dev_set"})
    return None


def _numbers_in(text: str):
    found = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")]
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if w in WORD_NUMBERS: found.append(float(WORD_NUMBERS[w]))
    if re.search(r"\b(percent|percentage)\b", (text or "").lower()) and not found:
        found.append(-1.0)  # percent word with no number still counts as a numeric claim
    return found


def _collect_numbers(obj, acc):
    if isinstance(obj, bool): return
    if isinstance(obj, (int, float)): acc.add(round(float(obj), 4))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k != "sha256": _collect_numbers(v, acc)
    elif isinstance(obj, list):
        for v in obj: _collect_numbers(v, acc)


def list_pairs(patient: str) -> dict:
    if (g := _guard(patient)) is not None: return g
    dec = pd.read_csv(TABLES / "visit_pairs_decisions_v3.csv")
    rows = dec[dec.patient == patient]
    pairs = [{"from_visit": str(r["from"]), "to_visit": str(r.to), "decision": str(r.decision)}
             for _, r in rows.iterrows()]
    return _seal({"status": "OK", "patient": patient, "pairs": pairs})


def pair_stats(patient: str, from_visit: str, to_visit: str) -> dict:
    if (g := _guard(patient)) is not None: return g
    dec = pd.read_csv(TABLES / "visit_pairs_decisions_v3.csv")
    row = dec[(dec.patient == patient) & (dec["from"] == from_visit) & (dec.to == to_visit)]
    if len(row) != 1: return _seal({"status": "ERROR", "error": "pair_not_found"})
    r = row.iloc[0]
    runs_df = pd.read_csv(TABLES / "per_run.csv")
    run_details = {}
    for visit in (from_visit, to_visit):
        sub = runs_df[(runs_df.patient == patient) & (runs_df.visit == visit)]
        run_details[visit] = {"n_runs": int(len(sub)), "n_total": int(sub.n_total.sum()),
                              "mean_flow_ul_s": round(float(sub.flow_ul_s.mean()), 6) if len(sub) else None,
                              "mean_skip_rate": round(float(sub.skip_rate.mean()), 4) if len(sub) else None}
    return _seal({"status": "OK", "patient": patient, "from_visit": from_visit, "to_visit": to_visit,
                  "treatment": str(r.treatment), "delta_raw": float(r.delta_raw),
                  "delta_adj": float(r.delta_adj), "rcv95": float(r.RCV95),
                  "decision": str(r.decision), "run_details": run_details})


def qc_gate(patient: str, from_visit: str, to_visit: str) -> dict:
    if (g := _guard(patient)) is not None: return g
    pv = pd.read_csv(TABLES / "per_visit_adjusted_v3.csv")
    rates = {}
    for visit in (from_visit, to_visit):
        sub = pv[(pv.patient == patient) & (pv.visit == visit)]
        if len(sub) != 1: return _seal({"status": "ERROR", "error": "visit_not_found"})
        rates[visit] = round(float(sub.iloc[0].skip_rate), 4)
    blocked = any(v > 0.25 for v in rates.values())
    return _seal({"status": "BLOCK" if blocked else "PASS", "patient": patient,
                  "skip_rates": rates, "threshold": 0.25, "qc_blocked": blocked})


def sample_cells(patient: str, visit: str, n: int) -> dict:
    if (g := _guard(patient)) is not None: return g
    n = max(1, min(int(n), 20))
    feats = pd.read_csv(TABLES / "cell_features_M10.csv")
    sub = feats[(feats.patient == patient) & (feats.visit == visit)]
    if not len(sub): return _seal({"status": "ERROR", "error": "no_cells_for_visit"})
    pick = sub.sample(n=min(n, len(sub)), random_state=42).sort_values("cell")
    cells = [{"cell": int(r.cell), "area_mean": round(float(r.area_mean), 3),
              "circ_mean": round(float(r.circ_mean), 4), "axis_ratio": round(float(r.axis_ratio), 4),
              "n_frames": int(r.n_frames)} for r in pick.itertuples()]  # no author labels
    return _seal({"status": "OK", "patient": patient, "visit": visit, "cells": cells})


def rater_summary(patient: str, visit: str) -> dict:
    if (g := _guard(patient)) is not None: return g
    out = {"status": "OK", "patient": patient, "visit": visit}
    for name, fname in (("spark_1_3", "rater_spark.csv"), ("open_weight", "rater_open.csv")):
        path = TABLES / fname
        if not path.exists(): out[name] = {"n": 0}; continue
        df = pd.read_csv(path, dtype={"date": str})
        sub = df[(df.patient == patient) & (df.visit.astype(str) == str(visit))]
        ok = sub[sub.status == "OK"] if len(sub) else sub
        counts = {k: int((ok.spiculated == k).sum()) for k in ("yes", "no", "cannot_tell")} if len(ok) else \
                 {"yes": 0, "no": 0, "cannot_tell": 0}
        out[name] = {"n": int(len(ok)), "counts": counts,
                     "cannot_tell_share": round(counts["cannot_tell"] / len(ok), 3) if len(ok) else None}
    return _seal(out)


def render_and_sign(patient: str, from_visit: str, to_visit: str, narrative: str) -> dict:
    if (g := _guard(patient)) is not None: return g
    # Checker inside the tool: any narrative number not produced by a tool output
    # of this run is rejected; feedback names the offending claim, never the truth.
    allowed = set()
    _collect_numbers(pair_stats(patient, from_visit, to_visit), allowed)
    _collect_numbers(qc_gate(patient, from_visit, to_visit), allowed)
    for num in _numbers_in(narrative):
        if num == -1.0 or round(num, 4) not in allowed:
            return _seal({"status": "REJECTED_UNVERIFIED_NUMBER",
                          "feedback": "narrative contains a number that does not appear in any "
                                      "tool output of this run; remove all numbers from the narrative"})
        return _seal({"status": "REJECTED_UNVERIFIED_NUMBER",
                      "feedback": "numbers belong in the templated payload fields, not in the "
                                  "narrative; remove all numbers from the narrative"})
    try:
        env = checker.sign_payload(checker.build_payload(patient, from_visit, to_visit))
        report = checker.render_report(env, narrative or "")
    except ValueError as e:
        return _seal({"status": "REJECTED_UNVERIFIED_NUMBER", "feedback": str(e)})
    ok, errs = checker.verify_envelope(env)
    aok, aerrs = checker.audit_report(report, env)
    if not ok or not aok:
        return _seal({"status": "REJECTED_UNVERIFIED_NUMBER",
                      "feedback": f"checker verification failed: {errs + aerrs}"})
    return _seal({"status": "PASS", "final_status": "AWAITING_SIGNOFF", "patient": patient,
                  "from_visit": from_visit, "to_visit": to_visit, "report": report,
                  "report_sha256": env["payload"]["report_sha256"], "envelope": env})


TOOLS = {"list_pairs": list_pairs, "pair_stats": pair_stats, "qc_gate": qc_gate,
         "sample_cells": sample_cells, "rater_summary": rater_summary,
         "render_and_sign": render_and_sign}


def call_tool(name: str, args: dict) -> dict:
    fn = TOOLS.get(name)
    if fn is None: return _seal({"status": "ERROR", "error": f"unknown_tool:{name}"})
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return _seal({"status": "ERROR", "error": f"bad_arguments:{e}"})
    except Exception as e:
        return _seal({"status": "ERROR", "error": f"{type(e).__name__}:{e}"})


if __name__ == "__main__":
    print(json.dumps(list_pairs("P1"), indent=1))
