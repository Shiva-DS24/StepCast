"""Creates a fake recording session (video + events) that imitates a Word demo,
so the builder and player can be tested without Windows.

Project:     StepCast - interactive step-by-step screen lessons
Author:      Dr Sivakumar Manickam <skumar@staff.odc.edu.om>
             Head of Educational Technology & Resources, Oman Dental College
Credits:     Conceived, designed, tested and led by Dr Sivakumar Manickam.
             Developed with the help of Claude (Anthropic) as an AI coding assistant.
Version:     1.0.0
Copyright:   (c) 2026 Dr Sivakumar Manickam. Licensed under the MIT License (see LICENSE).
"""

__author__ = "Dr Sivakumar Manickam"
__email__ = "skumar@staff.odc.edu.om"
__credits__ = ["Dr Sivakumar Manickam (lead: idea, design, testing)", "Claude, Anthropic (AI coding assistant)"]
__version__ = "1.0.0"
__copyright__ = "(c) 2026 Dr Sivakumar Manickam"

import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
W, H, FPS, DUR = 1600, 900, 25, 18.0
OFF = 0.4  # pretend ffmpeg started 0.4 s after launch
try:
    F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    FB = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
except OSError:
    F = FB = ImageFont.load_default()

# actions in video time
clicks = [(2.0, 190, 62, "Insert", "TabItemControl", [["Insert", "TabItemControl"]]),
          (4.0, 262, 120, "Table", "SplitButtonControl", [["Tables", "GroupControl"], ["Insert", "TabItemControl"]]),
          (6.0, 300, 230, "3 x 4 Table", "ButtonControl", [["Table", "MenuControl"]]),
          (8.5, 520, 420, "Page 1 content", "DocumentControl", [])]
typed = "Patient record"
type_t0 = 9.0
key_ctrl_b = 12.6
save_click = (15.0, 34, 18, "Save", "ButtonControl", [["Quick Access Toolbar", "ToolBarControl"]])
clicks.append(save_click)

path_pts = [(0, 800, 600)] + [(c[0], c[1], c[2]) for c in clicks] + [(DUR, 900, 500)]
def cursor(t):
    for (t0, x0, y0), (t1, x1, y1) in zip(path_pts, path_pts[1:]):
        if t0 <= t <= t1:
            # move during the 0.8 s before the next click
            p = 0 if t < t1 - 0.8 else (t - (t1 - 0.8)) / 0.8
            p = p * p * (3 - 2 * p)
            return x0 + (x1 - x0) * p, y0 + (y1 - y0) * p
    return path_pts[-1][1:]

def frame(t):
    im = Image.new("RGB", (W, H), "#e9e9e9")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 36], fill="#2b579a"); d.text((70, 9), "Document1 - Word", font=F, fill="white")
    d.rectangle([20, 8, 48, 28], outline="white")
    d.rectangle([0, 36, W, 160], fill="#f3f3f3")
    tab = "Insert" if t >= 2.0 else "Home"
    for i, nm in enumerate(["File", "Home", "Insert", "Design", "Layout", "References"]):
        x = 30 + i * 80
        if nm == tab: d.rectangle([x - 8, 50, x + 62, 74], fill="white", outline="#2b579a")
        d.text((x, 54), nm, font=F, fill="#222")
    if tab == "Insert":
        for i, nm in enumerate(["Table", "Pictures", "Shapes", "Chart", "Link"]):
            x = 240 + i * 90
            d.rectangle([x, 90, x + 60, 140], outline="#bbb", fill="#fff")
            d.text((x + 6, 145), nm, font=F, fill="#222")
    else:
        d.text((40, 100), "B   I   U    Calibri  11", font=FB, fill="#333")
    d.rectangle([300, 190, 1300, H], fill="white", outline="#ccc")
    if 4.0 <= t < 6.0:
        d.rectangle([240, 150, 420, 330], fill="#fff", outline="#888")
        for r in range(6):
            for c in range(8):
                hl = r < 3 and c < 4 and t > 5.2
                d.rectangle([250 + c * 20, 160 + r * 20, 266 + c * 20, 176 + r * 20],
                            fill="#cfe0f7" if hl else "#fff", outline="#888")
    if t >= 6.0:
        for r in range(3):
            for c in range(4):
                d.rectangle([360 + c * 220, 230 + r * 40, 580 + c * 220, 270 + r * 40], outline="#333")
    n = sum(1 for i in range(len(typed)) if t >= type_t0 + i * 0.18)
    if n:
        d.text((370, 405), typed[:n], font=FB if t >= key_ctrl_b else F, fill="#111")
    x, y = cursor(t)
    d.polygon([(x, y), (x, y + 22), (x + 6, y + 16), (x + 15, y + 16)], fill="black", outline="white")
    return im

ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                       "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                       os.path.join(out, "capture.mkv")], stdin=subprocess.PIPE)
for i in range(int(DUR * FPS)):
    ff.stdin.write(frame(i / FPS).tobytes())
ff.stdin.close(); ff.wait()

ev = []
L = lambda t: round(t + OFF, 4)  # events are logged in launch time
t = 0.0
while t < DUR:
    x, y = cursor(t); ev.append({"type": "move", "t": L(t), "x": int(x), "y": int(y)}); t += 0.05
for (ct, x, y, nm, ctype, anc) in clicks:
    ev.append({"type": "down", "t": L(ct), "x": x, "y": y, "button": "left"})
    ev.append({"type": "up", "t": L(ct + 0.08), "x": x, "y": y, "button": "left"})
    ev.append({"type": "uia", "kind": "point", "ref_t": L(ct), "t": L(ct + 0.03), "name": nm, "ctype": ctype,
               "rect": [x - 30, y - 15, x + 30, y + 15] if ctype != "DocumentControl" else [300, 190, 1300, 900],
               "ancestors": anc, "app": "Document1 - Word"})
for i, ch in enumerate(typed):
    kt = type_t0 + i * 0.18
    ev.append({"type": "key", "t": L(kt), "key": "space" if ch == " " else ch.lower(),
               "char": None if ch == " " else ch, "mods": []})
ev.append({"type": "uia", "kind": "focus", "ref_t": L(type_t0), "t": L(type_t0 + 0.05), "name": "Page 1 content",
           "ctype": "DocumentControl", "rect": [300, 190, 1300, 900], "is_password": False})
ev.append({"type": "key", "t": L(key_ctrl_b), "key": "b", "char": None, "mods": ["ctrl"]})
ev.sort(key=lambda e: e["t"])
with open(os.path.join(out, "events.jsonl"), "w") as f:
    for e in ev: f.write(json.dumps(e) + "\n")
json.dump({"version": 1, "title": "Inserting a table in Word", "screen": {"w": W, "h": H}, "fps": FPS,
           "video": "capture.mkv", "video_offset": OFF, "duration": DUR + OFF},
          open(os.path.join(out, "meta.json"), "w"), indent=2)
print("mock session written to", out)
