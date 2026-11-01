#!/usr/bin/env python3
"""Render the demo video clips from web/demo and the extracted frames. No model call, no sound.
Run: uv run --with pillow --with imageio-ffmpeg python tools/render_video_assets.py [--only v01,v04] [--repo URL] [--live URL]
Output: docs/media/video/*.mp4 (1920x1080, 30 fps, H.264) and thumb.png
"""
import argparse, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DEMO = ROOT / "web" / "demo"
OUT = ROOT / "docs" / "media" / "video"
W, H, FPS = 1920, 1080, 30
BG, PANEL, LINE, INK, MUTED = (20, 15, 11), (34, 25, 18), (65, 50, 38), (249, 246, 243), (178, 161, 147)
AMBER, TEAL, RED, DEV, SEALED = (36, 165, 245), (191, 212, 45), (82, 90, 255), (238, 148, 74), (152, 95, 222)
FONTS = {"sans": ["C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf"], "bold": ["C:/Windows/Fonts/seguisb.ttf", "DejaVuSans-Bold.ttf"],
         "mono": ["C:/Windows/Fonts/consola.ttf", "DejaVuSansMono.ttf"], "serif": ["C:/Windows/Fonts/georgia.ttf", "DejaVuSerif.ttf"]}
_cache = {}


def rgb(c):
    return (c[2], c[1], c[0])


def label(txt, size, color=INK, face="sans"):
    k = (txt, size, color, face)
    if k not in _cache:
        for name in FONTS[face]:
            try: f = ImageFont.truetype(name, size); break
            except OSError: continue
        l, t, r, b = f.getbbox(txt)
        im = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((2 - l, 2 - t), txt, font=f, fill=rgb(color) + (255,))
        _cache[k] = np.array(im)
    return _cache[k]


def put(frame, rgba, x, y, anchor="lt", alpha=1.0):
    h, w = rgba.shape[:2]
    x = int(x - (w / 2 if anchor[0] == "m" else w if anchor[0] == "r" else 0))
    y = int(y - (h / 2 if anchor[1] == "m" else h if anchor[1] == "b" else 0))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1: return
    src = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = src[..., 3:4].astype(float) / 255 * alpha
    frame[y0:y1, x0:x1] = (frame[y0:y1, x0:x1] * (1 - a) + src[..., 2::-1] * a).astype(np.uint8)


def blank():
    return np.full((H, W, 3), BG, np.uint8)


