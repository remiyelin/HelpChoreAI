#!/usr/bin/env python3
"""Deploy the HelpChoreAI workstation to a public modal.run URL.

One-time setup (uses your Modal account / free credit):
  uv run --with modal modal token new
Deploy:
  uv run --with modal modal deploy modal_app.py
Then open the printed https://<user>--helpchoreai-web.modal.run URL.

Public by default: PUBLIC_MODE=1 (read-only cached demo, no live calls, write
endpoints disabled). Keys are attached ONLY when DEPLOY_WITH_KEYS=1 is set
explicitly at deploy time: create a Modal secret named "helpchoreai-keys"
(dashboard or CLI) with META_MODEL_API_KEY / BASETEN_API_KEY.
The Checker private key is generated inside the container on first run (demo key).
"""
import os
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

secrets = [modal.Secret.from_name("helpchoreai-keys")] if os.environ.get("DEPLOY_WITH_KEYS") == "1" else []

@app.function(image=image, secrets=secrets, cpu=2, memory=2048, timeout=600)
@modal.web_server(8765, startup_timeout=120)
def web():
    import subprocess, sys
    os.environ.setdefault("PUBLIC_MODE", "1")  # read-only cached demo unless explicitly overridden at deploy
    subprocess.Popen([sys.executable, "/root/HelpChoreAI/src/server.py", "--port", "8765"],
                     cwd="/root/HelpChoreAI", env=os.environ.copy())
