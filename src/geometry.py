#!/usr/bin/env python3
"""Single source of truth for contour/mask geometry.

fill_contour uses cv2.drawContours(thickness=-1) — the same filled-contour convention
as the authors' pipeline. mask_from_rowspans rebuilds a SAM mask from the outline
stored by meta_api._mask_outline (row spans, NOT a polygon — never ray-cast it).
The old ray-casting rasterizer divided by max(dy, 1e-9), losing the sign for
negative-dy edges and over-filling ~5x; it is deleted, do not reintroduce it.
"""
import cv2
import numpy as np


SS = 4  # supersampling factor for subpixel fill accuracy

def fill_contour(points, h, w):
    """Filled boolean mask (h, w) of a contour given as (x, y) points, either winding order.
    cv2.drawContours(thickness=-1) (authors' convention) drawn at 4x supersampling and
    majority-downscaled: plain 1x fill adds a full boundary ring (~+10% area on a 20-px
    cell), while the supersampled fill tracks the analytic area to ~2%."""
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3:
        return np.zeros((h, w), dtype=bool)
    big = np.zeros((h * SS, w * SS), dtype=np.uint8)
    cv2.drawContours(big, [np.rint(pts * SS).astype(np.int32).reshape(-1, 1, 2)],
                     contourIdx=-1, color=1, thickness=-1)
    return big.reshape(h, SS, w, SS).mean(axis=(1, 3)) > 0.5


def mask_from_rowspans(polygon, h, w):
    """Rebuild a mask from a _mask_outline outline: first half = left edge per row
    (top->bottom), second half = right edge per row (bottom->top). Fill left..right inclusive."""
    mask = np.zeros((h, w), dtype=bool)
    if not polygon:
        return mask
    mid = len(polygon) // 2
    left = {int(y): int(x) for x, y in polygon[:mid]}
    right = {int(y): int(x) for x, y in polygon[mid:]}
    for y, x0 in left.items():
        x1 = right.get(y, x0)
        if 0 <= y < h:
            mask[y, max(0, min(x0, x1)): min(w, max(x0, x1) + 1)] = True
    return mask


def mask_from_rows(rows, h, w):
    """Mask from stored row spans [[y, x0, x1], ...] (cache entries written by _sam_run)."""
    mask = np.zeros((h, w), dtype=bool)
    for y, x0, x1 in rows or []:
        if 0 <= int(y) < h:
            mask[int(y), max(0, int(x0)): min(w, int(x1) + 1)] = True
    return mask


def iou(a, b):
    a, b = np.asarray(a, dtype=bool), np.asarray(b, dtype=bool)
    union = int((a | b).sum())
    return float((a & b).sum() / union) if union else 0.0


def area(mask):
    return int(np.asarray(mask, dtype=bool).sum())
