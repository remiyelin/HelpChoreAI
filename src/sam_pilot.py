#!/usr/bin/env python3
"""P-06 PILOT ONLY (stage 1 of 2): can SAM 3.1 masks recover spicules the convex-hull
author contours erase? 20 queue cells (10 author health=1, 10 health=0, seed 7):
 (a) box prompt (half-open max+1, include_confidence) on raw 200x48 and on 4x upscale — 40 calls;
 (b) concept prompts 'red blood cell' / 'cell' on 4x crops of 6 cells — 12 calls;
 (c) repeats of (a) in the better setting for 10 cells — 10 calls. Total <= 62 new calls.
Per mask (original-pixel units): area, perimeter, solidity, convexity defects >1px,
roughness, confidence, IoU vs author contour. Contact sheet: docs/media/sam_pilot_sheet.png.
Run: uv run python src/sam_pilot.py   (writes data/tables/pilot_sam.csv; NO full batch here)
"""
import json, sys
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import geometry, meta_api, server
from meta_sam_parser import build_object_prompt, PromptObject, PromptBox, FramePrompt
from step3b_pixel_model import decode_gray_png

ROOT = Path(__file__).resolve().parent.parent
TABLES, DOCS = ROOT / "data" / "tables", ROOT / "docs"
CALLS = [0]


def box_prompt(poly, w, h, scale=1):
    xs = [p[0] * scale for p in poly]; ys = [p[1] * scale for p in poly]
    return build_object_prompt(size=(w, h), objects=[PromptObject(id="1", prompts=[
        FramePrompt(frame=0, box=PromptBox(left=int(min(xs)), top=int(min(ys)),
                                           right=int(max(xs)) + 1, bottom=int(max(ys)) + 1))])])


def pick_mask(masks, poly, w, h):
    """Mask whose box centre is closest to the author box centre (same rule as _sam_run)."""
    cx = float(np.mean([p[0] for p in poly])); cy = float(np.mean([p[1] for p in poly]))
    def dist(m):
        b = m["box"]; return ((b[0] + b[2]) / 2 - cx) ** 2 + ((b[1] + b[3]) / 2 - cy) ** 2
    m = min(masks, key=dist)
    return geometry.mask_from_rows(m["rows"], h, w), m.get("confidence")


def shape_stats(mask):
    area = geometry.area(mask)
    if area == 0: return {"area": 0, "perimeter": 0.0, "solidity": np.nan, "defects_gt1px": 0, "roughness": np.nan}
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(cnts, key=cv2.contourArea)
    per = float(cv2.arcLength(cnt, True))
    # Hull area on the SAME 1x pixel grid (Condition 1, DECISIONS.md): convex hull of all
    # foreground pixels, filled at 1x, so solidity <= 1.0 by construction.
    fg = np.column_stack(np.nonzero(mask))[:, ::-1].astype(np.int32).reshape(-1, 1, 2)  # (x, y)
    hull = cv2.convexHull(fg)
    hull_canvas = np.zeros(mask.shape, dtype=np.uint8)
    cv2.drawContours(hull_canvas, [hull], contourIdx=-1, color=1, thickness=-1)
    hull_area = int(hull_canvas.sum())
    defects = 0
    try:
        hull_idx = cv2.convexHull(cnt, returnPoints=False)
        d = cv2.convexityDefects(cnt, hull_idx)
        if d is not None: defects = int((d.reshape(-1, 4)[:, 3] / 256.0 > 1.0).sum())
    except cv2.error:
        pass
    return {"area": area, "perimeter": round(per, 1), "solidity": round(area / hull_area, 3) if hull_area else np.nan,
            "defects_gt1px": defects, "roughness": round(per / (2 * np.sqrt(np.pi * area)), 3)}


def downscale4(mask4):
    h, w = mask4.shape[0] // 4, mask4.shape[1] // 4
    return mask4.reshape(h, 4, w, 4).mean(axis=(1, 3)) > 0.5


def call(png, prompt, repeat=0):
    r = meta_api.sam_prompt_mask(png, prompt, repeat=repeat, tag="pilot-v1")
    if r.get("_cache") == "miss": CALLS[0] += 1
    return r


