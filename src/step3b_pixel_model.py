#!/usr/bin/env python3
"""Step 3b: do grayscale pixel/texture features from the 961 real cell crops beat contour-only?

For every adjudication-queue cell: decode the real 200x40 crop (server.frame_png), rasterize the
author contour, and extract interior intensity (dark-crescent), radial-profile, edge-gradient and
texture features. LOPO (leave-one-patient-out) logistic regression vs author `health`, same
protocol as src/step3_contour_check.py. Contour-only baseline LOPO kappa mean = 0.243.
Run: uv run python src/step3b_pixel_model.py
Outputs: data/tables/cell_pixel_features.csv; prints the kappa table. Triage only, never ground truth.
"""
import sys, zlib, struct
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score
sys.path.insert(0, str(Path(__file__).parent))
import server
from step3_contour_check import frame_feats

ROOT = Path(__file__).resolve().parent.parent
BASE_FEATS = ["area_mean", "area_std", "circ_mean", "circ_std", "axis_ratio", "n_frames"]
CONTOUR_FEATS = ["rough_mean", "rough_std", "solid_mean", "solid_std"]
PIXEL_FEATS = ["pix_mean_in", "pix_std_in", "pix_p10_in", "pix_p90_in", "dark20_mean",
               "crescent_contrast", "ring_inner", "ring_mid", "ring_outer", "center_edge_diff",
               "edge_grad", "lap_var", "hist_entropy"]


def decode_gray_png(png: bytes) -> np.ndarray:
    """Decode the 8-bit grayscale PNGs written by server.png_gray (filter byte 0 per row)."""
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(png):
        ln, tag = struct.unpack(">I4s", png[pos:pos + 8]); data = png[pos + 8:pos + 8 + ln]
        if tag == b"IHDR": w, h = struct.unpack(">II", data[:8])
        if tag == b"IDAT": idat += data
        pos += 12 + ln
    raw = zlib.decompress(idat)
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(h, w + 1)
    assert (rows[:, 0] == 0).all(), "unexpected PNG filter"
    return rows[:, 1:].astype(float)


def rasterize(poly, h, w):
    pts = np.asarray(poly, dtype=float)
    yy, xx = np.mgrid[0:h, 0:w]
    inside = np.zeros((h, w), dtype=bool); x, y = pts[:, 0], pts[:, 1]; j = len(pts) - 1
    for i in range(len(pts)):
        cond = ((y[i] > yy) != (y[j] > yy)) & (xx < (x[j] - x[i]) * (yy - y[i]) / max(y[j] - y[i], 1e-9) + x[i])
        inside ^= cond; j = i
    return inside


def pixel_features(img: np.ndarray, poly) -> dict | None:
    h, w = img.shape
    mask = rasterize(poly, h, w)
    if mask.sum() < 20: return None
    inside, outside = img[mask], img[~mask]
    gy, gx = np.gradient(img)
    grad = np.hypot(gx, gy)
    # boundary band: mask dilated minus eroded (3x3 shifts)
    dil = mask.copy(); ero = mask.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        dil |= np.roll(np.roll(mask, dy, 0), dx, 1); ero &= np.roll(np.roll(mask, dy, 0), dx, 1)
    band = dil & ~ero
    dark20 = np.mean(np.sort(inside)[:max(1, int(0.2 * len(inside)))])
    ys, xs = np.nonzero(mask); cy, cx = ys.mean(), xs.mean()
    r = np.hypot(xs - cx, ys - cy); r = r / max(r.max(), 1e-9)
    def ring(lo, hi):
        sel = inside[(r >= lo) & (r < hi)]
        return float(sel.mean()) if len(sel) else float(np.nan)
    hist, _ = np.histogram(inside, bins=16, range=(0, 256), density=True)
    hist = hist[hist > 0]
    lap = np.zeros_like(img); lap[1:-1, 1:-1] = img[:-2, 1:-1] + img[2:, 1:-1] + img[1:-1, :-2] + img[1:-1, 2:] - 4 * img[1:-1, 1:-1]
    return {"pix_mean_in": float(inside.mean()), "pix_std_in": float(inside.std()),
            "pix_p10_in": float(np.percentile(inside, 10)), "pix_p90_in": float(np.percentile(inside, 90)),
            "dark20_mean": float(dark20),
            "crescent_contrast": float((inside.mean() - dark20) / (img.std() + 1e-9)),
            "ring_inner": ring(0, 0.33), "ring_mid": ring(0.33, 0.66), "ring_outer": ring(0.66, 1.01),
            "center_edge_diff": float(ring(0, 0.33) - ring(0.66, 1.01)),
            "edge_grad": float(grad[band].mean()) if band.any() else 0.0,
            "lap_var": float(lap[mask].var()), "hist_entropy": float(-(hist * np.log(hist)).sum()),
            "pix_mean_out": float(outside.mean()) if len(outside) else float(np.nan)}


