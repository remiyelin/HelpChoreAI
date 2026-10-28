#!/usr/bin/env python3
"""Step 2 SAM 3.1 audit harness (BLOCKED until Meta Model API credentials exist).

Purpose: on sampled frames, compare SAM 3.1 masks against authors' per-cell contours
(Offline pickle `Contours`, loaded ONLY via RestrictedUnpickler) with IoU / boundary-F1.
This script refuses to run without credentials and never fabricates masks.

Required env (set in YOUR terminal, never committed):
  META_MODEL_API_KEY=...   (Meta Model API, SAM 3.1)
Optional: HELPCHORE_SAM_MODEL=sam-3.1

Run after credentials + opencv are available:
  uv run --with opencv-python python src/sam_audit.py --patient P1 --visit 0w --run M10 --cells 20
"""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from step2_analysis import RestrictedUnpickler  # numpy-only restricted unpickler

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", default="P1"); ap.add_argument("--visit", default="0w")
    ap.add_argument("--run", default="M10"); ap.add_argument("--cells", type=int, default=20)
    args = ap.parse_args()
    if not os.environ.get("META_MODEL_API_KEY"):
        print("BLOCKED: META_MODEL_API_KEY not set. SAM 3.1 audit cannot run; no masks generated.")
        print("Ground-truth side is ready: authors' contours load via RestrictedUnpickler (see step2_analysis.inspect_pickle).")
        return 2
    # With credentials: extract sampled frames from the run .avi (opencv), prompt SAM 3.1 per tracked-cell
    # centroid (from pickle pos_x/pos_y at that frame), rasterize authors' contour polygon, compute IoU.
    raise NotImplementedError("Wire Meta Model API SAM 3.1 call here once credentials are provisioned.")

if __name__ == "__main__":
    raise SystemExit(main())
