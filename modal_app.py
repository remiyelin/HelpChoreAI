#!/usr/bin/env python3
"""Deploy the HelpChoreAI workstation to a public modal.run URL.

One-time setup (uses your Modal account / free credit):
  uv run --with modal modal token new
Deploy:
  uv run --with modal modal deploy modal_app.py
Then open the printed https://<user>--helpchoreai-web.modal.run URL.

Secrets: create a Modal secret named "helpchoreai-keys" (dashboard or CLI) with
META_MODEL_API_KEY / BASETEN_API_KEY, or leave unset — the app still runs fully
on pre-extracted tables/frames and reports live calls as BLOCKED.
The Checker private key is generated inside the container on first run (demo key).
"""
import pathlib
import modal

ROOT = pathlib.Path(__file__).parent
app = modal.App("helpchoreai")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy", "pandas", "scipy", "scikit-learn", "cryptography", "openai", "meta-sam-parser")
    .add_local_dir(ROOT / "src", "/root/HelpChoreAI/src")
    .add_local_dir(ROOT / "web", "/root/HelpChoreAI/web")
    .add_local_dir(ROOT / "tools", "/root/HelpChoreAI/tools")
    .add_local_file(ROOT / "pyproject.toml", "/root/HelpChoreAI/pyproject.toml")
    .add_local_dir(ROOT / "data" / "tables", "/root/HelpChoreAI/data/tables")
    .add_local_dir(ROOT / "data" / "fetch_manifest", "/root/HelpChoreAI/data/fetch_manifest")
    .add_local_dir(ROOT / "data" / "frames", "/root/HelpChoreAI/data/frames")
    .add_local_dir(ROOT / "data" / "dev", "/root/HelpChoreAI/data/dev")
)

try:
    keys = modal.Secret.from_name("helpchoreai-keys")
    secrets = [keys]
except Exception:
    secrets = []

@app.function(image=image, secrets=secrets, cpu=2, memory=2048, timeout=600)
@modal.web_server(8765, startup_timeout=120)
def web():
    import subprocess, sys
    subprocess.Popen([sys.executable, "/root/HelpChoreAI/src/server.py", "--port", "8765"],
                     cwd="/root/HelpChoreAI")
