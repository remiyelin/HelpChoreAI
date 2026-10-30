#!/usr/bin/env python3
"""P-06b: SAM 3.1 video tracking vs the lab tracker.
20 queue cells (10 author health=1, 10 health=0) with known pickle transits; cells
crossing in the same clip share one request (<=16 objects). Clips are MPEG-4 renders
of the served (flipped) consecutive AVI frames starting 5 frames before each transit.
Budget: <= 3000 billed frames total (usage.video_frames_processed is recorded per
request; abort before exceeding). Per tracked frame: SAM mask centroid vs pickle
pos_x/pos_y, IoU vs author contour (geometry.py), solidity + convexity defects
(same-grid hull, P-06 Condition 1). Object ids are joined only within a clip,
never across exit/re-entry (here: one prompt per cell, first transit frame).
Run: uv run python src/sam_tracking.py [--probe]   (probe = first clip only)
Outputs: data/tables/sam_tracking_frames.csv, sam_tracking_cells.csv,
data/tables/sam_tracking_summary.json, docs/media/sam_tracking_demo.mp4 + keyframe strip.
"""
import argparse, json, subprocess, sys
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import geometry, meta_api, server
from meta_sam_parser import build_object_prompt, PromptObject, PromptBox, FramePrompt
from sam_pilot import shape_stats

ROOT = Path(__file__).resolve().parent.parent
TABLES, MEDIA, CLIPS = ROOT / "data" / "tables", ROOT / "docs" / "media", ROOT / "data" / "frames" / "clips"
BUDGET_FRAMES = 3000


