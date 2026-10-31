#!/usr/bin/env python3
"""P-23 population measurements. Subcommands: A, B, C, D, analyze.

All paid calls go through meta_api's cache (data/api_cache). No threshold,
prompt or feature changes: SAM uses the raw-crop box prompt (tag pilot-v1)
from sam_pilot/sam_full_batch; raters use meta_api.spark_rater /
baseten_rater with the frozen prompt/schema at repeat=0; the position gate
uses sam_tracking.position_gate with its frozen 5 px / 10% thresholds.
Seed 20261031 everywhere. Budgets are enforced in-code and abort before
exceeding: Meta estimate cap $8 total ledger (baseline $1.26 already spent;
SAM image $0.0025/call, Spark rater $0.02/call, SAM video $0.0002/frame),
Baseten at most 200 new calls.
"""
import argparse, json, subprocess, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import geometry, meta_api, server
from sam_pilot import box_prompt, pick_mask, shape_stats
from sam_full_batch import SAM_FEATS, BASE_FEATS
from step3b_pixel_model import decode_gray_png
from rater_spark import cell_frame_pngs, cat_stats
import sam_tracking

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "data" / "tables"
SEED = 20261031
META_BASELINE_USD = float(__import__("os").environ.get("POP_EVAL_META_SPENT", "1.26"))
META_CAP_USD = 8.00
COST = {"sam_image": 0.0025, "spark_rater": 0.02, "sam_video_frame": 0.0002}
BASETEN_CAP = 200


class Budget:
    def __init__(self):
        self.meta_new_usd = 0.0
        self.baseten_new = 0
        self.meta_calls = {"sam_image": 0, "spark_rater": 0, "sam_video_frames": 0}

    def charge_meta(self, kind, n=1):
        self.meta_calls[kind] = self.meta_calls.get(kind, 0) + n
        self.meta_new_usd += COST[kind] * n
        total = META_BASELINE_USD + self.meta_new_usd
        if total > META_CAP_USD:
            raise SystemExit(f"META BUDGET: estimated total ${total:.2f} > ${META_CAP_USD}; stopping before exceeding")

    def charge_baseten(self, n=1):
        self.baseten_new += n
        if self.baseten_new > BASETEN_CAP:
            raise SystemExit(f"BASETEN BUDGET: >{BASETEN_CAP} new calls; stopping before exceeding")

    def summary(self):
        return {"meta_baseline_usd": META_BASELINE_USD, "meta_new_est_usd": round(self.meta_new_usd, 4),
                "meta_total_est_usd": round(META_BASELINE_USD + self.meta_new_usd, 4),
                "meta_calls": self.meta_calls, "baseten_new_calls": self.baseten_new}


def extract_frames(patient, date, frame_nos):
    """Extract exact AVI frames (no model call) for cells whose crops are missing."""
    fdir = ROOT / "data" / "frames" / f"{patient}_{date}_M10"
    missing = sorted({int(f) for f in frame_nos if not (fdir / f"frame_{int(f)}.raw").exists()})
    if not missing:
        return 0
    log = ROOT / ".tmp" / f"extract_{patient}_{date}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w") as fh:
        subprocess.run(["node", "tools/extract_imaq_frames.mjs", f"--patient={patient}",
                        f"--date={date}", "--frames=" + ",".join(map(str, missing))],
                       cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, check=True)
    return len(missing)


