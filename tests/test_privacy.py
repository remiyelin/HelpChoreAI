"""Privacy durable checks: no initials as whole words in tracked files, no sealed-patient
(P3/P5) tracked data, no contributor model ids. Tokens are read from the git-ignored
private map at runtime and are never printed; failures name files only."""
import json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "private" / "initials_map.json"


def _tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def _whole(tok):
    return re.compile(r"(?<![A-Za-z])" + re.escape(tok) + r"(?![a-z])")


def test_no_initials_as_whole_words_in_tracked_files():
    if not MAP.exists():
        return  # map is local-only; CI without the map cannot run this check
    tokens = list(json.loads(MAP.read_text()).keys())
    pats = [_whole(t) for t in tokens]
    bad = []
    for rel in _tracked():
        if Path(rel).suffix.lower() in {".png", ".mp4", ".wav", ".p", ".pkl", ".webp", ".woff2"}: continue
        try:
            text = (ROOT / rel).read_bytes().decode("latin-1")
        except OSError:
            continue
        if any(p.search(text) for p in pats):
            bad.append(rel)
    assert not bad, f"initials as whole words in tracked files: {bad}"


SEALED_MANIFEST = re.compile(r"^data/fetch_manifest/holdout_P[35]_manifest\.json$")

def test_no_sealed_patient_tracked_data():
    # Sealed contract: the ONLY tracked P3/P5 artifacts allowed are the hashed holdout
    # manifests (hashes/counts, no entry names, no content). Anything else is a leak.
    bad = []
    for rel in _tracked():
        norm = rel.replace("\\", "/")
        if SEALED_MANIFEST.match(norm):
            continue
        parts = norm.split("/")
        if len(parts) >= 3 and parts[0] == "data" and parts[1] == "dev" and parts[2] in ("P3", "P5"):
            bad.append(rel)
        elif "holdout" in norm and any(p in ("P3", "P5") for p in re.split(r"[/._-]", norm)):
            bad.append(rel)
        elif norm.startswith("data/") and any(p in ("P3", "P5") for p in re.split(r"[/._-]", norm)):
            bad.append(rel)
    assert not bad, f"sealed-patient tracked paths: {bad}"


def test_no_contributor_model_ids():
    needle = "-contrib" + "utor"  # split so this test file itself never carries the literal in src/tools scans
    bad = []
    for base in ("src", "tools"):
        for f in (ROOT / base).rglob("*"):
            if f.is_file() and needle in f.read_bytes().decode("latin-1"):
                bad.append(str(f.relative_to(ROOT)))
    assert not bad, f"contributor model id present in: {bad}"
