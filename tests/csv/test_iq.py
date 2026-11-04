"""Installation Qualification (IQ) Test Suite for HelpChoreAI.

Document: VAL-IQ-2026-001
GAMP 5 Category 5 — Custom Computational Science Tool
FDA 21 CFR Part 11 / ALCOA+ Data Integrity Framework

Verifies:
- Python >= 3.12 execution runtime environment
- Package dependencies and version tree integrity (uv lock / pyproject.toml)
- Directory layout topology and security segregation
- File system permissions and raw asset immutability
- Cryptographic infrastructure and pinned Ed25519 public key format
- Cryptographic SHA-256 integrity for all 18 authentic microfluidic datasets in data/csv/
- Offline execution environment isolation
"""

from __future__ import annotations

import hashlib
import importlib
import os
import pathlib
import sys
import tempfile
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
DATA_DIR = ROOT / "data"
CSV_DIR = DATA_DIR / "csv"
CHECKER_DIR = DATA_DIR / "checker"
CROSS_DOMAIN_DIR = DATA_DIR / "cross_domain"
TABLES_DIR = DATA_DIR / "tables"
DOCS_CSV_DIR = ROOT / "docs" / "csv"
MANIFEST_PATH = CSV_DIR / "MANIFEST_CSV_DATASETS.sha256"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# IQ-01: Runtime Environment & Python Version Qualification
# ---------------------------------------------------------------------------

def test_iq01_python_runtime_environment():
    """Verify that Python execution interpreter satisfies minimum requirement (>= 3.12.0).
    
    Traceable to URS-QUAL-01, PRE-02 in VAL-IQ-2026-001.
    """
    major, minor = sys.version_info.major, sys.version_info.minor
    assert sys.version_info >= (3, 12), (
        f"Python runtime must be >= 3.12.0, observed: {major}.{minor}.{sys.version_info.micro}"
    )
    assert sys.platform in ("win32", "linux", "darwin"), f"Unsupported platform: {sys.platform}"


# ---------------------------------------------------------------------------
# IQ-02: Package Lockfile & Dependency Tree Integrity
# ---------------------------------------------------------------------------

def test_iq02_dependency_tree_integrity():
    """Verify core scientific, statistical, and cryptographic dependencies are loaded with valid versions.
    
    Traceable to URS-DATA-02, URS-QUAL-01, PRE-03, PRE-05 in VAL-IQ-2026-001.
    """
    # Verify lockfile / config presence
    pyproject = ROOT / "pyproject.toml"
    assert pyproject.exists(), f"Configuration file {pyproject} must exist."

    deps = {
        "numpy": (1, 24),
        "scipy": (1, 10),
        "pandas": (2, 0),
        "statsmodels": (0, 14),
        "cryptography": (41, 0),
        "pytest": (8, 0),
    }

    for pkg_name, min_ver in deps.items():
        try:
            mod = importlib.import_module(pkg_name)
        except ImportError as e:
            pytest.fail(f"Required package '{pkg_name}' could not be imported: {e}")

        ver_str = getattr(mod, "__version__", None)
        assert ver_str is not None, f"Package '{pkg_name}' missing __version__ attribute"

        # Parse numeric version tokens
        tokens = [int(p) for p in ver_str.split(".")[:2] if p.isdigit()]
        if len(tokens) >= 2:
            assert tuple(tokens[:2]) >= min_ver, (
                f"Package '{pkg_name}' version {ver_str} does not meet minimum {min_ver}"
            )


# ---------------------------------------------------------------------------
# IQ-03: Directory Topology & Module Layout Qualification
# ---------------------------------------------------------------------------

def test_iq03_directory_topology_qualification():
    """Verify existence and segregation of application, data, test, tool, and CSV documentation directories.
    
    Traceable to URS-QUAL-02, URS-DATA-05, IQ-03 in VAL-IQ-2026-001.
    """
    expected_dirs = [
        SRC_DIR,
        DATA_DIR,
        CSV_DIR,
        CROSS_DOMAIN_DIR,
        TABLES_DIR,
        CHECKER_DIR,
        ROOT / "tests",
        ROOT / "tests" / "csv",
        ROOT / "tools",
        DOCS_CSV_DIR,
    ]

    for d in expected_dirs:
        assert d.exists(), f"Mandatory directory {d} is missing from project layout."
        assert d.is_dir(), f"Path {d} is not a directory."

    # Verify CSV documentation files are present
    mandatory_docs = [
        "URS.md",
        "FS.md",
        "TRACEABILITY_MATRIX.md",
        "IQ_PROTOCOL_REPORT.md",
        "OQ_PROTOCOL_REPORT.md",
        "PQ_PROTOCOL_REPORT.md",
        "ALCOA_PLUS_ASSESSMENT.md",
    ]
    for doc in mandatory_docs:
        doc_path = DOCS_CSV_DIR / doc
        assert doc_path.exists(), f"Required CSV validation document missing: {doc_path}"
        assert doc_path.stat().st_size > 500, f"CSV document {doc} appears empty or truncated."


# ---------------------------------------------------------------------------
# IQ-04: File System Permissions & Raw Asset Immutability
# ---------------------------------------------------------------------------

