#!/usr/bin/env python3
"""Generate frame targets for adjudication-queue cells from M10 pickles (RestrictedUnpickler only).
Output: data/frames/targets.json {patient: {date: [{cell, frame, pos_x}]}} sorted by confidence (queue order).
Run: uv run python tools/make_frame_targets.py
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from step2_analysis import RestrictedUnpickler

ROOT = Path(__file__).resolve().parent.parent
q = pd.read_csv(ROOT / "data" / "tables" / "adjudication_queue.csv")
out = {}
for (patient, date), g in q.groupby(["patient", "date"]):
    date = str(date)
    hits = list((ROOT / "data" / "dev" / patient).glob(f"{patient}__{date}_*__Offline__M10_results.p"))
    if not hits: continue
    with open(hits[0], "rb") as fh: obj = RestrictedUnpickler(fh, encoding="latin1").load()
    rows = []
    for r in g.itertuples():
        cell = int(r.cell)
        if cell >= len(obj["Frames"]): continue
        fr = np.asarray(obj["Frames"][cell]); mid = len(fr) // 2
        rows.append({"cell": cell, "frame": int(fr[mid]), "pos_x": round(float(np.asarray(obj["pos_x"][cell])[mid]), 1),
                     "confidence": float(r.confidence)})
    out.setdefault(patient, {})[date] = sorted(rows, key=lambda x: x["confidence"])
    print(patient, date, "targets", len(rows), "frame range", min(x["frame"] for x in rows), "-", max(x["frame"] for x in rows))
(ROOT / "data" / "frames").mkdir(parents=True, exist_ok=True)
(ROOT / "data" / "frames" / "targets.json").write_text(json.dumps(out, indent=1))
print("total targets", sum(len(v) for d in out.values() for v in d.values()))
