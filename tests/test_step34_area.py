"""Contour-area durable tests: shoelace correctness + pickle-Area divergence guard."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from step34_model import contour_area_mean_std, shoelace_area


def test_shoelace_square_and_triangle():
    assert shoelace_area([[0, 0], [10, 0], [10, 10], [0, 10]]) == 100.0
    assert shoelace_area([[0, 0], [4, 0], [0, 3]]) == 6.0
    assert np.isnan(shoelace_area([[0, 0], [1, 1]]))  # degenerate -> NaN, never a fake area


def test_contour_area_ignores_pickle_area_field():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    obj = {"Contours": [[sq, sq]], "Area": [[9999.0, 1.0]]}  # doubled/misaligned pickle field
    mean, std = contour_area_mean_std(obj, 0)
    assert mean == 100.0 and std == 0.0