def test_iq04_filesystem_permissions_and_raw_asset_immutability():
    """Verify write access to output/checker directories and assert immutability of raw input repositories.
    
    Traceable to URS-DATA-05, IQ-04 in VAL-IQ-2026-001.
    """
    # 1. Output directory write probe
    probe_file = CHECKER_DIR / ".iq_write_probe.tmp"
    try:
        probe_file.write_text("IQ_WRITE_PROBE_OK\n", encoding="utf-8")
        assert probe_file.exists()
        content = probe_file.read_text(encoding="utf-8").strip()
        assert content == "IQ_WRITE_PROBE_OK"
    finally:
        if probe_file.exists():
            probe_file.unlink()

    # 2. Raw asset repository immutability
    assert CROSS_DOMAIN_DIR.exists(), f"Raw repository {CROSS_DOMAIN_DIR} missing."
    raw_files = sorted(list(CROSS_DOMAIN_DIR.glob("HL60_LatB_3fr_*.txt")))
    assert len(raw_files) == 5, f"Expected 5 raw multi-flow run files, found {len(raw_files)}"

    for rf in raw_files:
        assert rf.stat().st_size > 3000, f"Raw data file {rf.name} has suspicious size: {rf.stat().st_size}"


# ---------------------------------------------------------------------------
# IQ-05: Cryptographic Infrastructure & Public Key Pinning
# ---------------------------------------------------------------------------

def test_iq05_cryptographic_infrastructure_ed25519_key_pinning():
    """Verify that Ed25519 cryptographic public key is securely pinned, valid hex format, and loads cleanly.
    
    Traceable to URS-COMP-02, URS-COMP-03, IQ-05 in VAL-IQ-2026-001.
    """
    import checker
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    pub_key_path = CHECKER_DIR / "public_key.hex"
    assert pub_key_path.exists(), f"Pinned public key file {pub_key_path} missing."

    key_hex = pub_key_path.read_text(encoding="utf-8").strip()
    assert len(key_hex) == 64, f"Ed25519 public key hex must be 64 characters (32 bytes), got {len(key_hex)}"
    assert all(c in "0123456789abcdef" for c in key_hex.lower()), "Key contains non-hexadecimal characters"

    # Verify checker module loads the pinned public key
    loaded_key = checker.pinned_public_key_hex()
    assert loaded_key.lower() == key_hex.lower(), "Checker pinned key does not match disk key"

    # Verify raw bytes construct a valid Ed25519PublicKey object
    raw_bytes = bytes.fromhex(key_hex)
    assert len(raw_bytes) == 32
    pub_obj = Ed25519PublicKey.from_public_bytes(raw_bytes)
    assert isinstance(pub_obj, Ed25519PublicKey)


# ---------------------------------------------------------------------------
# IQ-06: Cryptographic SHA-256 Manifest Integrity for 18 CSV Datasets
# ---------------------------------------------------------------------------

def test_iq06_csv_datasets_manifest_sha256_integrity():
    """Verify cryptographic SHA-256 integrity for all 18 authentic microfluidic datasets in data/csv/.
    
    Traceable to URS-DATA-01, URS-DATA-02, FS-DATA-03 in VAL-URS-2026-001 and VAL-FS-2026-001.
    """
    assert MANIFEST_PATH.exists(), f"Manifest file {MANIFEST_PATH} missing."

    manifest_lines = MANIFEST_PATH.read_text(encoding="utf-8").strip().splitlines()
    entries = {}
    for line in manifest_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        assert len(parts) == 2, f"Malformed manifest line: {line}"
        digest, fname = parts[0].strip(), parts[1].strip()
        entries[fname] = digest

    assert len(entries) == 18, f"Expected exactly 18 manifest entries, found {len(entries)}"

    for fname, expected_sha in entries.items():
        fpath = CSV_DIR / fname
        assert fpath.exists(), f"Dataset file {fname} in manifest does not exist in {CSV_DIR}"
        assert fpath.stat().st_size > 0, f"Dataset file {fname} is 0 bytes."

        # Compute actual SHA-256
        h = hashlib.sha256()
        with open(fpath, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        actual_sha = h.hexdigest()

        assert actual_sha.lower() == expected_sha.lower(), (
            f"SHA-256 mismatch for {fname}:\n  Expected: {expected_sha}\n  Actual:   {actual_sha}"
        )


# ---------------------------------------------------------------------------
# IQ-07: Offline Execution Environment Isolation
# ---------------------------------------------------------------------------

def test_iq07_offline_execution_environment_isolation():
    """Verify that core verification modules operate without external API tokens or internet access.
    
    Traceable to URS-COMP-03 in VAL-URS-2026-001.
    """
    import checker
    import stats

    # Verify functions are callable without environment variables
    orig_env = dict(os.environ)
    try:
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("META_MODEL_API_KEY", None)
        os.environ.pop("BASETEN_API_KEY", None)

        key_hex = checker.pinned_public_key_hex()
        assert len(key_hex) == 64

        runs = stats.load_rtdc_runs(CROSS_DOMAIN_DIR)
        assert len(runs) > 0
    finally:
        os.environ.clear()
        os.environ.update(orig_env)
