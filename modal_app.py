#!/usr/bin/env python3
"""Deploy the public HelpChoreAI page to a modal.run URL.

The image holds web/ only: static files, a signed demo pack, no keys, no pickles, no model calls.
The viewer's browser verifies every signature itself.

One-time setup:  uv run --with modal modal token new
Deploy:          uv run --with modal modal deploy modal_app.py
Then open the printed https://<user>--helpchoreai-web.modal.run URL.
"""
import pathlib
import modal

ROOT = pathlib.Path(__file__).parent
app = modal.App("helpchoreai")

image = modal.Image.debian_slim(python_version="3.12").add_local_dir(ROOT / "web", "/root/web")


@app.function(image=image, cpu=0.25, memory=256, timeout=600)
@modal.concurrent(max_inputs=100)
@modal.web_server(8000, startup_timeout=60)
def web():
    import subprocess
    # Modal needs the server on the external interface, not on localhost.
    subprocess.Popen("python -m http.server 8000 --bind 0.0.0.0 --directory /root/web", shell=True)