class Clip:
    def __init__(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.p = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                                   "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                   "-crf", "18", "-preset", "medium", str(OUT / f"{name}.mp4")], stdin=subprocess.PIPE)
        self.n = 0

    def add(self, frame, repeat=1):
        for _ in range(repeat):
            self.p.stdin.write(frame.tobytes()); self.n += 1

    def close(self):
        self.p.stdin.close(); self.p.wait()
        print(f"{self.name}: {self.n / FPS:.1f}s")


def ease(t):
    return 1 - (1 - min(max(t, 0), 1)) ** 3


# P3 chart ---------------------------------------------------------------------------------------
def p3():
    v = [r for r in json.loads((DEMO / "visits.json").read_text(encoding="utf-8")) if r["patient"] == "P3"]
    return sorted(v, key=lambda r: r["week"])


def chart_geometry(rows, right=1800):
    x0, x1, y0, y1 = 150, right, 110, 930
    wmax = rows[-1]["week"]
    return (lambda w: x0 + (x1 - x0) * w / wmax), (lambda v: y1 - (y1 - y0) * v / .45), x0, x1, y0, y1


def chart_base(rows, right=1800):
    f = blank()
    X, Y, x0, x1, y0, y1 = chart_geometry(rows, right)
    for v in (.1, .2, .3, .4):
        cv2.line(f, (x0, int(Y(v))), (x1, int(Y(v))), LINE, 1, cv2.LINE_AA)
        put(f, label(f"{int(v * 100)}%", 26, MUTED, "mono"), x0 - 18, Y(v), "rm")
    for r in rows:
        if r["week"] in (0, 19, 26, 31):
            put(f, label(f"week {r['week']}", 28, MUTED), X(r["week"]), y1 + 30, "mm")
    return f


def chart_frame(rows, progress, right=1800, labels=True):
    """progress 0..1 runs along the weeks."""
    f = chart_base(rows, right)
    X, Y, *_ = chart_geometry(rows, right)
    end = rows[-1]["week"] * progress
    pts = [(r["week"], r["raw"]) for r in rows]
    for (a, va), (b, vb) in zip(pts, pts[1:]):
        if a >= end: break
        t = min(1, (end - a) / (b - a))
        c = AMBER if a >= 19 else TEAL
        cv2.line(f, (int(X(a)), int(Y(va))), (int(X(a + (b - a) * t)), int(Y(va + (vb - va) * t))), c, 5, cv2.LINE_AA)
    for w, val in pts:
        if w <= end + .01:
            cv2.circle(f, (int(X(w)), int(Y(val))), 13 if w == 26 else 8, AMBER if w >= 26 else TEAL, -1, cv2.LINE_AA)
    if labels:
        for w, size, dy, color in ((19, 64, 62, INK), (26, 130, -86, AMBER), (31, 64, 62, INK)):
            if w <= end + .01:
                r = next(x for x in rows if x["week"] == w)
                put(f, label(f"{round(r['raw'] * 100)}%", size, color, "bold"), min(X(w), right - 30), Y(r["raw"]) + dy, "mm")
    return f


def v01():
    rows = p3(); c = Clip("v01_chart")
    n = 8 * FPS
    for i in range(n): c.add(chart_frame(rows, (i + 1) / n))
    last = chart_frame(rows, 1)
    c.add(last, 3 * FPS); c.close()
    cv2.imwrite(str(OUT / "thumb.png"), last)


def card(f, x, y, w, h):
    cv2.rectangle(f, (int(x), y), (int(x + w), y + h), PANEL, -1)
    cv2.rectangle(f, (int(x), y), (int(x + w), y + h), AMBER, 3, cv2.LINE_AA)
    put(f, label("No decision", 84, AMBER, "bold"), x + 40, y + 110, "lm")
    put(f, label("More than a third of the cells", 38, INK), x + 40, y + 210, "lm")
    put(f, label("could not be read.", 38, INK), x + 40, y + 262, "lm")


def v02():
    rows = p3(); c = Clip("v02_no_decision")
    n = int(.8 * FPS); cw = 660
    for i in range(n):
        t = ease((i + 1) / n)
        f = chart_frame(rows, 1, right=int(1800 - 640 * t)); card(f, W - (cw + 60) * t, 380, cw, 330); c.add(f)
    f = chart_frame(rows, 1, right=1160); card(f, W - cw - 60, 380, cw, 330)
    c.add(f, 4 * FPS); c.close()


# Cells --------------------------------------------------------------------------------------------
def v03():
    import server
    clip_path = ROOT / "data" / "frames" / "clips" / "P1_20171212_1324_1428.mp4"
    obj = server.load_pickle("P1", "20171212")
    cell = 9
    fr = np.asarray(obj["Frames"][cell]); px = np.asarray(obj["pos_x"][cell], float)
    cap = cv2.VideoCapture(str(clip_path)); frames = []
    while True:
        ok, im = cap.read()
        if not ok: break
        frames.append(im)
    cap.release()
    seq = [(frames[int(a) - 1324], float(b)) for a, b in zip(fr, px) if 0 <= int(a) - 1324 < len(frames)]
    span = 240; scale = W / span; out_h = int(48 * scale)
    xs = np.convolve([s[1] for s in seq], np.ones(5) / 5, mode="same")
    c = Clip("v03_cells")
    total = 8 * FPS
    for i in range(total):
        k = i / total * (len(seq) - 1)
        a = int(k); im = seq[a][0]
        cx = float(np.clip(xs[a] + (xs[min(a + 1, len(seq) - 1)] - xs[a]) * (k - a), span / 2, 1280 - span / 2))
        crop = cv2.getRectSubPix(im, (span, 48), (cx, 24))
        big = cv2.resize(crop, (W, out_h), interpolation=cv2.INTER_NEAREST)
        f = blank(); y = (H - out_h) // 2; f[y:y + out_h] = big
        c.add(f)
    c.close()


def resample(poly, n=360):
    p = np.asarray(poly + [poly[0]], float)
    seg = np.hypot(*np.diff(p, axis=0).T); s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def aligned(a, b):
    """Rotate b so that point i of b sits close to point i of a."""
    best = min(range(len(b)), key=lambda k: np.sum((a - np.roll(b, -k, axis=0)) ** 2))
    return np.roll(b, -best, axis=0)


def v04():
    cells = json.loads((DEMO / "cells" / "index.json").read_text(encoding="utf-8"))
    c0 = next(x for x in cells if x["id"] == "P1-8w-122")
    img = cv2.imread(str(DEMO / "cells" / f"{c0['id']}.png"), cv2.IMREAD_GRAYSCALE)
    S = 16; bw, bh = c0["w"] * S, c0["h"] * S; ox, oy = (W - bw) // 2, 60
    base = blank()
    base[oy:oy + bh, ox:ox + bw] = cv2.cvtColor(cv2.resize(img, (bw, bh), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
    A = resample(c0["stored"]); B = aligned(A, resample(c0["sam"]))
    P = lambda q: np.int32(np.round((q * S + [ox, oy]) * 8))  # 3 fractional bits

    def draw(f, q, color, upto=None):
        pts = P(q[:upto] if upto else q).reshape(-1, 1, 2)
        cv2.polylines(f, [pts], upto is None, color, 3, cv2.LINE_AA, shift=3)

    def caption(f, big, small, color):
        put(f, label(big, 54, color, "bold"), W / 2, oy + bh + 66, "mm")
        put(f, label(small, 32, MUTED), W / 2, oy + bh + 128, "mm")

    c = Clip("v04_outline")
    c.add(base, 2 * FPS)
    for i in range(FPS):
        f = base.copy(); draw(f, A, INK, max(2, int(len(A) * (i + 1) / FPS))); c.add(f)
    f = base.copy(); draw(f, A, INK); caption(f, "Stored outline: 0 dents", "A smooth outline cannot show spikes", INK)
    c.add(f, 3 * FPS)
    n = int(1.5 * FPS)
    for i in range(n):
        t = ease((i + 1) / n); f = base.copy()
        col = tuple(int(INK[k] + (AMBER[k] - INK[k]) * t) for k in range(3))
        draw(f, A + (B - A) * t, col); c.add(f)
    f = base.copy(); draw(f, B, AMBER); caption(f, f"SAM 3.1: {c0['dents']} dents", "It follows the real edge", AMBER)
    c.add(f, 4 * FPS); c.close()


def v05():
    d = json.loads((DEMO / "flow.json").read_text(encoding="utf-8"))
    x0, x1, y0, y1 = 170, 1820, 80, 900
    xs = np.log([p[1] for p in d["points"]]); lo, hi = xs.min(), xs.max()
    X = lambda f: x0 + (x1 - x0) * (np.log(f) - lo) / (hi - lo)
    Y = lambda v: y1 - (y1 - y0) * v
    base = blank()
    for v in (0, .5, 1):
        cv2.line(base, (x0, int(Y(v))), (x1, int(Y(v))), LINE, 1, cv2.LINE_AA)
        put(base, label(f"{int(v * 100)}%", 26, MUTED, "mono"), x0 - 18, Y(v), "rm")
    put(base, label("slower", 30, MUTED), x0, y1 + 42, "lm")
    put(base, label("faster flow", 30, MUTED), x1, y1 + 42, "rm")
    put(base, label("spiky cells", 30, MUTED), x0, y0 - 40, "lm")

    def dots(f, who):
        for p in d["points"]:
            if p[0] != who: continue
            x, y = int(X(p[1])), int(Y(p[2]))
            if who == "dev": cv2.circle(f, (x, y), 4, DEV, -1, cv2.LINE_AA)
            else: cv2.fillPoly(f, [np.array([[x, y - 5], [x + 5, y], [x, y + 5], [x - 5, y]])], SEALED, cv2.LINE_AA)
        return f

    def curve(f, who, frac, color):
        c0 = d["fits"][who]["curve"]; n = max(2, int(len(c0) * frac))
        cv2.polylines(f, [np.array([[int(X(a)), int(Y(b))] for a, b in c0[:n]], np.int32)], False, color, 5, cv2.LINE_AA)

    c = Clip("v05_flow")
    a = dots(base.copy(), "dev"); b = dots(a.copy(), "sealed")
    for i in range(FPS): c.add(cv2.addWeighted(base, 1 - (i + 1) / FPS, a, (i + 1) / FPS, 0))
    c.add(a, 2 * FPS // 1)
    for i in range(FPS): c.add(cv2.addWeighted(a, 1 - (i + 1) / FPS, b, (i + 1) / FPS, 0))
    for i in range(2 * FPS):
        f = b.copy(); curve(f, "dev", (i + 1) / (2 * FPS), DEV); curve(f, "sealed", (i + 1) / (2 * FPS), SEALED); c.add(f)
    f = b.copy(); curve(f, "dev", 1, DEV); curve(f, "sealed", 1, SEALED)
    put(f, label("same slope: \u22120.32", 72, INK, "bold"), x1, y0 + 40, "rm")
    cv2.circle(f, (x1 - 470, y0 + 112), 8, DEV, -1, cv2.LINE_AA)
    put(f, label("3 patients", 32, INK), x1 - 450, y0 + 112, "lm")
    cv2.fillPoly(f, [np.array([[x1 - 250, y0 + 102], [x1 - 240, y0 + 112], [x1 - 250, y0 + 122], [x1 - 260, y0 + 112]])], SEALED, cv2.LINE_AA)
    put(f, label("2 sealed patients", 32, INK), x1, y0 + 112, "rm")
    c.add(f, 4 * FPS); c.close()


def v06():
    pairs = json.loads((DEMO / "pairs.json").read_text(encoding="utf-8"))
    groups = [("confirmed", "confirmed", TEAL, True), ("ruled_out", "ruled out", MUTED, False), ("refused", "refused", AMBER, True), ("missed", "missed by normal reading", TEAL, False)]
    total = sum(1 for p in pairs if p["naive_alarm"])
    c = Clip("v06_tiles")

    def scene(upto):
        f = blank()
        put(f, label(f"{total} alarms in {len(pairs)} visit pairs", 64, INK, "bold"), 170, 170, "lm")
        y = 330
        for i, (key, name, color, fill) in enumerate(groups[:upto]):
            n = sum(1 for p in pairs if p["outcome"] == key)
            put(f, label(("+" if key == "missed" else "") + str(n), 96, INK, "bold"), 170, y, "lm")
            put(f, label(name, 40, MUTED), 330, y, "lm")
            for k in range(n):
                cv2.circle(f, (900 + k * 74, y), 26, color, -1 if fill else 4, cv2.LINE_AA)
            y += 165
        return f

    c.add(scene(0), FPS)
    for i in range(1, 5): c.add(scene(i), 2 * FPS)
    c.add(scene(4), FPS); c.close()


def v07(repo, live):
    rows = p3(); c = Clip("v07_end")
    f = chart_frame(rows, 1, right=1160); card(f, W - 720, 380, 660, 330)
    c.add(f, 3 * FPS)
    end = blank()
    put(end, label("HelpChoreAI", 120, INK, "serif"), W / 2, 330, "mm")
    put(end, label("Before you act on a number, ask: can we trust it?", 44, MUTED), W / 2, 450, "mm")
    y = 590
    for t in (repo, live):
        if t: put(end, label(t, 38, INK, "mono"), W / 2, y, "mm"); y += 66
    put(end, label("SAM 3.1  \u00b7  Muse Spark 1.3  \u00b7  Muse Spark Open  \u00b7  Muse Voice Transcribe  \u00b7  Muse Code", 34, MUTED), W / 2, 800, "mm")
    put(end, label("Research use only. Not medical advice.", 30, MUTED), W / 2, 870, "mm")
    n = FPS
    for i in range(n): c.add(cv2.addWeighted(f, 1 - (i + 1) / n, end, (i + 1) / n, 0))
    c.add(end, 6 * FPS); c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="v01,v02,v03,v04,v05,v06,v07")
    ap.add_argument("--repo", default=""); ap.add_argument("--live", default="")
    a = ap.parse_args()
    todo = a.only.split(",")
    for name, fn in (("v01", v01), ("v02", v02), ("v03", v03), ("v04", v04), ("v05", v05), ("v06", v06)):
        if name in todo: fn()
    if "v07" in todo: v07(a.repo, a.live)


if __name__ == "__main__":
    main()
