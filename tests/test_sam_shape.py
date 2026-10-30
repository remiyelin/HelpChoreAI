"""SAM shape-stats durable tests: same-grid hull solidity <= 1 by construction (Condition 1)."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from sam_pilot import shape_stats


def test_solidity_never_exceeds_one_and_detects_concavity():
    crescent = np.zeros((40, 60), dtype=bool)
    yy, xx = np.mgrid[0:40, 0:60]
    crescent[(xx - 30) ** 2 + (yy - 20) ** 2 <= 15 ** 2] = True
    crescent[(xx - 38) ** 2 + (yy - 20) ** 2 <= 12 ** 2] = False  # bite -> concave
    s = shape_stats(crescent)
    assert 0 < s["solidity"] <= 1.0 and s["defects_gt1px"] >= 1 and s["area"] > 100


def test_solidity_of_filled_square_is_one():
    sq = np.zeros((30, 30), dtype=bool); sq[5:25, 5:25] = True
    s = shape_stats(sq)
    assert s["solidity"] <= 1.0 and s["solidity"] > 0.95 and s["defects_gt1px"] == 0
