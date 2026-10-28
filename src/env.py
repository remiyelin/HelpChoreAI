"""Minimal .env loader: project-root .env, existing environment wins. No secrets are ever printed."""
import os
from pathlib import Path

def load_env() -> dict:
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    loaded = {}
    if env_file.exists():
        for line in env_file.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
                loaded[key] = True
    # Meta docs use MODEL_API_KEY; hackathon convention here is META_MODEL_API_KEY. Accept both.
    if not os.environ.get("META_MODEL_API_KEY") and os.environ.get("MODEL_API_KEY"):
        os.environ["META_MODEL_API_KEY"] = os.environ["MODEL_API_KEY"]
    return loaded