def lopo(df, feats, label="health"):
    """LOPO kappa per patient + cell-bootstrap CI of mean kappa (seed 20261031)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import cohen_kappa_score, balanced_accuracy_score
    d = df.dropna(subset=feats + [label]).copy()
    if d[label].nunique() < 2 or len(d) < 20:
        return {"n": int(len(d)), "mean_kappa": None, "kappa_ci95": None, "per_patient": {}}
    oof = {}
    for test_p in sorted(d.patient.unique()):
        tr, te = d[d.patient != test_p], d[d.patient == test_p]
        if tr[label].nunique() < 2 or len(te) < 5:
            continue
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
        clf.fit(tr[feats], tr[label])
        oof[test_p] = (te[label].to_numpy(), clf.predict(te[feats]))
    if not oof:
        return {"n": int(len(d)), "mean_kappa": None, "kappa_ci95": None, "per_patient": {}}
    kaps, per = [], {}
    for p, (y, pr) in sorted(oof.items()):
        s = server.kappa_ac1(list(y), list(pr))
        kaps.append(s["kappa"])
        per[p] = {"kappa": s["kappa"], "ac1": s["ac1"], "pabak": round(2 * s["agreement"] - 1, 3),
                  "bal_acc": round(float(balanced_accuracy_score(y, pr)), 3), "n": int(len(y))}
    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(1000):
        bk = []
        for p, (y, pr) in sorted(oof.items()):
            idx = rng.integers(0, len(y), len(y))
            if len(np.unique(y[idx])) < 2 or len(np.unique(pr[idx])) < 2:
                continue
            bk.append(cohen_kappa_score(y[idx], pr[idx]))
        if len(bk) == len(oof):
            boots.append(float(np.mean(bk)))
    lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if boots else (None, None)
    return {"n": int(len(d)), "mean_kappa": round(float(np.mean(kaps)), 3),
            "kappa_ci95": [round(lo, 3), round(hi, 3)] if lo is not None else None, "per_patient": per}


def boot_metric_ci(y, pred, b=1000):
    """Bootstrap CIs for kappa/AC1/PABAK on rated pairs (seed 20261031)."""
    y, pred = np.asarray(y), np.asarray(pred)
    ks, acs, pbs = [], [], []
    rng = np.random.default_rng(SEED)
    for _ in range(b):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) < 2 or len(np.unique(pred[idx])) < 2:
            continue
        k, a, pb = cat_stats(y[idx], pred[idx])
        ks.append(k); acs.append(a); pbs.append(pb)
    def ci(v):
        return [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] if v else None
    return {"kappa_ci95": ci(ks), "ac1_ci95": ci(acs), "pabak_ci95": ci(pbs)}


def rater_metrics(df):
    """AC1/PABAK/cannot_tell with CIs vs author + counts, for one rater's rows (repeat=0)."""
    if "spiculated" not in df.columns:
        return {"n_sample": int(len(df)), "n_ok": 0, "n_rated": 0, "cannot_tell_share": None,
                "status_counts": df.status.value_counts().to_dict() if len(df) else {}}
    ok = df[df.status == "OK"]
    rated = ok[ok.spiculated.isin(["yes", "no"])]
    out = {"n_sample": int(len(df)), "n_ok": int(len(ok)), "n_rated": int(len(rated)),
           "cannot_tell_share": round(float((ok.spiculated == "cannot_tell").mean()), 3) if len(ok) else None}
    if len(rated) >= 5 and rated.author_health.nunique() == 2:
        y = rated.author_health.to_numpy()
        pr = (rated.spiculated == "yes").astype(int).to_numpy()
        kap, ac1, pabak = cat_stats(y, pr)
        out.update({"kappa": kap, "ac1": ac1, "pabak": pabak, **boot_metric_ci(y, pr),
                    "confusion": {"tp": int(((y == 1) & (pr == 1)).sum()), "fn": int(((y == 1) & (pr == 0)).sum()),
                                  "fp": int(((y == 0) & (pr == 1)).sum()), "tn": int(((y == 0) & (pr == 0)).sum())}})
    # cannot_tell CI (binomial bootstrap over OK rows)
    if len(ok):
        ct = (ok.spiculated == "cannot_tell").astype(int).to_numpy()
        rng = np.random.default_rng(SEED)
        boots = [float(ct[rng.integers(0, len(ct), len(ct))].mean()) for _ in range(1000)]
        out["cannot_tell_ci95"] = [round(float(np.percentile(boots, 2.5)), 3),
                                   round(float(np.percentile(boots, 97.5)), 3)]
    return out


def sam_one_cell(patient, date, cell, budget):
    """One raw-crop box-prompt SAM call (tag pilot-v1) + shape features. Cached."""
    got = server.frame_png(patient, str(date), int(cell), crop=True)
    if got is None:
        return {"sam_status": "NO_FRAME"}
    png, info = got
    img = decode_gray_png(png)
    h, w = img.shape
    poly = info.get("contour_crop_fullres") or info["contour_crop"]
    r = meta_api.sam_prompt_mask(png, box_prompt(poly, w, h, 1), repeat=0, tag="pilot-v1")
    if r.get("_cache") == "miss" and r.get("status") == "OK":
        budget.charge_meta("sam_image")
    base = {"sam_status": r.get("status"), "sam_cache": r.get("_cache")}
    if r.get("status") == "OK":
        mask, conf = pick_mask(r["masks"], poly, w, h)
        author = geometry.fill_contour(poly, h, w)
        base.update({"sam_confidence": conf, "sam_iou_author": round(geometry.iou(mask, author), 3),
                     **{f"sam_{k}": v for k, v in shape_stats(mask).items() if k != "area"},
                     "sam_area": geometry.area(mask)})
        base["sam_area_ratio"] = round(base["sam_area"] / max(geometry.area(author), 1), 3)
    else:
        base["sam_detail"] = (r.get("detail") or "")[:160]
    return base


