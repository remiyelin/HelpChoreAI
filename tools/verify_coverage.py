#!/usr/bin/env python3
"""Verify EVERY adjudication-queue cell renders a real strip + crop PNG via server.frame_png.
Run: uv run python tools/verify_coverage.py  (exit 1 if any cell lacks a valid PNG)
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import server

ROOT = Path(__file__).resolve().parent.parent
targets = json.loads((ROOT / "data" / "frames" / "targets.json").read_text())
total, ok, bad = 0, 0, []
for patient, dates in targets.items():
    for date, rows in dates.items():
        for r in rows:
            total += 1
            try:
                crop = server.frame_png(patient, date, int(r["cell"]), crop=True)
                strip = server.frame_png(patient, date, int(r["cell"]), crop=False)
                good = (crop and crop[0][:8] == b"\x89PNG\r\n\x1a\n" and strip and strip[0][:8] == b"\x89PNG\r\n\x1a\n"
                        and len(crop[1].get("contour_crop", [])) >= 3)
            except Exception as e:
                good, bad = False, bad + [f"{patient}/{date}/cell{r['cell']}: {type(e).__name__}"]
            if good: ok += 1
            elif len(bad) < 10: bad.append(f"{patient}/{date}/cell{r['cell']}")
print(f"coverage verify: {ok}/{total} queue cells render real strip+crop PNG")
if bad: print("FAILURES:", bad)
sys.exit(0 if ok == total else 1)
