#!/usr/bin/env python3
"""HelpChoreAI Step 1 (external-terminal fallback): Figshare 5793482 Range/ZIP64 ingest.
Same policy as tools/figshare_ingest.mjs: dev P1,P2,P4 extract Results/*.txt + 3 contour samples;
holdout P3,P5 sealed (hashed manifest only). Run:  python tools/figshare_ingest.py [--patient P1]
Requires: pip install requests
"""
import hashlib, io, json, re, struct, sys, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
_MAP_PATH = ROOT / "private" / "initials_map.json"
if not _MAP_PATH.exists():
    raise SystemExit("private/initials_map.json missing: create the git-ignored initials -> P-code map before running ingest")
CODE = json.loads(_MAP_PATH.read_text())
import requests

API = "https://api.figshare.com/v2/collections/5793482/articles?page_size=100"
DEV = {"P1", "P2", "P4"}

def article_files():
    out = []
    for a in requests.get(API, timeout=60).json():
        d = requests.get(f"https://api.figshare.com/v2/articles/{a['id']}", timeout=60).json()
        f = (d.get("files") or [{}])[0]
        out.append({"id": a["id"], "title": a["title"], "size": f.get("size"),
                    "md5": f.get("computed_md5"), "url": f.get("download_url")})
    return out

class SplitReader:
    def __init__(self, parts):
        self.parts, self.starts, acc = parts, [], 0
        for p in parts:
            self.starts.append(acc); acc += p["size"]
        self.total = acc
    def range(self, start, end):
        end = min(end, self.total); pos, chunks = start, []
        while pos < end:
            i = max(j for j, s in enumerate(self.starts) if s <= pos)
            p, off = self.parts[i], pos - self.starts[i]
            take = min(p["size"] - off, end - pos)
            r = requests.get(p["url"], headers={"Range": f"bytes={off}-{off+take-1}"}, timeout=300)
            r.raise_for_status(); chunks.append(r.content[:take]); pos += take
        return b"".join(chunks)

def main():
    only = next((a.split("=")[1] for a in sys.argv if a.startswith("--patient=")), None)
    files = article_files()
    (ROOT / "data/fetch_manifest").mkdir(parents=True, exist_ok=True)
    (ROOT / "data/fetch_manifest/figshare_files.json").write_text(json.dumps(files, indent=1))
    groups = {}
    for f in files:
        m = re.search(r"shape_analysis_(P\d+)\.zip(?:\.(\d+))?", f["title"])
        if m: groups.setdefault(m.group(1), []).append({**f, "part": int(m.group(2) or 1)})
    for patient in sorted(groups):
        if only and patient != only: continue
        parts = sorted(groups[patient], key=lambda x: x["part"])
        rdr = SplitReader(parts)
        tail_len = min(32 * 1024 * 1024, rdr.total)
        tail = rdr.range(rdr.total - tail_len, rdr.total)
        idx = tail.rfind(struct.pack("<I", 0x06064B50))
        if idx < 0: raise SystemExit(f"{patient}: ZIP64 EOCD not found, widen tail window")
        cd_size, cd_off = struct.unpack_from("<QQ", tail, idx + 40)[0], struct.unpack_from("<Q", tail, idx + 48)[0]
        cd = rdr.range(cd_off, cd_off + cd_size)
        # Parse names/sizes via zipfile on the central directory is non-trivial; reuse manual parse:
        entries, p = [], 0
        while p + 46 <= len(cd) and cd[p:p+4] == struct.pack("<I", 0x02014B50):
            method, csize, usize, lho = struct.unpack_from("<HIII", cd, p + 10)[0], struct.unpack_from("<I", cd, p+20)[0], struct.unpack_from("<I", cd, p+24)[0], struct.unpack_from("<I", cd, p+42)[0]
            nlen, elen, clen = struct.unpack_from("<HHH", cd, p + 28)
            name = cd[p+46:p+46+nlen].decode("utf8", "replace"); extra = cd[p+46+nlen:p+46+nlen+elen]
            q = 0
            while q + 4 <= len(extra):
                tag, ln = struct.unpack_from("<HH", extra, q)
                if tag == 0x0001:
                    r = q + 4
                    if usize == 0xFFFFFFFF: usize = struct.unpack_from("<Q", extra, r)[0]; r += 8
                    if csize == 0xFFFFFFFF: csize = struct.unpack_from("<Q", extra, r)[0]; r += 8
                    if lho == 0xFFFFFFFF: lho = struct.unpack_from("<Q", extra, r)[0]; r += 8
                q += 4 + ln
            entries.append({"name": name, "method": method, "csize": csize, "usize": usize, "lho": lho})
            p += 46 + nlen + elen + clen
        print(f"{patient}: entries={len(entries)} totalGB={rdr.total/1e9:.1f}")
        if patient not in DEV:
            manifest = {"patient": patient, "sealed": True,
                        "entry_count": len(entries),
                        "cd_sha256": hashlib.sha256(cd).hexdigest(),
                        "entry_names_sha256": hashlib.sha256("\n".join(e["name"] for e in entries).encode()).hexdigest()}
            (ROOT / f"data/fetch_manifest/holdout_{patient}_manifest.json").write_text(json.dumps(manifest, indent=1))
            print("  SEALED manifest written"); continue
        outdir = ROOT / f"data/dev/{patient}"; outdir.mkdir(parents=True, exist_ok=True)
        def extract(e):
            lh = rdr.range(e["lho"], e["lho"] + 30)
            nl, el = struct.unpack_from("<HH", lh, 26)
            raw = rdr.range(e["lho"] + 30 + nl + el, e["lho"] + 30 + nl + el + e["csize"])
            return zipfile.ZipFile(io.BytesIO(b"PK\x03\x04" + lh[4:] + raw)).open(e["name"]).read() if False else (
                __import__("zlib").decompress(raw, -15) if e["method"] == 8 else raw)
        def deidentify(name):
            for init, p in CODE.items():
                if re.search(rf"(^|/){init}(?=[/(_])|_{init}(?=\()", name) and p != patient:
                    return None
            out = name
            for init, p in CODE.items():
                out = re.sub(rf"(^|/){init}(?=[/(_])", rf"\g<1>{p}", out)
                out = re.sub(rf"_{init}(?=\()", f"_{p}", out)
            return out
        for e in [x for x in entries if re.search(r"results_[^/]+\.txt$", x["name"], re.I)] + \
                 [x for x in entries if x["name"].endswith("_contours.txt")][:3]:
            safe = deidentify(e["name"])
            if safe is None:
                continue
            data = extract(e)
            (outdir / safe.replace("/", "__").replace("\\", "__")).write_bytes(data)
            print(f"  extracted {safe} ({len(data)} B) sha256={hashlib.sha256(data).hexdigest()[:16]}")

if __name__ == "__main__":
    main()
