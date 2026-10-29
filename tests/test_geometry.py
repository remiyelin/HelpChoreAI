"""Geometry durable tests: filled-area accuracy (both windings), exact square,
shifted-circle IoU band, row-span rebuild, and the old ray-caster over-fill regression."""
import math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import geometry


def ellipse_pts(a, b, cx=30.0, cy=30.0, n=72, reverse=False):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = [[cx + a * np.cos(x), cy + b * np.sin(x)] for x in t]
    return pts[::-1] if reverse else pts


def old_raycast_area(poly, h, w):
    """The deleted buggy expression, kept here ONLY to pin the regression."""
    pts = np.asarray(poly, dtype=float)
    yy, xx = np.mgrid[0:h, 0:w]
    inside = np.zeros((h, w), dtype=bool); x, y = pts[:, 0], pts[:, 1]; j = len(pts) - 1
    for i in range(len(pts)):
        cond = ((y[i] > yy) != (y[j] > yy)) & (xx < (x[j] - x[i]) * (yy - y[i]) / max(y[j] - y[i], 1e-9) + x[i])
        inside ^= cond; j = i
    return int(inside.sum())


def test_circle_and_ellipse_area_both_windings():
    for rev in (False, True):
        c = geometry.fill_contour(ellipse_pts(10, 10, reverse=rev), 61, 61)
        assert abs(geometry.area(c) - math.pi * 100) <= 0.05 * math.pi * 100
        e = geometry.fill_contour(ellipse_pts(13, 9, reverse=rev), 61, 61)
        assert abs(geometry.area(e) - math.pi * 13 * 9) <= 0.05 * math.pi * 13 * 9


def test_square_exact():
    sq = [[2, 2], [12, 2], [12, 12], [2, 12]]
    assert geometry.area(geometry.fill_contour(sq, 20, 20)) == 100  # exact continuous 10x10 area


def test_shifted_circle_iou_band():
    a = geometry.fill_contour(ellipse_pts(10, 10, cx=25, cy=25), 51, 51)
    b = geometry.fill_contour(ellipse_pts(10, 10, cx=28, cy=25), 51, 51)
    assert 0.6 < geometry.iou(a, b) < 0.8
    assert geometry.iou(a, a) == 1.0


def test_rowspans_rebuild_not_polygon():
    # Outline as _mask_outline emits: left edge rows top->bottom, right edge bottom->top.
    poly = [[5, 2], [5, 3], [5, 4], [9, 4], [9, 3], [9, 2]]
    m = geometry.mask_from_rowspans(poly, 8, 14)
    assert geometry.area(m) == 3 * 5  # rows 2..4, cols 5..9 inclusive
    assert geometry.area(geometry.mask_from_rowspans([], 8, 14)) == 0


def test_old_expression_overfills_ellipse():
    pts = ellipse_pts(13, 9)
    analytic = math.pi * 13 * 9
    new = geometry.area(geometry.fill_contour(pts, 61, 61))
    old = old_raycast_area(pts, 61, 61)
    assert abs(new - analytic) <= 0.05 * analytic
    assert old > 1.3 * analytic, f"regression pin lost: old={old} analytic={analytic:.0f}"
