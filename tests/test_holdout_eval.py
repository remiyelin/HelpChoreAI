"""P-22: sealed_results.csv is reproducible from the frozen eval-v1 pipeline."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

ROOT = Path(__file__).parent.parent
TABLES = ROOT / "data" / "tables"


@pytest.mark.skipif(not (TABLES / "per_run_holdout.csv").exists(),
                    reason="holdout data absent on this checkout")
def test_sealed_results_recreated_to_6_decimals():
    import step12_holdout_eval
    got = step12_holdout_eval.recreate_sealed_results()
    want = pd.read_csv(TABLES / "sealed_results.csv")
    assert list(got.columns) == list(want.columns)
    assert len(got) == len(want)
    for col in ("patient", "from", "to", "treatment", "decision", "naive_decision"):
        assert (got[col].astype(str) == want[col].astype(str)).all(), col
    for col in ("delta_raw", "delta_adj", "RCV95", "from_skip_rate", "to_skip_rate"):
        assert np.allclose(got[col], want[col], atol=5e-7), col