def contour_features(patient, date, cell):
    obj = server.load_pickle(patient, date)
    if obj is None or cell >= len(obj["Contours"]): return (np.nan,) * 4
    vals = [v for v in (frame_feats(c) for c in obj["Contours"][cell]) if v]
    if not vals: return (np.nan,) * 4
    r = np.array([v[0] for v in vals]); s = np.array([v[1] for v in vals])
    return float(np.nanmean(r)), float(np.nanstd(r)), float(np.nanmean(s)), float(np.nanstd(s))


def main():
    feats = pd.read_csv(ROOT / "data" / "tables" / "cell_features_M10.csv")
    base = {(r.patient, str(r.date), int(r.cell)): r for r in feats.itertuples()}
    queue = pd.read_csv(ROOT / "data" / "tables" / "adjudication_queue.csv")
    rows, skipped = [], 0
    for q in queue.itertuples():
        got = server.frame_png(q.patient, str(q.date), int(q.cell), crop=True)
        if got is None: skipped += 1; continue
        png, info = got
        pf = pixel_features(decode_gray_png(png), info.get("contour_crop_fullres") or info["contour_crop"])
        b = base.get((q.patient, str(q.date), int(q.cell)))
        if pf is None or b is None: skipped += 1; continue
        row = {"patient": q.patient, "date": str(q.date), "visit": q.visit, "cell": int(q.cell),
               "health": int(q.health), **{f: getattr(b, f) for f in BASE_FEATS},
               **dict(zip(CONTOUR_FEATS, contour_features(q.patient, str(q.date), int(q.cell)))), **pf}
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "data" / "tables" / "cell_pixel_features.csv", index=False)
    d = df.dropna().copy()
    print(f"STEP3B queue cells with real crop + pixel feats: {len(df)} (skipped {skipped}); usable after dropna: {len(d)}")
    for name, cols in [("BASE (area/circ/axis/frames)", BASE_FEATS),
                       ("BASE+CONTOUR (rough/solid)", BASE_FEATS + CONTOUR_FEATS),
                       ("PIXEL ONLY", PIXEL_FEATS),
                       ("BASE+CONTOUR+PIXEL", BASE_FEATS + CONTOUR_FEATS + PIXEL_FEATS)]:
        kaps, accs = [], []
        for test_p in sorted(d.patient.unique()):
            tr, te = d[d.patient != test_p], d[d.patient == test_p]
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
            clf.fit(tr[cols], tr.health); pred = clf.predict(te[cols])
            kaps.append(cohen_kappa_score(te.health, pred)); accs.append(balanced_accuracy_score(te.health, pred))
        print(f"{name}: LOPO kappa per patient={np.round(kaps, 3)} mean={np.mean(kaps):.3f} | bal_acc mean={np.mean(accs):.3f}")
    print("Reference: contour-only baseline LOPO kappa mean 0.243 (Step 3 contour check). "
          "Classifier remains triage/prioritization only, never ground truth.")


if __name__ == "__main__":
    main()
