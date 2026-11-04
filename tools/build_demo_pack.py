#!/usr/bin/env python3
"""Build the static signed demo pack in web/demo/. Local, with the data present. Makes no model call:
PUBLIC_MODE=1 means SAM masks come from data/api_cache or the cell is skipped.
Run: uv run --with pillow python tools/build_demo_pack.py
The public page serves only web/: no pickle, no key, no patient initials, no recording dates.
"""
import collections, json, os, random, re, shutil, subprocess, sys, time
from pathlib import Path
os.environ["PUBLIC_MODE"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
import cv2
import numpy as np
import pandas as pd
import statsmodels.api as sm
from PIL import Image
import audit_table, checker, geometry, meta_api, server
from sam_pilot import box_prompt, pick_mask, shape_stats
from step3b_pixel_model import decode_gray_png

T = ROOT / "data" / "tables"
OUT = ROOT / "web" / "demo"
RUNS = ROOT / "logs" / "agent_runs"
HERO_CELL = ("P1", "8w", 122)
CROP_W = 64
SEED = 20261031
CHANNEL_CLIP = "P1_20171212"

PREDICTIONS = [  # plain-words form of PREREGISTRATION.md, scorecard sections; misses first
    {"id": "e", "said": "SAM would find more dents in spiky cells and would not make the classifier worse.",
     "found": "Dents: +0.52, inside the predicted range. Solidity gap too small. Classifier got worse, kappa 0.033 to -0.052 on 180 cells.",
     "result": "Missed in part"},
    {"id": "d", "said": "AI raters would agree with the lab within a set range and say cannot tell a set share of the time.",
     "found": "Agreement in range for both (AC1 0.518 and 0.576). They said cannot tell far less than predicted (17.5% and 1.3%).",
     "result": "Missed in part"},
    {"id": "c", "said": "Decisions would differ from the normal reading in 25-50% of pairs, and 20-45% of decidable pairs would show a change.",
     "found": "Decisions differ in 45.5% and 27.3% were refused, both as predicted. Changes among decidable pairs: 0 of 8.",
     "result": "Missed in part"},
    {"id": "b", "said": "Correcting for flow would reduce the noise in 60-90% of visits.",
     "found": "It reduced the noise in 13 of 13 visits. Stronger than predicted, so outside the range.",
     "result": "Missed"},
    {"id": "a", "said": "Faster flow would mean fewer spiky cells in 80-100% of visits, slope between -0.60 and -0.10.",
     "found": "13 of 13 visits. Slope -0.322.",
     "result": "Held"},
]


def write(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def week(v):
    return int(str(v).rstrip("w"))


def visits_table():
    dev_raw = pd.read_csv(T / "per_visit.csv")
    dev_adj = pd.read_csv(T / "per_visit_adjusted_v3.csv")
    sealed = pd.read_csv(T / "per_visit_holdout.csv")
    dev_runs = pd.read_csv(T / "per_run.csv")
    sealed_runs = pd.read_csv(T / "per_run_holdout.csv")
    sealed_dec = pd.read_csv(T / "sealed_results.csv")
    frozen = {}
    for r in sealed_dec.itertuples():
        frozen[(r.patient, r._2)] = r.from_skip_rate
        frozen[(r.patient, r.to)] = r.to_skip_rate
    rows = []
    for name, base, runs in (("dev", dev_raw, dev_runs), ("sealed", sealed, sealed_runs)):
        for r in base.itertuples():
            g = runs[(runs.patient == r.patient) & (runs.visit == r.visit)]
            kept = g.dropna(subset=["frac_health1"])
            row = {"patient": r.patient, "visit": r.visit, "week": week(r.visit), "cohort": name,
                   "raw": round(float(r.frac_health1), 4), "kept": int(g.n_kept.sum()), "total": int(g.n_total.sum()),
                   "runs": int(len(kept)), "flow": round(float(kept.flow_ul_s.median()), 4)}
            row["unreadable"] = round(1 - row["kept"] / row["total"], 4)
            if name == "dev":
                a = dev_adj[(dev_adj.patient == r.patient) & (dev_adj.visit == r.visit)].iloc[0]
                row["adj"] = round(float(a.frac_adj), 4)
                row["skip"] = round(float(a.skip_rate), 4)
            else:
                row["skip"] = round(float(frozen.get((r.patient, r.visit), r.skip_rate)), 4)
            row["blocked"] = bool(row["skip"] > 0.25 or row["kept"] < 500)
            rows.append(row)
    return rows


def pairs_table(visits):
    v = {(r["patient"], r["visit"]): r for r in visits}
    rows = []
    for name, f in (("dev", "visit_pairs_decisions_v3.csv"), ("sealed", "sealed_results.csv")):
        for r in pd.read_csv(T / f).itertuples():
            a, b = v[(r.patient, r._2)], v[(r.patient, r.to)]
            pa, pb, na, nb = a["raw"], b["raw"], a["kept"], b["kept"]
            pool = (pa * na + pb * nb) / (na + nb)
            band = 1.96 * np.sqrt(pool * (1 - pool) * (1 / na + 1 / nb))
            alarm = bool(abs(r.delta_raw) > band)
            d = r.decision
            outcome = ({"exceeds_RCV": "confirmed", "within_RCV": "ruled_out", "indeterminate_QC": "refused"}[d] if alarm
                       else {"exceeds_RCV": "missed", "within_RCV": "quiet", "indeterminate_QC": "quiet_refused"}[d])
            pid = f"{r.patient}_{r._2}_{r.to}"
            rows.append({"id": pid, "patient": r.patient, "from": r._2, "to": r.to, "cohort": name, "raw": round(float(r.delta_raw), 4),
                         "adj": round(float(r.delta_adj), 4), "band": round(float(r.RCV95), 4), "naive_band": round(float(band), 4),
                         "naive_alarm": alarm, "decision": d, "outcome": outcome, "has_report": (RUNS / pid / "envelope.json").exists()})
    return rows


def flow_table():
    out = {"points": [], "fits": {}}
    for name, f in (("dev", "per_run.csv"), ("sealed", "per_run_holdout.csv")):
        d = pd.read_csv(T / f).dropna(subset=["frac_health1"])
        d = d[d.flow_ul_s > 0]
        out["points"] += [[name, round(float(r.flow_ul_s), 4), round(float(r.frac_health1), 4), int(r.n_kept)] for r in d.itertuples()]
        pts = sorted(d.patient.unique())
        k = np.round(d.frac_health1 * d.n_kept).to_numpy(float); n = d.n_kept.to_numpy(float)
        X = np.column_stack([*(np.asarray(d.patient == p, float) for p in pts), np.log(d.flow_ul_s.to_numpy(float))])
        m = sm.GLM(np.column_stack([k, n - k]), X, family=sm.families.Binomial()).fit()
        mean_i = float(np.mean(m.params[:-1])); slope = float(m.params[-1])
        grid = np.exp(np.linspace(np.log(d.flow_ul_s.min()), np.log(d.flow_ul_s.max()), 24))
        curve = 1 / (1 + np.exp(-(mean_i + slope * np.log(grid))))
        out["fits"][name] = {"slope": round(slope, 4), "curve": [[round(float(x), 4), round(float(y), 4)] for x, y in zip(grid, curve)]}
    return out


def mask_outline(mask, x0):
    m = (np.asarray(mask) > 0).astype(np.uint8)[:, x0:x0 + CROP_W]
    big = cv2.resize(m, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    cs, _ = cv2.findContours(big, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs: return []
    c = max(cs, key=cv2.contourArea).reshape(-1, 2)
    return [[round(float(x) / 4, 2), round(float(y) / 4, 2)] for x, y in c]


def build_cell(r, group, folder):
    got = server.frame_png(r.patient, str(r.date), int(r.cell), crop=True)
    if got is None: return None
    png, info = got
    img = decode_gray_png(png); h, w = img.shape
    poly = info.get("contour_crop_fullres") or info["contour_crop"]
    res = meta_api.sam_prompt_mask(png, box_prompt(poly, w, h, 1), repeat=0, tag="pilot-v1")
    if res.get("status") != "OK": return None
    mask, conf = pick_mask(res["masks"], poly, w, h)
    stats = shape_stats(mask)
    ys, xs = np.nonzero(mask)
    x0 = int(max(0, min(w - CROP_W, xs.mean() - CROP_W / 2)))
    crop = img[:, x0:x0 + CROP_W].astype(float)
    lo, hi = np.percentile(crop, 1), np.percentile(crop, 99)
    crop = np.clip((crop - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
    cid = f"{r.patient}-{r.visit}-{int(r.cell)}"
    cv2.imwrite(str(folder / f"{cid}.png"), crop)
    return {"id": cid, "patient": r.patient, "visit": r.visit, "cell": int(r.cell), "group": group,
            "lab": "spiky" if int(r.author_health) == 1 else "smooth", "w": CROP_W, "h": int(h),
            "stored": [[round(float(p[0]) - x0 + .5, 2), round(float(p[1]) + .5, 2)] for p in poly],
            "sam": mask_outline(mask, x0), "solidity": stats["solidity"], "dents": stats["defects_gt1px"],
            "confidence": None if conf is None else round(float(conf), 3)}


def cells_pack():
    folder = OUT / "cells"; folder.mkdir(parents=True, exist_ok=True)
    keep = ["patient", "date", "visit", "cell", "author_health", "sam_status", "sam_confidence", "sam_iou_author", "sam_solidity", "sam_defects_gt1px"]
    f = pd.concat([pd.read_csv(T / "sam_shape_features.csv", dtype={"date": str})[keep],
                   pd.read_csv(T / "sam_shape_features_population.csv", dtype={"date": str})[keep]], ignore_index=True)
    f = f[(f.sam_status == "OK") & (f.sam_iou_author > .6)]
    hero = f[(f.patient == HERO_CELL[0]) & (f.visit == HERO_CELL[1]) & (f.cell == HERO_CELL[2])]
    spiky = f[(f.author_health == 1) & (f.sam_confidence > .8)].sort_values("sam_solidity")
    smooth = f[(f.author_health == 0) & (f.sam_confidence > .8)].sort_values("sam_solidity", ascending=False)
    random_rows = f.sample(n=60, random_state=SEED)
    picks = [(hero, "spiky", 1), (spiky, "spiky", 20), (smooth, "smooth", 20), (random_rows, "random", 20)]
    out, seen, skipped = [], set(), 0
    for frame, group, want in picks:
        got = 0
        for r in frame.itertuples():
            key = (r.patient, r.visit, int(r.cell))
            if key in seen: continue
            seen.add(key)
            c = build_cell(r, group, folder)
            if c is None:
                skipped += 1; print(f"skip {key}: no frame or no cached mask"); continue
            out.append(c); got += 1
            if got == want: break
    write("cells/index.json", out)
    print(f"cells: {len(out)}, skipped {skipped}")


def trail_summary():
    finals = {}
    p = ROOT / "logs" / "audit_trail.jsonl"
    for line in p.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("kind") == "final": finals[e["run_id"]] = e.get("output", {})
    return {k: {"status": v.get("status"), "tools": v.get("tools_used", []), "refusals": v.get("refusals", 0)} for k, v in finals.items()}


def reports_pack():
    trail = trail_summary(); index = []
    for d in sorted(RUNS.iterdir()):
        env = json.loads((d / "envelope.json").read_text(encoding="utf-8"))
        report = (d / "report.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        ok, errs = checker.verify_envelope(env, report_text=report, check_tables=False)
        assert ok, (d.name, errs)
        audit_f = d / "open_weight_audit.json"
        audit = None
        if audit_f.exists():
            a = json.loads(audit_f.read_text(encoding="utf-8"))
            assert a["report_sha256"] == env["payload"]["report_sha256"], f"{d.name}: audit is about another text"
            audit = {k: a.get(k) for k in ("verdict", "reasons", "model_id", "host")}
        write(f"reports/{d.name}.json", {"id": d.name, "payload_canonical": checker.canonical(env["payload"]).decode("ascii"),
                                         "signature_hex": env["signature_hex"], "public_key_hex": env["public_key_hex"], "report": report,
                                         "open_weight_audit": audit, "agent": trail.get(d.name)})
        index.append(d.name)
    write("reports/index.json", index)
    (OUT / "public_key.hex").write_text(checker.pinned_public_key_hex() + "\n", encoding="utf-8")
    write("rules.json", {"banned": checker.BANNED, "disclaimer": checker.DISCLAIMER})
    print(f"reports: {len(index)}")


def open_pack():
    parity = []
    f = T / "open_weight_parity.csv"
    if f.exists():
        d = pd.read_csv(f).astype(object).where(lambda x: x.notna(), None)
        parity = d.drop(columns=[c for c in ("payload_sha256_cloud", "payload_sha256_open") if c in d]).to_dict("records")
    hosts = []
    for p in sorted((ROOT / "logs").glob("tamper_benchmark_*.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        if "spark_open" in j and "paraphrase12" in j["spark_open"]:
            hosts.append({"host": j.get("host"), "model": j.get("model_id"), "local": j["local_rules"], "open": j["spark_open"], "version": "current"})
        elif "sensitivity_paraphrase12" in j:
            hosts.append({"host": "baseten", "model": "meta-models/muse-spark-open", "version": "earlier auditor prompt",
                          "local": {"tampered12": j["sensitivity_old12"]["local_rules"], "paraphrase12": j["sensitivity_paraphrase12"]["local_rules"], "clean12": j["specificity_clean12"]["local_rules"]},
                          "open": {"tampered12": j["sensitivity_old12"]["spark_open"], "paraphrase12": j["sensitivity_paraphrase12"]["spark_open"], "clean12": j["specificity_clean12"]["spark_open"]}})
    if any(h["version"] == "current" for h in hosts):
        hosts = [h for h in hosts if h["version"] == "current"]
    summary = lambda f: json.loads((T / f).read_text(encoding="utf-8"))
    hard = pd.read_csv(T / "claim_check_hard.csv")[["decision", "sentence", "want", "word_list", "spark_open"]].to_dict("records")
    write("open.json", {"parity": parity, "hosts": hosts, "reader": summary("open_reader_summary.json"), "claims": summary("claim_check_summary.json"), "claims_hard": hard})


def example_pack():
    pairs, _v, info = audit_table.audit(audit_table.load(ROOT / "examples" / "reichel2022_sealed_holdout.csv"), reference=0.016, unreadable_rule="frozen")
    write("example.json", {"synthetic": False, "info": info, "pairs": pairs.to_dict("records")})


def tool_counts():
    c = collections.Counter()
    for p in meta_api.CACHE.glob("*.json"):
        try: j = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        if isinstance(j, dict): c[str(j.get("model") or "other")] += 1
    write("tools.json", {"sam": c["sam-3.1"], "spark": c["muse-spark-1.3"], "spark_open": c["meta-models/muse-spark-open"], "voice": c["muse-voice-transcribe-1.0"]})
    return c


def channel_pack():
    clips = sorted((ROOT / "data" / "frames" / "clips").glob(f"{CHANNEL_CLIP}_*.mp4"), key=lambda p: p.stat().st_size, reverse=True)
    if not clips:
        print("channel: no clip, skipped"); return
    cap = cv2.VideoCapture(str(clips[0])); frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
    cap.release()
    frames = frames[:90]
    imgs = [Image.fromarray(f) for f in frames]
    imgs[0].save(OUT / "channel.webp", save_all=True, append_images=imgs[1:], duration=70, loop=0, quality=50, method=4)
    imgs[len(imgs) // 2].save(OUT / "channel.png", optimize=True)
    print(f"channel: {len(frames)} frames from a tracked clip")


def main():
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    headline = json.loads((T / "headline_numbers.json").read_text(encoding="utf-8"))
    visits = visits_table()
    write("visits.json", visits)
    write("pairs.json", pairs_table(visits))
    write("flow.json", flow_table())
    write("predictions.json", PREDICTIONS)
    write("headline.json", {k: headline[k] for k in ("naive_binomial_vs_frozen", "pooled_log_flow_slope", "within_visit_negative_slope", "rcv95", "author_contour_solidity")})
    cells_pack(); reports_pack(); open_pack(); example_pack(); tool_counts(); channel_pack()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    write("meta.json", {"commit": commit, "built": time.strftime("%Y-%m-%d")})
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"web/demo: {size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