def main():
    q = pd.read_csv(TABLES / "adjudication_queue.csv")
    sample = pd.concat([q[q.health == h].sample(n=10, random_state=7) for h in (0, 1)]).reset_index(drop=True)
    rows, sheet_panels = [], []
    for q_ in sample.itertuples():
        got = server.frame_png(q_.patient, str(q_.date), int(q_.cell), crop=True)
        if got is None: continue
        png, info = got
        img = decode_gray_png(png); h, w = img.shape
        poly = info.get("contour_crop_fullres") or info["contour_crop"]
        author = geometry.fill_contour(poly, h, w)
        big = np.repeat(np.repeat(img, 4, 0), 4, 1)
        png4 = server.png_gray(big.astype(np.uint8))
        entry = {"patient": q_.patient, "date": str(q_.date), "visit": q_.visit, "cell": int(q_.cell),
                 "author_health": int(q_.health), "author_area": geometry.area(author)}
        for setting, use_png, scale, dims in [("raw", png, 1, (w, h)), ("x4", png4, 4, (w * 4, h * 4))]:
            r = call(use_png, box_prompt(poly, dims[0], dims[1], scale))
            if r.get("status") == "OK":
                mask_s, conf = pick_mask(r["masks"], [[x * scale, y * scale] for x, y in poly], dims[0], dims[1])
                mask = downscale4(mask_s) if scale == 4 else mask_s
                entry.update({f"{setting}_status": "OK", f"{setting}_confidence": conf,
                              f"{setting}_iou_author": round(geometry.iou(mask, author), 3),
                              **{f"{setting}_{k}": v for k, v in shape_stats(mask).items()}})
                if setting == "x4": entry["_mask_x4"] = mask
            else:
                entry.update({f"{setting}_status": r.get("status"), f"{setting}_detail": (r.get("detail") or "")[:120]})
            print(f"{q_.patient}/c{int(q_.cell)} h={int(q_.health)} {setting}: {entry.get(setting + '_status')} "
                  f"IoU={entry.get(setting + '_iou_author')} sol={entry.get(setting + '_solidity')} conf={entry.get(setting + '_confidence')}")
        rows.append(entry)
        sheet_panels.append((img, poly, entry.get("_mask_x4")))
    df = pd.DataFrame(rows).drop(columns=["_mask_x4"], errors="ignore")
    # (c) concept prompts on 4x for first 6 cells
    concept = {}
    for q_ in sample.head(6).itertuples():
        got = server.frame_png(q_.patient, str(q_.date), int(q_.cell), crop=True)
        png, info = got; img = decode_gray_png(png); h, w = img.shape
        png4 = server.png_gray(np.repeat(np.repeat(img, 4, 0), 4, 1).astype(np.uint8))
        for text in ("red blood cell", "cell"):
            r = call(png4, text)
            concept[f"{q_.patient}/c{int(q_.cell)}:{text}"] = (r.get("status"), r.get("records", 0))
            print(f"concept '{text}' {q_.patient}/c{int(q_.cell)}: {r.get('status')} records={r.get('records', 0)}")
    # better setting by mean IoU, then (d) repeats for 10 cells
    means = {s: df[f"{s}_iou_author"].mean() for s in ("raw", "x4") if f"{s}_iou_author" in df}
    better = max(means, key=means.get)
    print("mean IoU by setting:", {k: round(v, 3) for k, v in means.items()}, "-> better:", better)
    rep_rows = []
    for q_ in sample.head(10).itertuples():
        got = server.frame_png(q_.patient, str(q_.date), int(q_.cell), crop=True)
        png, info = got; img = decode_gray_png(png); h, w = img.shape
        poly = info.get("contour_crop_fullres") or info["contour_crop"]
        use_png, dims, scale = (png, (w, h), 1) if better == "raw" else (
            server.png_gray(np.repeat(np.repeat(img, 4, 0), 4, 1).astype(np.uint8)), (w * 4, h * 4), 4)
        r = call(use_png, box_prompt(poly, dims[0], dims[1], scale), repeat=1)
        if r.get("status") == "OK":
            mask_s, _ = pick_mask(r["masks"], [[x * scale, y * scale] for x, y in poly], dims[0], dims[1])
            mask = downscale4(mask_s) if scale == 4 else mask_s
            first = df[(df.patient == q_.patient) & (df.cell == int(q_.cell))].iloc[0]
            # IoU vs first-run mask is recomputed from the stored first mask via a fresh deterministic
            # comparison: solidity spread only needs the two scalar values; mask IoU needs run-1 mask,
            # which was kept in sheet panels for x4 or recomputed below for raw.
            rep_rows.append({"patient": q_.patient, "cell": int(q_.cell), "repeat_solidity": shape_stats(mask)["solidity"],
                             "first_solidity": first[f"{better}_solidity"], "repeat_mask": mask,
                             "first_iou_author": first[f"{better}_iou_author"],
                             "repeat_iou_author": round(geometry.iou(mask, geometry.fill_contour(poly, h, w)), 3)})
    # repeat-vs-first mask IoU: rerun is cached, so re-derive first masks from cache (hits, 0 new calls)
    for rr in rep_rows:
        qmask = None
        got = server.frame_png(rr["patient"], str(df[(df.patient == rr["patient"]) & (df.cell == rr["cell"])].iloc[0].date), rr["cell"], crop=True)
        png, info = got; img = decode_gray_png(png); h, w = img.shape
        poly = info.get("contour_crop_fullres") or info["contour_crop"]
        use_png, dims, scale = (png, (w, h), 1) if better == "raw" else (
            server.png_gray(np.repeat(np.repeat(img, 4, 0), 4, 1).astype(np.uint8)), (w * 4, h * 4), 4)
        r0 = call(use_png, box_prompt(poly, dims[0], dims[1], scale), repeat=0)
        m0s, _ = pick_mask(r0["masks"], [[x * scale, y * scale] for x, y in poly], dims[0], dims[1])
        m0 = downscale4(m0s) if scale == 4 else m0s
        rr["iou_repeat_vs_first"] = round(geometry.iou(rr.pop("repeat_mask"), m0), 3)
    rep = pd.DataFrame(rep_rows)
    if len(rep):
        rep["solidity_absdiff"] = (rep.repeat_solidity - rep.first_solidity).abs()
        print(rep[["patient", "cell", "iou_repeat_vs_first", "first_solidity", "repeat_solidity"]].to_string(index=False))
        print(f"repeat IoU mean={rep.iou_repeat_vs_first.mean():.3f} min={rep.iou_repeat_vs_first.min():.3f}; "
              f"solidity |diff| mean={rep.solidity_absdiff.mean():.3f} max={rep.solidity_absdiff.max():.3f}")
    df.to_csv(TABLES / "pilot_sam.csv", index=False)
    (TABLES / "pilot_sam_concept.json").write_text(json.dumps(
        {"concept": {k: list(v) for k, v in concept.items()}, "mean_iou": {k: round(float(v), 3) for k, v in means.items()},
         "better_setting": better, "new_calls": CALLS[0]}, indent=1), encoding="utf-8")
    # contact sheet: 5 cols x 4 rows, crop x3, author contour teal, SAM x4 mask amber
    import struct, zlib
    panels = []
    for img, poly, mask in sheet_panels:
        rgb = np.stack([img, img, img], -1).astype(float)
        if mask is not None: rgb[mask] = rgb[mask] * 0.45 + np.array([245.0, 158.0, 11.0]) * 0.55
        for x, y in poly:
            if 0 <= int(y) < rgb.shape[0] and 0 <= int(x) < rgb.shape[1]: rgb[int(y), int(x)] = [13, 200, 180]
        panels.append(np.repeat(np.repeat(rgb.astype(np.uint8), 3, 0), 3, 1))
    ph = max(p.shape[0] for p in panels); pw = max(p.shape[1] for p in panels)
    panels = [np.pad(p, ((0, ph - p.shape[0]), (0, pw - p.shape[1]), (0, 0)), constant_values=40) for p in panels]
    sheet = np.full((4 * ph + 15, 5 * pw + 24, 3), 40, np.uint8)
    for i, p in enumerate(panels):
        r_, c_ = divmod(i, 5); sheet[r_ * (ph + 3):r_ * (ph + 3) + ph, c_ * (pw + 3):c_ * (pw + 3) + pw] = p
    raw = b"".join(b"\x00" + sheet[i].tobytes() for i in range(sheet.shape[0]))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    out = DOCS / "media" / "sam_pilot_sheet.png"; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", sheet.shape[1], sheet.shape[0], 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    print(f"sheet: {out} | panel order = pilot_sam.csv row order")
    print(f"NEW SAM CALLS (pilot): {CALLS[0]}")
    print(df[["patient", "cell", "author_health", "raw_iou_author", "x4_iou_author", "raw_solidity", "x4_solidity",
              "x4_defects_gt1px", "x4_confidence"]].to_string(index=False) if "x4_iou_author" in df else df.to_string())


if __name__ == "__main__":
    main()
