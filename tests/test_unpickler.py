"""P-22: RestrictedUnpickler uses an exact allowlist and fails closed."""
import collections, io, pickle, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from step2_analysis import RestrictedUnpickler


def test_forbidden_class_raises():
    blob = pickle.dumps(collections.OrderedDict(a=1))
    with pytest.raises(pickle.UnpicklingError):
        RestrictedUnpickler(io.BytesIO(blob)).load()


def test_numpy_prefixed_but_unlisted_class_raises():
    import numpy as np
    blob = pickle.dumps(np.random.default_rng(0))
    with pytest.raises(pickle.UnpicklingError):
        RestrictedUnpickler(io.BytesIO(blob)).load()


def test_allowlisted_builtins_roundtrip():
    blob = pickle.dumps({"x": [1, (2, 3)]})
    out = RestrictedUnpickler(io.BytesIO(blob)).load()
    assert out == {"x": [1, (2, 3)]}