def kept_cells():
    cf = pd.read_csv(TABLES / "cell_features_M10.csv")
    return cf[cf.shape_code != 0].copy()


def part_a(sample_n=None):
    """SAM on kept dev cells NOT in the adjudication queue (population cohort)."""
    budget = Budget()
    kept = kept_cells()
    q = pd.read_csv(TABLES / "adjudication_queue.csv")
    qkeys = set(zip(q.patient, q.date.astype(str), q.cell))
    off = kept[[(r.patient, str(r.date), int(r.cell)) not in qkeys for r in kept.itertuples()]].copy()
    off = off.sort_values(["patient", "date", "cell"]).reset_index(drop=True)
    mode = "all"
    if sample_n is not None and len(off) > sample_n:
        idx = np.random.default_rng(SEED).choice(len(off), size=sample_n, replace=False)
        off = off.iloc[sorted(idx)].copy()
        mode = f"random{sample_n}"
    # extract mid frames, one sequential pass per (patient, date)
    objs, need = {}, {}
    for r in off.itertuples():
        k = (r.patient, str(r.date))
        if k not in objs:
            objs[k] = server.load_pickle(*k)
        fr = np.asarray(objs[k]["Frames"][int(r.cell)])
        need.setdefault(k, []).append(int(fr[len(fr) // 2]))
    for (patient, date), frames in sorted(need.items()):
        n = extract_frames(patient, date, frames)
        print(f"A extract {patient}/{date}: {n} frames", flush=True)
    out_path = TABLES / "sam_shape_features_population.csv"
    done = {}
    if out_path.exists():
        prev = pd.read_csv(out_path)
        done = {(r.patient, str(r.date), int(r.cell)): r._asdict() for r in prev.itertuples()}
    rows = []
    for i, r in enumerate(off.itertuples()):
        key = (r.patient, str(r.date), int(r.cell))
        if key in done:
            rows.append(done[key]); continue
        base = {"patient": r.patient, "date": str(r.date), "visit": r.visit, "cell": int(r.cell),
                "author_health": int(r.health), **{f: getattr(r, f) for f in BASE_FEATS}}
        base.update(sam_one_cell(r.patient, str(r.date), int(r.cell), budget))
        rows.append(base)
        if (i + 1) % 25 == 0:
            pd.DataFrame(rows).to_csv(out_path, index=False)
            print(f"A {i + 1}/{len(off)} meta={budget.summary()}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    print(f"A done mode={mode} n={len(df)} statuses={df.sam_status.value_counts().to_dict()} budget={budget.summary()}")
    return df


def part_b():
    """Random 100 kept dev cells (seed, label-blind), Spark + Spark Open at repeat=0."""
    budget = Budget()
    kept = kept_cells().sort_values(["patient", "date", "cell"]).reset_index(drop=True)
    idx = np.random.default_rng(SEED).choice(len(kept), size=100, replace=False)
    sample = kept.iloc[sorted(idx)].copy()
    # extract quarter/mid/three-quarter frames for the sampled tracks
    need = {}
    for r in sample.itertuples():
        obj = server.load_pickle(r.patient, str(r.date))
        if obj is None or int(r.cell) >= len(obj["Frames"]):
            continue
        fr = np.asarray(obj["Frames"][int(r.cell)])
        for j in sorted({len(fr) // 4, len(fr) // 2, (3 * len(fr)) // 4}):
            need.setdefault((r.patient, str(r.date)), []).append(int(fr[j]))
    for (patient, date), frames in sorted(need.items()):
        print(f"B extract {patient}/{date}: {extract_frames(patient, date, frames)} frames", flush=True)
    rows_s, rows_o = [], []
    for r in sample.itertuples():
        pngs, track = cell_frame_pngs(r.patient, str(r.date), int(r.cell))
        base = {"patient": r.patient, "date": str(r.date), "visit": r.visit, "cell": int(r.cell),
                "author_health": int(r.health), "repeat": 0, "n_frames_sent": len(pngs), "track_frames": track}
        if not pngs:
            rows_s.append({**base, "status": "NO_FRAMES"})
            rows_o.append({**base, "status": "NO_FRAMES"})
            continue
        rs = meta_api.spark_rater(pngs, repeat=0)
        if rs.get("_cache") == "miss" and rs.get("status") == "OK":
            budget.charge_meta("spark_rater")
        ro = meta_api.baseten_rater(pngs, repeat=0)
        if ro.get("_cache") == "miss":
            budget.charge_baseten(int(ro.get("_new_calls", 1)))
        for rows, rr, model in ((rows_s, rs, "muse-spark-1.3"), (rows_o, ro, "meta-models/muse-spark-open")):
            row = {**base, "model": model, "status": rr.get("status"), "cache": rr.get("_cache")}
            if rr.get("status") == "OK":
                rt = rr["rater"]
                row.update({"spiculated": rt["spiculated"], "confidence": rt["confidence"],
                            "spicule_points": json.dumps(rt["spicule_points"]),
                            "image_quality": rt["image_quality"], "reason": rt["reason"]})
            else:
                row.update({"detail": (rr.get("detail") or "")[:200]})
            rows.append(row)
        print(f"B {r.patient}/{r.date}/c{int(r.cell)}: spark={rs.get('status')} open={ro.get('status')} "
              f"budget={budget.summary()}", flush=True)
    ds, do = pd.DataFrame(rows_s), pd.DataFrame(rows_o)
    ds.to_csv(TABLES / "rater_unselected_spark.csv", index=False)
    do.to_csv(TABLES / "rater_unselected_open.csv", index=False)
    print("B spark:", rater_metrics(ds))
    print("B open:", rater_metrics(do))
    print("B head-to-head:", head_to_head(ds, do))
    print("B budget:", budget.summary())


def sealed_cells():
    """All kept (shape!=0) sealed cells from the fetched Offline pickles + Results labels.

    Same construction as step34_model.load_cells, restricted to the sealed
    patients (explicitly allowed for Part C in this task)."""
    from step2_analysis import RestrictedUnpickler
    import re as _re
    rows = []
    dev = ROOT / "data" / "dev"
    for patient in ("P3", "P5"):
        for pkl in sorted((dev / patient).glob("*Offline__M10_results.p")):
            m = _re.match(r"(P\d)__(\d{8})_P\d\(([^)]+)\)__", pkl.name)
            if not m: continue
            pat, date, visit = m.groups()
            res_files = list((dev / patient).glob(f"{patient}__{date}_*__Results__results_M10_*.txt"))
            if len(res_files) != 1: continue
            labels = []
            for line in res_files[0].read_text(errors="replace").splitlines():
                if not line.strip() or line.startswith("#"): continue
                qq = line.split(); labels.append((int(float(qq[1])), int(float(qq[3]))))
            with open(pkl, "rb") as fh: obj = RestrictedUnpickler(fh, encoding="latin1").load()
            from step34_model import contour_area_mean_std
            for i in range(min(len(labels), len(obj["Frames"]))):
                def ms(k):
                    a = np.asarray(obj[k][i], dtype=float); return float(np.nanmean(a)), float(np.nanstd(a))
                am, asd = contour_area_mean_std(obj, i); cm, csd = ms("circularity")
                xm, _ = ms("x_ax"); ym, _ = ms("y_ax")
                s, h = labels[i]
                if s == 0: continue
                rows.append({"patient": pat, "date": date, "visit": visit, "cell": i, "shape_code": s,
                             "health": h, "area_mean": am, "area_std": asd, "circ_mean": cm,
                             "circ_std": csd, "axis_ratio": (xm / ym if ym else np.nan),
                             "n_frames": len(obj["Frames"][i])})
    return pd.DataFrame(rows)


def part_c():
    """Sealed predictions (d) raters and (e) SAM concavity, frozen ranges."""
    budget = Budget()
    cells = sealed_cells()
    print(f"C sealed kept cells: {len(cells)}; by patient {cells.patient.value_counts().to_dict()}")
    if not len(cells):
        print("C BLOCKED: no sealed pickles on disk (run tools/extract_holdout_pickles.mjs)")
        return
    rng = np.random.default_rng(SEED)
    # (d) 80 cells, 40/40 by author label; labels used only to stratify.
    picks = []
    for h in (0, 1):
        sub = cells[cells.health == h]
        idx = rng.choice(len(sub), size=min(40, len(sub)), replace=False)
        picks.append(sub.iloc[sorted(idx)])
    sample_d = pd.concat(picks).reset_index(drop=True)
    need = {}
    for r in sample_d.itertuples():
        obj = server.load_pickle(r.patient, str(r.date))
        fr = np.asarray(obj["Frames"][int(r.cell)])
        for j in sorted({len(fr) // 4, len(fr) // 2, (3 * len(fr)) // 4}):
            need.setdefault((r.patient, str(r.date)), []).append(int(fr[j]))
    for (patient, date), frames in sorted(need.items()):
        print(f"C(d) extract {patient}/{date}: {extract_frames(patient, date, frames)} frames", flush=True)
    rows_s, rows_o = [], []
    sealed_spark_f, sealed_open_f = TABLES / "rater_sealed_spark.csv", TABLES / "rater_sealed_open.csv"
    if sealed_spark_f.exists() and sealed_open_f.exists():
        print("C(d) tables already exist; not re-calling raters (BLOCKED replies are not cached)")
        rows_s = pd.read_csv(sealed_spark_f).to_dict("records")
        rows_o = pd.read_csv(sealed_open_f).to_dict("records")
    for r in sample_d.itertuples() if not rows_s else []:
        pngs, track = cell_frame_pngs(r.patient, str(r.date), int(r.cell))
        base = {"patient": r.patient, "date": str(r.date), "visit": r.visit, "cell": int(r.cell),
                "author_health": int(r.health), "repeat": 0, "n_frames_sent": len(pngs), "track_frames": track}
        if not pngs:
            rows_s.append({**base, "status": "NO_FRAMES"}); rows_o.append({**base, "status": "NO_FRAMES"}); continue
        rs = meta_api.spark_rater(pngs, repeat=0)
        if rs.get("_cache") == "miss" and rs.get("status") == "OK": budget.charge_meta("spark_rater")
        ro = meta_api.baseten_rater(pngs, repeat=0)
        if ro.get("_cache") == "miss": budget.charge_baseten(int(ro.get("_new_calls", 1)))
        for rows, rr, model in ((rows_s, rs, "muse-spark-1.3"), (rows_o, ro, "meta-models/muse-spark-open")):
            row = {**base, "model": model, "status": rr.get("status"), "cache": rr.get("_cache")}
            if rr.get("status") == "OK":
                rt = rr["rater"]
                row.update({"spiculated": rt["spiculated"], "confidence": rt["confidence"],
                            "spicule_points": json.dumps(rt["spicule_points"]),
                            "image_quality": rt["image_quality"], "reason": rt["reason"]})
            else:
                row.update({"detail": (rr.get("detail") or "")[:200]})
            rows.append(row)
        print(f"C(d) {r.patient}/{r.date}/c{int(r.cell)}: spark={rs.get('status')} open={ro.get('status')}", flush=True)
    ds, do = pd.DataFrame(rows_s), pd.DataFrame(rows_o)
    ds.to_csv(TABLES / "rater_sealed_spark.csv", index=False)
    do.to_csv(TABLES / "rater_sealed_open.csv", index=False)
    print("C(d) spark:", rater_metrics(ds))
    print("C(d) open:", rater_metrics(do))
    print("C(d) head-to-head:", head_to_head(ds, do))
    # (e) at most 400 holdout cells, raw box prompt (seed sample over all sealed
    # kept cells); sized to 180 so the cumulative Meta estimate stays under $8.
    n_e = min(180, len(cells))
    idx = rng.choice(len(cells), size=n_e, replace=False)
    sample_e = cells.iloc[sorted(idx)].reset_index(drop=True)
    need = {}
    objs = {}
    for r in sample_e.itertuples():
        k = (r.patient, str(r.date))
        if k not in objs: objs[k] = server.load_pickle(*k)
        fr = np.asarray(objs[k]["Frames"][int(r.cell)])
        need.setdefault(k, []).append(int(fr[len(fr) // 2]))
    for (patient, date), frames in sorted(need.items()):
        print(f"C(e) extract {patient}/{date}: {extract_frames(patient, date, frames)} frames", flush=True)
    rows = []
    for i, r in enumerate(sample_e.itertuples()):
        base = {"patient": r.patient, "date": str(r.date), "visit": r.visit, "cell": int(r.cell),
                "author_health": int(r.health), **{f: getattr(r, f) for f in BASE_FEATS}}
        base.update(sam_one_cell(r.patient, str(r.date), int(r.cell), budget))
        rows.append(base)
        if (i + 1) % 25 == 0:
            pd.DataFrame(rows).to_csv(TABLES / "sam_shape_features_sealed.csv", index=False)
            print(f"C(e) {i + 1}/{len(sample_e)} budget={budget.summary()}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "sam_shape_features_sealed.csv", index=False)
    ok = df[df.sam_status == "OK"]
    for h, g in ok.groupby("author_health"):
        print(f"C(e) health={h}: n={len(g)} solidity={g.sam_solidity.mean():.3f} defects={g.sam_defects_gt1px.mean():.2f}")
    print("C budget:", budget.summary())


def part_d():
    """Position gate out of sample: 20 new dev cells, frozen 5 px / 10% gate."""
    budget = Budget()
    cand, objs = sam_tracking.candidates()
    first = pd.read_csv(TABLES / "sam_tracking_cells.csv")
    first_keys = set(zip(first.patient, first.date.astype(str), first.cell))
    pool = cand[[(r.patient, str(r.date), int(r.cell)) not in first_keys for r in cand.itertuples()]]
    pool = pool.sort_values(["track_len", "score"]).reset_index(drop=True)
    chosen = []
    for r in pool.itertuples():
        trial = pd.DataFrame(chosen + [r._asdict()])
        billed = sum(c["billed"] for c in sam_tracking.group_clips(trial))
        if billed <= 1600:
            chosen.append(r._asdict())
        if len(chosen) == 20: break
    cells = pd.DataFrame(chosen)
    clips = sam_tracking.group_clips(cells)
    est = sum(c["billed"] for c in clips)
    print(f"D selected {len(cells)} cells in {len(clips)} clips, billed estimate {est} (cap 1600)")
    assert est <= 1600
    frame_rows, billed_total = [], 0
    for clip in clips:
        sam_tracking.extract_clip_frames(clip)
        path = sam_tracking.write_clip(clip)
        mp4 = path.read_bytes()
        up = meta_api.sam_upload_video(mp4, path.name)
        if up.get("status") != "OK":
            print(f"D clip {path.name}: upload {up.get('status')}"); continue
        prompt = sam_tracking.clip_prompt(clip, objs)
        ck = meta_api._key("sam-3.1-video", [{"clip": __import__("hashlib").sha256(mp4).hexdigest(),
                                              "prompt": prompt}], extra="video-v1")
        if not (meta_api.CACHE / f"{ck}.json").exists():
            est = META_BASELINE_USD + budget.meta_new_usd + clip["billed"] * COST["sam_video_frame"]
            if est > META_CAP_USD:
                print(f"D STOP: next new clip would bring Meta estimate to ${est:.2f} > ${META_CAP_USD}; "
                      f"remaining clips not called (cache-only completion)")
                break
        r = meta_api.sam_track_video(up["file_id"], mp4, prompt)
        print(f"D clip {path.name}: {r.get('status')} billed={r.get('video_frames_processed')} cache={r.get('_cache')}", flush=True)
        if r.get("status") != "OK": continue
        billed = int(r.get("video_frames_processed") or clip["billed"])
        billed_total += billed
        if r.get("_cache") == "miss":
            budget.charge_meta("sam_video_frame", billed)
        if billed_total > 1600:
            raise SystemExit(f"D BILLED BUDGET EXCEEDED: {billed_total} > 1600")
        by_key = sam_tracking.index_records(r["records"])
        obj = objs[(clip["patient"], clip["date"])]
        for k, c in enumerate(clip["cells"]):
            oid, cell = str(k + 1), int(c["cell"])
            frames = np.asarray(obj["Frames"][cell]); posx = np.asarray(obj["pos_x"][cell], dtype=float)
            posy = np.asarray(obj["pos_y"][cell], dtype=float)
            track_idx = {int(f): i for i, f in enumerate(frames)}
            for (fr_idx, o), rec in sorted(by_key.items()):
                if o != oid or fr_idx is None: continue
                absolute = clip["start"] + fr_idx
                if absolute not in track_idx: continue
                ti = track_idx[absolute]
                mask = geometry.mask_from_rows(rec["rows"], clip["h"], clip["w"])
                if geometry.area(mask) == 0: continue
                ys_m, xs_m = np.nonzero(mask)
                dist = float(np.hypot(xs_m.mean() - posx[ti], ys_m.mean() - posy[ti]))
                frame_rows.append({"patient": clip["patient"], "date": clip["date"], "cell": cell,
                                   "author_health": int(c["health"]), "clip_frame": int(fr_idx),
                                   "abs_frame": int(absolute), "centroid_dist_px": round(dist, 2)})
        pd.DataFrame(frame_rows).to_csv(TABLES / "sam_tracking_frames_oos.csv", index=False)
    fdf = pd.DataFrame(frame_rows)
    fdf.to_csv(TABLES / "sam_tracking_frames_oos.csv", index=False)
    gate = sam_tracking.position_gate(fdf) if len(fdf) else fdf
    gate.to_csv(TABLES / "sam_tracking_gate_oos.csv", index=False)
    print(f"D billed total {billed_total}; gate:\n{gate.to_string(index=False) if len(gate) else 'no frames'}")
    print("D budget:", budget.summary())


def head_to_head(a, b):
    """Agreement between two rater DataFrames on cells both rated yes/no."""
    ma = {(r.patient, str(r.date), int(r.cell)): r.spiculated for r in a.itertuples() if r.status == "OK"}
    mb = {(r.patient, str(r.date), int(r.cell)): r.spiculated for r in b.itertuples() if r.status == "OK"}
    keys = sorted(set(ma) & set(mb))
    both = [(ma[k], mb[k]) for k in keys if ma[k] in ("yes", "no") and mb[k] in ("yes", "no")]
    out = {"n_both_ok": len(keys), "n_both_rated": len(both)}
    if len(both) >= 5:
        y = np.array([1 if x == "yes" else 0 for x, _ in both])
        pr = np.array([1 if x == "yes" else 0 for _, x in both])
        kap, ac1, pabak = cat_stats(y, pr)
        out.update({"kappa": kap, "ac1": ac1, "pabak": pabak, **boot_metric_ci(y, pr),
                    "raw_agreement_3way": round(float(np.mean([x == z for x, z in
                                                                 [(ma[k], mb[k]) for k in keys]])), 3) if keys else None})
    return out


def analyze():
    """LOPO BASE vs BASE+SAM on queue / off-queue / all, from the saved tables."""
    queue = pd.read_csv(TABLES / "sam_shape_features.csv")
    cf = kept_cells()
    base_map = {(r.patient, str(r.date), int(r.cell)): {f: getattr(r, f) for f in BASE_FEATS}
                for r in cf.itertuples()}
    for f in BASE_FEATS:
        queue[f] = [base_map.get((r.patient, str(r.date), int(r.cell)), {}).get(f) for r in queue.itertuples()]
    pop_path = TABLES / "sam_shape_features_population.csv"
    out = {}
    if pop_path.exists():
        pop = pd.read_csv(pop_path)
        for name, d in (("queue", queue), ("off_queue", pop), ("all", pd.concat([queue, pop], ignore_index=True))):
            dd = d[d.sam_status == "OK"].rename(columns={"author_health": "health"})
            out[name] = {"BASE": lopo(dd, BASE_FEATS), "BASE+SAM": lopo(dd, BASE_FEATS + SAM_FEATS),
                         "SAM_ONLY": lopo(dd, SAM_FEATS)}
            print(name, json.dumps(out[name], indent=1))
    (TABLES / "population_lopo.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["A", "B", "C", "D", "analyze"])
    ap.add_argument("--sample", type=int, default=None, help="Part A random subsample size (fallback)")
    a = ap.parse_args()
    if a.part == "A": part_a(a.sample)
    elif a.part == "B": part_b()
    elif a.part == "C": part_c()
    elif a.part == "D": part_d()
    else: analyze()
