#!/usr/bin/env python3
"""Last step before pushing. After the open-weight runs and the deploy:
  uv run --with pillow --with imageio-ffmpeg python tools/finalize.py --repo URL --live URL --video URL
Rebuilds web/demo from the current files, fills the result block and the links in README.md and
SUBMISSION.md, and renders the end card. Makes no model call. Prints the numbers for the video script.
"""
import argparse, csv, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def open_result():
    rows = list(csv.DictReader(open(ROOT / "data" / "tables" / "open_weight_parity.csv", encoding="utf-8")))
    same = sum(r["equal"] == "True" and r.get("signature_ok") == "True" for r in rows)
    lines = [f"Open weights: {same} of {len(rows)} reports signed in open-weight mode carry the same numbers as the cloud run."]
    hosts = []
    for p in sorted((ROOT / "logs").glob("tamper_benchmark_*.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        if "spark_open" in j and "paraphrase12" in j["spark_open"]:
            o, l = j["spark_open"], j["local_rules"]
            hosts.append(j.get("host"))
            lines.append(f"On {j.get('host')}: advice hidden in normal words stopped {o['paraphrase12']['hits']} of 12 (fixed rules {l['paraphrase12']['hits']} of 12); "
                         f"clean reports passed {o['clean12']['hits']} of 12.")
    return lines, same, len(rows), hosts


def fill(path, lines, links):
    s = path.read_text(encoding="utf-8")
    body = "\n\n".join(lines)
    s = re.sub(r"<!--open-result-->.*?<!--/open-result-->", f"<!--open-result-->\n{body}\n<!--/open-result-->", s, flags=re.S)
    for k, v in links.items():
        if v: s = s.replace(k, v)
    path.write_text(s, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=""); ap.add_argument("--live", default=""); ap.add_argument("--video", default="")
    a = ap.parse_args()
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_demo_pack.py")], cwd=ROOT, check=True)
    lines, same, total, hosts = open_result()
    links = {"REPO_URL": a.repo, "LIVE_URL": a.live, "VIDEO_URL": a.video}
    for name in ("README.md", "SUBMISSION.md"):
        fill(ROOT / name, lines, links)
    subprocess.run([sys.executable, str(ROOT / "tools" / "render_video_assets.py"), "--only", "v07", "--repo", a.repo, "--live", a.live], cwd=ROOT, check=True)
    left = [k for k in links if k in (ROOT / "README.md").read_text(encoding="utf-8") + (ROOT / "SUBMISSION.md").read_text(encoding="utf-8")]
    print("\nFor the video script:")
    for l in lines: print(" ", l)
    print(f"  Hosts tested: {len(hosts)} ({', '.join(str(h) for h in hosts)})")
    print("Links still empty:", ", ".join(left) if left else "none")


if __name__ == "__main__":
    main()