def candidates():
    q = pd.read_csv(TABLES / "adjudication_queue.csv")
    objs, rows = {}, []
    for r in q.itertuples():
        key = (r.patient, str(r.date))
        if key not in objs: objs[key] = server.load_pickle(r.patient, str(r.date))
        obj = objs[key]
        if obj is None or int(r.cell) >= len(obj["Frames"]): continue
        fr = np.asarray(obj["Frames"][int(r.cell)])
        if not (40 <= len(fr) <= 170): continue
        rows.append({"patient": r.patient, "date": str(r.date), "visit": r.visit, "cell": int(r.cell),
                     "health": int(r.health), "track_len": int(len(fr)), "f0": int(fr.min()), "f1": int(fr.max()),
                     "score": int(len(fr) + int(fr.min()) // 2000)})
    return pd.DataFrame(rows), objs


def group_clips(cells):
    """Merge same-run cells whose [f0-5, f1] windows overlap (gap <= 10) into one clip."""
    clips = []
    for (patient, date), g in cells.groupby(["patient", "date"]):
        cur = None
        for r in g.sort_values("f0").itertuples():
            start, end = max(0, r.f0 - 5), r.f1  # transits can start at frame 0: never negative
            if cur is None or start > cur["end"] + 10:
                cur = {"patient": patient, "date": str(date), "start": int(start), "end": int(end), "cells": []}
                clips.append(cur)
            else:
                cur["end"] = max(cur["end"], int(end))
            cur["cells"].append(r._asdict() if hasattr(r, "_asdict") else dict(r._asdict()))
        for c in clips:
            pass
    for c in clips:
        c["billed"] = max(50, c["end"] - c["start"] + 1)
    return clips


def select_cells():
    cand, objs = candidates()
    chosen = []
    for health in (0, 1):
        pool = cand[cand.health == health].sort_values("score")
        picked = []
        for r in pool.itertuples():
            trial = pd.DataFrame(chosen + picked + [r._asdict()])
            if sum(c["billed"] for c in group_clips(trial)) <= BUDGET_FRAMES or len(picked) < 3:
                picked.append(r._asdict())
            if len(picked) == 10: break
        chosen.extend(picked)
    cells = pd.DataFrame(chosen)
    clips = group_clips(cells)
    total = sum(c["billed"] for c in clips)
    print(f"selected {len(cells)} cells (health counts {cells.health.value_counts().to_dict()}) "
          f"in {len(clips)} clips, billed-frame estimate {total} (budget {BUDGET_FRAMES})")
    for c in clips:
        print(f" clip {c['patient']}/{c['date']} frames {c['start']}-{c['end']} ({c['billed']} billed), cells {[x['cell'] for x in c['cells']]}")
    assert total <= BUDGET_FRAMES, "selection exceeds billed-frame budget"
    return cells, clips, objs


def extract_clip_frames(clip):
    have = all((ROOT / "data" / "frames" / f"{clip['patient']}_{clip['date']}_M10" / f"frame_{f}.raw").exists()
               for f in (clip["start"], clip["end"]))
    if not have:
        cmd = ["node", "tools/extract_imaq_frames.mjs", f"--patient={clip['patient']}", f"--date={clip['date']}",
               f"--range={clip['start']}-{clip['end']}"]
        print("extract:", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)


def read_frame(patient, date, frame_no):
    fdir = ROOT / "data" / "frames" / f"{patient}_{date}_M10"
    raw, meta = fdir / f"frame_{frame_no}.raw", fdir / f"frame_{frame_no}.json"
    if not raw.exists(): return None
    m = json.loads(meta.read_text()); w, h = int(m["width"]), int(m["height"])
    img = np.frombuffer(raw.read_bytes(), dtype=np.uint8)
    if img.size < w * h: return None
    return img[:w * h].reshape(h, w)[::-1].copy()  # served (flipped) orientation


def write_clip(clip):
    CLIPS.mkdir(parents=True, exist_ok=True)
    path = CLIPS / f"{clip['patient']}_{clip['date']}_{clip['start']}_{clip['end']}.mp4"
    frames = []
    for f in range(clip["start"], clip["end"] + 1):
        img = read_frame(clip["patient"], clip["date"], f)
        if img is None: raise SystemExit(f"missing extracted frame {f} in clip {path.name}")
        frames.append(img)
    h, w = frames[0].shape
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for img in frames:
        vw.write(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    vw.release()
    clip.update({"path": path, "w": w, "h": h, "n_frames": len(frames)})
    return path


def clip_prompt(clip, objs):
    obj = objs[(clip["patient"], clip["date"])]
    prompts = []
    for k, c in enumerate(clip["cells"]):
        cell = int(c["cell"])
        contour = np.asarray(obj["Contours"][cell][0], dtype=float)
        xs, ys = contour[:, 0], contour[:, 1]
        prompts.append(PromptObject(id=str(k + 1), prompts=[FramePrompt(
            frame=int(c["f0"] - clip["start"]),
            box=PromptBox(left=int(xs.min()), top=int(ys.min()), right=int(xs.max()) + 1, bottom=int(ys.max()) + 1))]))
    return build_object_prompt(size=(clip["w"], clip["h"]), objects=prompts)


def index_records(records):
    """Key streamed records by (frame, object_id) — output lines can arrive out of order."""
    return {(r["frame"], r["object_id"]): r for r in records}


def position_gate(frames: pd.DataFrame, thresh_px: float = 5.0, max_frac: float = 0.10) -> pd.DataFrame:
    """Position gate (no API calls): flag a frame when the SAM centroid is more than
    thresh_px from the lab tracker's pos_x/pos_y; flag the whole track when that
    happens on more than max_frac of its frames. Catches silent identity lag, where
    SAM returns confident cell-shaped masks hundreds of pixels behind the cell."""
    g = (frames.groupby(["patient", "date", "cell", "author_health"])["centroid_dist_px"]
         .apply(lambda s: float((s > thresh_px).mean())).reset_index(name="frac_frames_over_thresh"))
    g["track_flagged"] = g.frac_frames_over_thresh > max_frac
    return g


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    cells, clips, objs = select_cells()
    if args.probe: clips = clips[:1]
    billed_total, frame_rows, cell_rows = 0, [], []
    clip_keys = []  # (clip, by_key) per processed clip, for the demo choice below
    for clip in clips:
        extract_clip_frames(clip)
        path = write_clip(clip)
        mp4 = path.read_bytes()
        up = meta_api.sam_upload_video(mp4, path.name)
        if up.get("status") != "OK":
            print(f"clip {path.name}: upload {up}"); continue
        prompt = clip_prompt(clip, objs)
        r = meta_api.sam_track_video(up["file_id"], mp4, prompt)
        print(f"clip {path.name}: track {r.get('status')} records={len(r.get('records', []))} "
              f"billed={r.get('video_frames_processed')} cache={r.get('_cache')}")
        if r.get("status") != "OK": continue
        billed = int(r.get("video_frames_processed") or clip["billed"])
        billed_total += billed
        if billed_total > BUDGET_FRAMES:
            raise SystemExit(f"BILLED BUDGET EXCEEDED: {billed_total} > {BUDGET_FRAMES} — stop and ask")
        by_key = index_records(r["records"])
        obj = objs[(clip["patient"], clip["date"])]
        for k, c in enumerate(clip["cells"]):
            oid, cell = str(k + 1), int(c["cell"])
            frames = np.asarray(obj["Frames"][cell]); posx = np.asarray(obj["pos_x"][cell], dtype=float)
            posy = np.asarray(obj["pos_y"][cell], dtype=float)
            track_idx = {int(f): i for i, f in enumerate(frames)}
            dists, sols, matched = [], [], 0
            for (fr_idx, o), rec in sorted(by_key.items()):
                if o != oid or fr_idx is None: continue
                absolute = clip["start"] + fr_idx
                if absolute not in track_idx: continue
                ti = track_idx[absolute]
                mask = geometry.mask_from_rows(rec["rows"], clip["h"], clip["w"])
                if geometry.area(mask) == 0: continue
                matched += 1
                ys_m, xs_m = np.nonzero(mask)
                dist = float(np.hypot(xs_m.mean() - posx[ti], ys_m.mean() - posy[ti]))
                contour = np.asarray(obj["Contours"][cell][ti], dtype=float)
                iou = geometry.iou(mask, geometry.fill_contour(contour, clip["h"], clip["w"]))
                st = shape_stats(mask)
                dists.append(dist); sols.append(st["solidity"])
                frame_rows.append({"patient": clip["patient"], "date": clip["date"], "cell": cell,
                                   "author_health": int(c["health"]), "clip_frame": int(fr_idx), "abs_frame": int(absolute),
                                   "centroid_dist_px": round(dist, 2), "iou_author": round(iou, 3),
                                   "solidity": st["solidity"], "defects_gt1px": st["defects_gt1px"],
                                   "confidence": rec.get("confidence")})
            cell_rows.append({"patient": clip["patient"], "date": clip["date"], "cell": cell,
                              "author_health": int(c["health"]), "track_len": int(c["track_len"]),
                              "frames_matched": matched, "frames_lost": int(c["track_len"] - matched),
                              "median_centroid_dist_px": round(float(np.median(dists)), 2) if dists else None,
                              "share_within_2px": round(float(np.mean([d <= 2 for d in dists])), 3) if dists else None,
                              "solidity_min": round(float(np.min(sols)), 3) if sols else None,
                              "solidity_median": round(float(np.median(sols)), 3) if sols else None})
            print(f" cell {cell} h={int(c['health'])}: matched {matched}/{int(c['track_len'])} "
                  f"medianDist={cell_rows[-1]['median_centroid_dist_px']} within2px={cell_rows[-1]['share_within_2px']}")
        clip_keys.append((clip, by_key))
    fdf, cdf = pd.DataFrame(frame_rows), pd.DataFrame(cell_rows)
    fdf.to_csv(TABLES / "sam_tracking_frames.csv", index=False)
    cdf.to_csv(TABLES / "sam_tracking_cells.csv", index=False)
    agg = {}
    for h, g in cdf.groupby("author_health"):
        agg[str(h)] = {"cells": int(len(g)), "median_centroid_dist_px": round(float(g.median_centroid_dist_px.median()), 2),
                       "share_within_2px_mean": round(float(g.share_within_2px.mean()), 3),
                       "frames_lost_total": int(g.frames_lost.sum()), "frames_total": int(g.track_len.sum()),
                       "solidity_min_median": round(float(g.solidity_min.median()), 3),
                       "solidity_median_median": round(float(g.solidity_median.median()), 3)}
    summary = {"billed_frames_total": int(billed_total), "cost_usd_at_0.20_per_1000": round(billed_total * 0.20 / 1000, 4),
               "by_health": agg, "overall": {
                   "median_centroid_dist_px": round(float(cdf.median_centroid_dist_px.median()), 2),
                   "share_within_2px_mean": round(float(cdf.share_within_2px.mean()), 3),
                   "frames_lost_total": int(cdf.frames_lost.sum()), "frames_total": int(cdf.track_len.sum())}}
    (TABLES / "sam_tracking_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    if clip_keys and len(cdf):
        best = cdf.sort_values("median_centroid_dist_px").iloc[0]
        demo = next((ck for ck in clip_keys if any(int(c["cell"]) == int(best.cell) and c["patient"] == best.patient
                                                   for c in ck[0]["cells"])), clip_keys[0])
        print(f"demo clip: {demo[0]['path'].name} (best-tracked cell {int(best.cell)}, median dist {best.median_centroid_dist_px} px)")
        save_demo(demo, objs)


def save_demo(demo, objs):
    import struct, zlib
    clip, by_key = demo
    MEDIA.mkdir(parents=True, exist_ok=True)
    n = clip["n_frames"]; fps = max(1, round(n / 10))
    out = MEDIA / "sam_tracking_demo.mp4"
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (clip["w"], clip["h"] * 6))
    obj = objs[(clip["patient"], clip["date"])]
    keyframes = []
    for j in range(n):
        img = read_frame(clip["patient"], clip["date"], clip["start"] + j)
        rgb = np.stack([img, img, img], -1).astype(float)
        for k, c in enumerate(clip["cells"]):
            rec = by_key.get((j, str(k + 1)))
            if rec:
                mask = geometry.mask_from_rows(rec["rows"], clip["h"], clip["w"])
                rgb[mask] = rgb[mask] * 0.45 + np.array([245.0, 158.0, 11.0]) * 0.55
                cell = int(c["cell"]); frames = np.asarray(obj["Frames"][cell])
                if clip["start"] + j in frames:
                    ti = int(np.where(frames == clip["start"] + j)[0][0])
                    for x, y in np.asarray(obj["Contours"][cell][ti], dtype=float)[::4]:
                        if 0 <= int(y) < clip["h"] and 0 <= int(x) < clip["w"]: rgb[int(y), int(x)] = [13, 200, 180]
        big = cv2.resize(rgb.astype(np.uint8), (clip["w"], clip["h"] * 6), interpolation=cv2.INTER_NEAREST)
        vw.write(big)
        if j in {0, n // 5, 2 * n // 5, 3 * n // 5, 4 * n // 5, n - 1}: keyframes.append(big)
    vw.release()
    strip = np.vstack(keyframes)
    sh, sw = strip.shape[:2]
    raw = b"".join(b"\x00" + strip[i].tobytes() for i in range(sh))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    (MEDIA / "sam_tracking_keyframes.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", sw, sh, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    print(f"demo: {out} (fps {fps}, {n} frames) + docs/media/sam_tracking_keyframes.png")


if __name__ == "__main__":
    main()
