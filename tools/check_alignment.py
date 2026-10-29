#!/usr/bin/env python3
"""Alignment check: is the served (vertically flipped) frame the orientation in which the
author contour actually sits on the cell? For 50 random queue cells with frames, compare
mean grey inside the author contour vs a 3-px ring outside it, in both orientations.
Cells are darker than background, so the aligned orientation shows inside < ring.
Served orientation is expected to win for >= 0.95 of cells.
Run: uv run python tools/check_alignment.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import geometry, server
from step3b_pixel_model import decode_gray_png

ROOT = Path(__file__).resolve().parent.parent


def ring_outside(mask, px=3):
    dil = mask.copy()
    for _ in range(px):
        d = dil.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            d |= np.roll(np.roll(dil, dy, 0), dx, 1)
        dil = d
    return dil & ~mask


def main():
    q = pd.read_csv(ROOT / "data" / "tables" / "adjudication_queue.csv")
    q = q.sample(n=min(50, len(q)), random_state=42)
    served_dark, flipped_dark, used = 0, 0, 0
    diffs_served, diffs_flipped = [], []
    for r in q.itertuples():
        got = server.frame_png(r.patient, str(r.date), int(r.cell), crop=True)
        if got is None: continue
        png, info = got
        img = decode_gray_png(png); h, w = img.shape
        poly = info.get("contour_crop_fullres") or info["contour_crop"]
        mask = geometry.fill_contour(poly, h, w)
        ring = ring_outside(mask)
        if mask.sum() < 20 or ring.sum() < 20: continue
        used += 1
        if img[mask].mean() < img[ring].mean(): served_dark += 1
        unflipped = img[::-1]  # same contour, image flipped back: misaligned unless symmetric
        if unflipped[mask].mean() < unflipped[ring].mean(): flipped_dark += 1
        diffs_served.append(float(img[mask].mean() - img[ring].mean()))
        diffs_flipped.append(float(unflipped[mask].mean() - unflipped[ring].mean()))
    print(f"cells used: {used}")
    print(f"mean inside-minus-ring grey: served {np.mean(diffs_served):.2f}, unflipped {np.mean(diffs_flipped):.2f} (more negative = darker inside)")
    print(f"inside darker than 3px ring, served (flipped) orientation: {served_dark}/{used} = {served_dark / max(used, 1):.3f}")
    print(f"inside darker than 3px ring, unflipped orientation:       {flipped_dark}/{used} = {flipped_dark / max(used, 1):.3f}")
    print("expected: served >= 0.95" if served_dark / max(used, 1) >= 0.95 else "WARNING: served < 0.95 — investigate flip/contour alignment")


if __name__ == "__main__":
    main()
