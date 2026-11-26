"""
StepCast Lesson Builder
-----------------------
Turns a recording session (from record.py) into an interactive HTML lesson:

    lesson_folder/
        index.html      <- open this (works offline, from a USB stick, or inside Moodle)
        video.mp4
        step_guide.docx <- printable numbered list of the steps
        assets/logo.png
        lesson.json     <- copy of the lesson data

Usage:
    python build_lesson.py sessions/2026-11-23_071000            # build
    python build_lesson.py sessions/... --title "Inserting a table in Word"
    python build_lesson.py sessions/... --zoom 2.2 --fast --open
    python build_lesson.py --rebuild lessons/my_lesson            # after editing in ?edit mode

Runs on any OS (needs ffmpeg + ffprobe on PATH).

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


import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

# Windows consoles/pipes often use cp1252, which cannot print "✓" etc.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "player_template.html")
sys.path.insert(0, HERE)
from paths import LESSONS_DIR, find_tool  # noqa: E402

TYPING_GAP = 2.5       # s of silence that ends a typing burst
CLICK_TYPE_JOIN = 4.0  # click followed by typing within this -> one step
DOUBLE_CLICK = 0.45
DRAG_MIN_PX = 14
LEAD_IN = 1.2          # each step starts this many seconds before its action
ZOOM_IN_TIME = 0.9
ZOOM_OUT_TIME = 1.1
HOLD_AFTER = 1.8

NAV_KEYS = {"left", "right", "up", "down", "home", "end", "delete"}
KEY_LABELS = {
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "enter": "Enter",
    "esc": "Esc", "escape": "Esc", "tab": "Tab", "space": "Space", "backspace": "Backspace",
    "delete": "Delete", "up": "↑", "down": "↓", "left": "←", "right": "→",
    "page_up": "Page Up", "page_down": "Page Down", "home": "Home", "end": "End",
    "insert": "Insert", "print_screen": "PrtSc", "caps_lock": "Caps Lock",
}


# ----------------------------------------------------------------------------- utils
def ffbin(name):
    p = find_tool(name)
    if p:
        return p
    sys.exit(f"{name} was not found. Run 'Install StepCast.bat' again, or install it with: winget install Gyan.FFmpeg")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=0x08000000 if os.name == "nt" else 0)    # no console window
    if r.returncode != 0:
        raise RuntimeError(" ".join(cmd[:4]) + " …\n" + r.stderr[-800:])
    return r.stdout


def probe_duration(path):
    out = run([ffbin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path])
    try:
        return float(out.strip())
    except ValueError:
        return None


def slug(text):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return s[:50] or "lesson"


def key_label(name, mods=()):
    def one(k):
        if k in KEY_LABELS:
            return KEY_LABELS[k]
        if re.fullmatch(r"f\d{1,2}", k):
            return k.upper()
        return k.upper() if len(k) == 1 else k.replace("_", " ").title()
    order = [m for m in ("ctrl", "alt", "shift", "win") if m in mods]
    return " + ".join([one(m) for m in order] + [one(name)])


def quote(s, n=40):
    s = s.replace("\n", " ↵ ").replace("\t", " ⇥ ").strip()
    if len(s) > n:
        s = s[: n - 1] + "…"
    return f"“{s}”"


# ----------------------------------------------------------------------------- load
def load_session(sdir):
    with open(os.path.join(sdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    events = []
    with open(os.path.join(sdir, "events.jsonl"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # a half-written last line after a crash
    off = float(meta.get("video_offset") or 0)
    reg = meta.get("region") or {}
    rx, ry = int(reg.get("x", 0)), int(reg.get("y", 0))     # recording a window/area: make positions relative to it
    for e in events:
        e["t"] = e["t"] - off
        if "ref_t" in e:
            e["ref_t"] = e["ref_t"] - off
        if "x" in e and "y" in e and isinstance(e["x"], (int, float)):
            e["x"] -= rx
            e["y"] -= ry
        if e.get("rect"):
            r = e["rect"]
            e["rect"] = [r[0] - rx, r[1] - ry, r[2] - rx, r[3] - ry]
    events.sort(key=lambda e: e["t"])
    return meta, events


# ----------------------------------------------------------------------------- actions
def detect_actions(events, W, H):
    """Returns a time-ordered list of action dicts."""
    uia_point = {round(e["ref_t"], 4): e for e in events if e["type"] == "uia" and e.get("kind") == "point"}
    uia_focus = [e for e in events if e["type"] == "uia" and e.get("kind") == "focus"]

    actions = []
    raw_clicks = []   # every single press, for the click rings
    # ---- mouse ----
    downs = {}
    for e in events:
        if e["type"] == "down":
            downs[e["button"]] = e
        elif e["type"] == "up" and e["button"] in downs:
            d = downs.pop(e["button"])
            if not (0 <= d["x"] < W and 0 <= d["y"] < H):
                continue  # other monitor
            dist = math.hypot(e["x"] - d["x"], e["y"] - d["y"])
            ui = uia_point.get(round(d["t"], 4), {})
            if dist >= DRAG_MIN_PX and e["t"] - d["t"] > 0.15:
                actions.append({"kind": "drag", "t": d["t"], "end": e["t"], "x": d["x"], "y": d["y"],
                                "x2": e["x"], "y2": e["y"], "button": d["button"], "ui": ui})
            else:
                kind = {"left": "click", "right": "rclick", "middle": "mclick"}.get(d["button"], "click")
                raw_clicks.append([round(d["t"], 3), d["x"], d["y"], kind])
                actions.append({"kind": kind, "t": d["t"], "end": d["t"], "x": d["x"], "y": d["y"], "ui": ui})
    # ---- scrolling: notches close together in the same direction = one action ----
    for e in events:
        if e["type"] != "scroll" or not (0 <= e["x"] < W and 0 <= e["y"] < H):
            continue
        d = "up" if e.get("dy", 0) > 0 else "down"
        last = next((a for a in reversed(actions) if a["kind"] == "scroll"), None)
        if last and last["dir"] == d and e["t"] - last["end"] < 1.2:
            last["end"] = e["t"]
            last["count"] += 1
        else:
            actions.append({"kind": "scroll", "dir": d, "t": e["t"], "end": e["t"], "count": 1,
                            "sx": e["x"], "sy": e["y"], "ui": {}})
    actions.sort(key=lambda a: a["t"])

    # merge double clicks
    merged = []
    for a in actions:
        p = merged[-1] if merged else None
        if (p and a["kind"] == "click" and p["kind"] == "click" and a["t"] - p["t"] < DOUBLE_CLICK
                and math.hypot(a["x"] - p["x"], a["y"] - p["y"]) < 8):
            p["kind"] = "dclick"
            p["end"] = a["t"]
        else:
            merged.append(a)
    actions = merged

    # the same button clicked again and again (e.g. "Grow Font" x6) -> one action with a count
    merged = []
    for a in actions:
        p = merged[-1] if merged else None
        nm = (a.get("ui") or {}).get("name")
        if (p and nm and a["kind"] in ("click", "dclick") and p["kind"] in ("click", "dclick")
                and (p.get("ui") or {}).get("name") == nm and a["t"] - p["end"] < 1.3
                and math.hypot(a["x"] - p["x"], a["y"] - p["y"]) < 14):
            p["count"] = p.get("count", 2 if p["kind"] == "dclick" else 1) + (2 if a["kind"] == "dclick" else 1)
            p["kind"] = "click"
            p["end"] = a["end"]
        else:
            merged.append(a)
    actions = merged

    # ---- keyboard ----
    keys = [e for e in events if e["type"] == "key"]
    click_times = [a["t"] for a in actions]
    burst = None
    key_actions = []

    def flush():
        nonlocal burst
        if burst:
            if burst["text"].strip():
                key_actions.append(burst)
            elif burst["raw"]:
                # only Enter/Backspace etc. -> show as key presses
                for (t, k) in burst["raw"]:
                    key_actions.append({"kind": "key", "t": t, "end": t, "label": key_label(k), "count": 1})
        burst = None

    for e in keys:
        mods = [m for m in e.get("mods", []) if m != "shift"]
        name = e["key"]
        is_text = (not mods) and (e.get("char") is not None or name in ("space", "enter", "tab", "backspace"))
        is_nav = (not mods) and name in NAV_KEYS
        if burst and (e["t"] - burst["end"] > TYPING_GAP or any(burst["end"] < ct <= e["t"] for ct in click_times)):
            flush()
        if is_text or (is_nav and burst):
            if not burst:
                burst = {"kind": "type", "t": e["t"], "end": e["t"], "text": "", "frames": [], "raw": []}
            if is_text:
                if name == "backspace":
                    burst["text"] = burst["text"][:-1]
                elif name == "space":
                    burst["text"] += " "
                elif name == "enter":
                    burst["text"] += "\n"
                elif name == "tab":
                    burst["text"] += "\t"
                else:
                    burst["text"] += e["char"]
                if e.get("char") is None:
                    burst["raw"].append((e["t"], name))
            burst["end"] = e["t"]
            burst["frames"].append([round(e["t"], 3), burst["text"]])
        else:
            flush()
            label = key_label(name, e.get("mods", []))
            last = key_actions[-1] if key_actions else None
            if last and last["kind"] == "key" and last["label"] == label and e["t"] - last["end"] < 1.0:
                last["count"] += 1
                last["end"] = e["t"]
            else:
                key_actions.append({"kind": "key", "t": e["t"], "end": e["t"], "label": label, "count": 1})
    flush()

    # focus info, where the text went (caret), password masking
    carets = [(e["ref_t"], e["x"], e["y"]) for e in events if e["type"] == "caret"
              and 0 <= e["x"] < W and 0 <= e["y"] < H]
    for b in key_actions:
        if b["kind"] != "type":
            continue
        b["path"] = [[round(t, 3), x, y] for (t, x, y) in carets if b["t"] - 0.15 <= t <= b["end"] + 0.4]
        f = min(uia_focus, key=lambda u: abs(u["ref_t"] - b["t"]), default=None)
        if f and abs(f["ref_t"] - b["t"]) < 0.3:
            b["ui"] = f
            if f.get("is_password"):
                b["text"] = "•" * len(b["text"])
                b["frames"] = [[t, "•" * len(x)] for t, x in b["frames"]]

    actions += key_actions
    actions.sort(key=lambda a: a["t"])

    marks = [e["t"] for e in events if e["type"] == "mark"]
    scrolls = [e["t"] for e in events if e["type"] == "scroll"]
    moves = [(e["t"], e["x"], e["y"]) for e in events if e["type"] == "move"]
    return actions, marks, scrolls, moves, raw_clicks


# ----------------------------------------------------------------------------- titles
NOISY_CONTEXT = re.compile(r"xaml|backstage|taskbar|desktop|running applications|ribbon|msodock|"
                           r"source|host|container|chrome_widget|^pane$|^grouping$|^toolbar$|"
                           r"notification|system tray|^window$", re.I)


def clean_context(name):
    name = (name or "").strip()
    if not name or len(name) > 32 or NOISY_CONTEXT.search(name):
        return ""
    return name


TASKBAR_RUNNING = re.compile(r"\s+-\s+\d+\s+running windows?$", re.I)


def where_kind(ui):
    app = (ui.get("app") or "").strip()
    if app == "Taskbar" or TASKBAR_RUNNING.search(ui.get("name") or ""):
        return "taskbar"
    if app == "Program Manager":
        return "desktop"
    return ""


# things you move by dragging (everything else: a drag selects)
DRAGGABLE = {"ScrollBarControl", "SliderControl", "ThumbControl", "TitleBarControl", "ListItemControl",
             "TreeItemControl", "ImageControl", "ButtonControl", "SplitButtonControl", "TabItemControl",
             "HeaderItemControl", "HeaderControl", "MenuItemControl", "SplitterControl"}


def is_text_area(ui):
    """Does dragging here select something (text in Word, a text box, a web page, cells)?"""
    if is_document(ui) or ui.get("ctype") in ("EditControl", "TextControl", "DocumentControl"):
        return True
    if where_kind(ui):                     # taskbar / desktop icons are moved, not selected
        return False
    return ui.get("ctype") not in DRAGGABLE


def selection_title(ui):
    ct = ui.get("ctype", "")
    if ct in ("DataItemControl", "DataGridControl", "TableControl") or re.fullmatch(r"[A-Z]{1,3}\d+", ui.get("name") or ""):
        return "Select the cells"
    return "Select the text"


def is_document(ui):
    name = ui.get("name") or ""
    return ui.get("ctype") == "DocumentControl" or bool(re.fullmatch(r"Page \d+( content)?", name.strip()))


def ui_context(ui, own_name):
    """One short, friendly place name (e.g. "File", "Insert", "Tables"), or ""."""
    if ui.get("ctype") == "TabItemControl" or where_kind(ui) or is_document(ui):
        return ""
    app = ui.get("app") or ""
    anc = ui.get("ancestors", [])
    if any(NOISY_CONTEXT.search(nm or "") and re.search(r"taskbar|xaml|tray", nm or "", re.I) for nm, _ in anc):
        return ""          # Windows taskbar / tray: no useful location
    for nm, ct in anc:
        if ct in ("GroupControl", "TabItemControl", "MenuControl", "MenuItemControl",
                  "ToolBarControl", "PaneControl", "TabControl", "ListControl"):
            nm = clean_context(nm)
            if nm and nm != own_name and nm not in app:   # "Document1" is just the window name
                return nm
    return ""


def tidy_note(note, app=""):
    """Older lessons stored "Where: A ▸ B" - keep only the last friendly part.
    Drop notes that only repeat the window name ("Document1", "Program Manager")."""
    if note and note.startswith("Where: "):
        parts = [clean_context(x) for x in note[7:].split("▸")]
        parts = [x for x in parts if x]
        note = parts[-1] if parts else ""
    note = (note or "").strip()
    if note and (note == "Program Manager" or (app and note in app and note != app.split(" - ")[-1])):
        return ""
    return note


def action_title(a, next_type=None):
    ui = a.get("ui") or {}
    name = (ui.get("name") or "").strip().replace("\n", " ")
    ct = ui.get("ctype", "")
    k = a["kind"]
    if k == "type":
        field = name if ct in ("EditControl", "ComboBoxControl") and name and not is_document(ui) else ""
        return f"Type {quote(a['text'])}" + (f" in {quote(field, 30)}" if field else "")
    if k == "scroll":
        return f"Scroll {a['dir']}"
    if k == "mclick":
        return f"Middle-click {quote(name, 36) if name else 'here'}"
    if k == "key":
        return f"Press {a['label']}" + (f" ×{a['count']}" if a.get("count", 1) > 1 else "")
    if k == "drag":
        if is_text_area(ui):
            return selection_title(ui)
        return f"Drag {quote(name, 30)}" if name else "Drag"
    place = where_kind(ui)
    if place == "taskbar":
        app = TASKBAR_RUNNING.sub("", name).strip() or "the app"
        verb = {"rclick": "Right-click", "dclick": "Double-click"}.get(k, "Click")
        return f"{verb} {quote(app, 30)} on the taskbar"
    if place == "desktop":
        verb = {"rclick": "Right-click", "click": "Click"}.get(k, "Double-click")
        return f"{verb} {quote(name, 30)} on the desktop" if name else f"{verb} the desktop"
    if is_document(ui) or (ct == "EditControl" and k == "click" and next_type):
        target = "the document" if is_document(ui) else (quote(name, 30) if name else "the box")
        verb = {"click": "Click in", "dclick": "Double-click in", "rclick": "Right-click in"}.get(k, "Click in")
        return f"{verb} {target}"
    nm = quote(name, 36) if name else ""
    n = a.get("count", 1)
    if n > 1 and k == "click":
        return f"Click {nm or 'here'} {n} times"
    if k == "rclick":
        return f"Right-click {nm or 'here'}"
    if k == "dclick":
        return f"Double-click {nm or 'here'}"
    if not nm:
        return "Click here"
    verb = {
        "TabItemControl": "Open the {} tab", "MenuItemControl": "Choose {}",
        "ListItemControl": "Select {}", "TreeItemControl": "Select {}",
        "RadioButtonControl": "Select {}", "CheckBoxControl": "Tick {}",
        "ComboBoxControl": "Open the {} list", "HyperlinkControl": "Click the {} link",
        "EditControl": "Click in {}",
    }.get(ct, "Click {}")
    return verb.format(nm)


def typeable(ui):
    """Is this a place you click before typing (a box or the document)?"""
    if not ui:
        return True
    if where_kind(ui):
        return False
    return is_document(ui) or ui.get("ctype") in ("EditControl", "ComboBoxControl", "DocumentControl",
                                                 "DataItemControl", "TextControl", "CustomControl")


def build_steps(actions, marks, duration):
    # 1) group actions into step units
    units = []
    for a in actions:
        last = units[-1] if units else None
        if (last and a["kind"] == "type" and last[-1]["kind"] in ("click", "dclick")
                and a["t"] - last[-1]["t"] < CLICK_TYPE_JOIN and typeable(last[-1].get("ui") or {})):
            last.append(a)          # click into a box, then type -> one step
        elif (last and a["kind"] in ("click",) and last[-1]["kind"] == "click"
              and a["t"] - last[-1]["t"] < 0.6
              and (a.get("ui") or {}).get("name") == (last[-1].get("ui") or {}).get("name")):
            last.append(a)          # accidental repeat click
        else:
            units.append([a])

    if marks:   # user placed manual step marks -> those define the steps
        bounds = sorted(set([0.0] + [m for m in marks if 0 < m < duration]))
        grouped = []
        for i, b in enumerate(bounds):
            e = bounds[i + 1] if i + 1 < len(bounds) else duration
            acts = [a for u in units for a in u if b <= a["t"] < e]
            grouped.append({"start": b, "end": e, "actions": acts})
    else:
        grouped = []
        for u in units:
            grouped.append({"start": None, "end": None, "actions": u})
        # timing: step starts LEAD_IN before its first action
        for i, g in enumerate(grouped):
            t0 = g["actions"][0]["t"]
            prev_t = grouped[i - 1]["actions"][-1]["end"] if i else 0
            g["start"] = 0.0 if i == 0 else min(t0, max(prev_t + 0.25, t0 - LEAD_IN))
        for i, g in enumerate(grouped):
            g["end"] = grouped[i + 1]["start"] if i + 1 < len(grouped) else duration

    steps = []
    for i, g in enumerate(grouped):
        acts = g["actions"]
        if acts:
            primary = acts[-1] if acts[-1]["kind"] == "type" else acts[0]
            if len(acts) > 1 and acts[0]["kind"] in ("click", "dclick") and acts[-1]["kind"] == "type":
                # "Type 'x' in <box clicked>"
                ui = acts[0].get("ui") or {}
                primary = dict(acts[-1])
                if (ui.get("ctype") in ("EditControl", "ComboBoxControl")) and ui.get("name") and not is_document(ui):
                    primary["ui"] = ui
                title = action_title(primary)
                if is_document(ui):
                    title = f"Click in the document and type {quote(acts[-1]['text'])}"
            else:
                title = action_title(primary)
            ui0 = acts[0].get("ui") or {}
            ctx = ui_context(ui0, ui0.get("name", "")) if acts[0]["kind"] != "type" else ""
            focus = next(([a["x"], a["y"]] for a in acts if "x" in a), None)
            t_act = acts[0]["t"]
            last = acts[-1]
            if last["kind"] == "type":
                shot_t = last["end"] + 0.35          # show the finished text
            elif last["kind"] == "key":
                shot_t = last["end"] + 0.4           # show the effect of the shortcut
            else:
                shot_t = t_act - 0.05                # show the target just before the click
            shot_t = min(shot_t, g["end"] - 0.05)
        else:
            title, ctx, focus, t_act = f"Step {i + 1}", "", None, g["start"]
            shot_t = g["start"] + 0.5
        steps.append({
            "id": f"s{i + 1}",
            "title": title,
            "note": tidy_note(ctx, (acts[0].get("ui") or {}).get("app", "") if acts else ""),
            "start": round(g["start"], 3),
            "end": round(g["end"], 3),
            "action_t": round(t_act, 3),
            "shot_t": round(max(shot_t, 0), 3),
            "focus": focus,
            "app": (acts[0].get("ui") or {}).get("app", "") if acts else "",
        })
    if not steps:
        steps.append({"id": "s1", "title": "Watch the demonstration", "note": "", "start": 0,
                      "end": round(duration, 3), "action_t": 0, "shot_t": 0.5, "focus": None, "app": ""})
    return steps


# ----------------------------------------------------------------------------- camera
def build_camera(actions, scrolls, moves, W, H, zoom):
    def clamp(cx, cy, s):
        vw, vh = W / s, H / s
        cx = min(max(cx, vw / 2), W - vw / 2)
        cy = min(max(cy, vh / 2), H - vh / 2)
        return (round(cx, 1), round(cy, 1), round(s, 3))

    def view_rect(c):
        cx, cy, s = c
        vw, vh = W / s, H / s
        return cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2

    targets = []
    last_click = None
    for a in actions:
        ui = a.get("ui") or {}
        rect = ui.get("rect")
        s = zoom
        if a["kind"] == "drag":
            cx, cy = (a["x"] + a["x2"]) / 2, (a["y"] + a["y2"]) / 2
            dx, dy = abs(a["x2"] - a["x"]) + 1, abs(a["y2"] - a["y"]) + 1
            s = max(1.0, min(zoom, 0.7 * W / dx, 0.7 * H / dy))
        elif "x" in a:
            cx, cy = a["x"], a["y"]
            if rect and (rect[2] - rect[0]) * (rect[3] - rect[1]) > 0.35 * W * H:
                s = max(1.0, zoom * 0.85)
        elif a["kind"] == "type":
            s = max(1.0, zoom * 0.8)
            path = a.get("path") or []
            if path:
                # follow the text cursor: start where typing begins, pan when it leaves the view
                c = clamp(path[0][1], path[0][2], s)
                targets.append({"t": a["t"], "end": a["end"], "c": c, "move": ZOOM_IN_TIME})
                for (pt, px, py) in path[1:]:
                    l, t_, r, b = view_rect(c)
                    mx, my = (r - l) * 0.15, (b - t_) * 0.15
                    if not (l + mx <= px <= r - mx and t_ + my <= py <= b - my):
                        c = clamp(px, py, s)
                        targets.append({"t": pt + 0.1, "end": a["end"], "c": c, "move": 0.5, "pan": True})
                continue
            if rect and 0 < (rect[2] - rect[0]) < 0.4 * W and 0 < (rect[3] - rect[1]) < 0.4 * H:
                cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            else:
                continue      # we don't know where the text went: don't guess, don't zoom
        else:
            continue   # key presses: keep camera where it is
        if "x" in a:
            last_click = (a["x"], a["y"])
        targets.append({"t": a["t"], "end": a["end"], "c": clamp(cx, cy, s), "move": ZOOM_IN_TIME})
    targets.sort(key=lambda x: x["t"])

    full = (W / 2, H / 2, 1.0)
    kf = [[0.0, *full]]
    cur, cur_t = full, 0.0

    def add(t, c):
        nonlocal cur, cur_t
        t = round(max(t, kf[-1][0] + 0.05), 3)
        kf.append([t, *c])
        cur, cur_t = c, t

    for i, tg in enumerate(targets):
        arrive = tg["t"] - 0.1
        depart = arrive - tg["move"]
        if depart > cur_t:
            add(depart, cur)
        add(max(arrive, cur_t + 0.25), tg["c"])
        hold_end = tg["end"] + HOLD_AFTER
        # stop holding if the user scrolls, or the pointer leaves the zoomed view
        for st in scrolls:
            if tg["end"] < st < hold_end:
                hold_end = st
                break
        l, t_, r, b = view_rect(tg["c"])
        for (mt, mx, my) in moves:
            if tg["end"] + 0.2 < mt < hold_end and not (l <= mx <= r and t_ <= my <= b):
                hold_end = mt
                break
        nxt = targets[i + 1]["t"] - 0.1 - targets[i + 1]["move"] if i + 1 < len(targets) else float("inf")
        if nxt - hold_end > 1.2:
            add(hold_end, cur)
            add(hold_end + ZOOM_OUT_TIME, full)
    return kf


# ----------------------------------------------------------------------------- media
def make_video(src, dst, fast):
    ff = ffbin("ffmpeg")
    if fast:
        cmd = [ff, "-y", "-v", "error", "-i", src, "-c", "copy", "-movflags", "+faststart", dst]
    else:
        cmd = [ff, "-y", "-v", "error", "-i", src, "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
               "-movflags", "+faststart", dst]
    run(cmd)


def make_screenshot(video, t, focus, W, H, dst, zoom=1.6):
    """Screenshot for the Word guide: a moderately zoomed crop around the click,
    with a highlight ring drawn on the clicked spot."""
    ff = ffbin("ffmpeg")
    tmp = dst + ".tmp.png"
    run([ff, "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", video, "-frames:v", "1", tmp])
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        os.replace(tmp, dst)
        return
    im = Image.open(tmp).convert("RGB")
    if focus:
        cw, ch = int(W / zoom), int(H / zoom)
        x0 = int(min(max(focus[0] - cw / 2, 0), W - cw))
        y0 = int(min(max(focus[1] - ch / 2, 0), H - ch))
        im = im.crop((x0, y0, x0 + cw, y0 + ch))
        d = ImageDraw.Draw(im)
        fx, fy, r = focus[0] - x0, focus[1] - y0, max(16, int(W / 70))
        for k, col in ((r + 3, (0, 0, 0)), (r, (245, 158, 11))):
            d.ellipse([fx - k, fy - k, fx + k, fy + k], outline=col, width=4)
    if im.width > 1400:
        im = im.resize((1400, int(im.height * 1400 / im.width)), Image.LANCZOS)
    im.save(dst, "PNG", optimize=True)
    os.remove(tmp)


def make_screenshots(lesson, out_dir, only_missing=False):
    video = os.path.join(out_dir, lesson.get("video", "video.mp4"))
    os.makedirs(os.path.join(out_dir, "screens"), exist_ok=True)
    W, H = lesson["width"], lesson["height"]
    for i, s in enumerate(lesson["steps"]):
        name = f"screens/{s['id']}.png"
        if only_missing and s.get("shot") and os.path.exists(os.path.join(out_dir, s["shot"])):
            continue
        t = s.get("shot_t", s.get("action_t", s["start"]) + 0.3)
        t = min(max(t, s["start"]), max(s["start"], s["end"] - 0.05))
        try:
            make_screenshot(video, t, s.get("focus"), W, H, os.path.join(out_dir, name))
            s["shot"] = name
        except RuntimeError:
            s["shot"] = ""


def load_branding():
    b = {"app_name": "StepCast", "organisation": "ODC EdTech Unit", "author": "Dr Siva",
         "logo": "logo.png", "accent": "#0f766e",
         "guide_screenshots": False,
         "action_pause": 1.0,        # seconds the picture holds at each click so learners can follow
         "default_speed": 1.0,       # starting playback speed for students
         "show_edit_button": True,
         "normal_speed": 0.5,       # "1×" in the player = half the speed you recorded at
         "step_pause": 1.0}         # pause before each new step
    p = os.path.join(HERE, "branding.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            b.update(json.load(f))
    return b


def apply_branding(lesson, out_dir):
    b = load_branding()
    logo_src = b.get("logo") and os.path.join(HERE, b["logo"])
    if logo_src and os.path.exists(logo_src):
        os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
        ext = os.path.splitext(logo_src)[1].lower() or ".png"
        shutil.copyfile(logo_src, os.path.join(out_dir, "assets", "logo" + ext))
        b["logo"] = "assets/logo" + ext
    else:
        b["logo"] = ""
    lesson["branding"] = b


# ----------------------------------------------------------------------------- render
def render_html(lesson, out_dir):
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    data = json.dumps(lesson, ensure_ascii=False).replace("</", "<\\/")
    title = (lesson["title"].replace("&", "&amp;").replace("<", "&lt;"))
    html = tpl.replace("__LESSON_JSON__", data).replace("__LESSON_TITLE__", title)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(out_dir, "lesson.json"), "w", encoding="utf-8") as f:
        json.dump(lesson, f, ensure_ascii=False, indent=1)


# ----------------------------------------------------------------------------- callouts
VERBS = {"click": "Left-click", "dclick": "Double-click", "rclick": "Right-click", "mclick": "Middle-click"}


def _short_name(ui):
    name = TASKBAR_RUNNING.sub("", (ui.get("name") or "").strip().replace("\n", " "))
    if not name or len(name) > 28 or ui.get("ctype") in ("DocumentControl", "PaneControl", "WindowControl"):
        return ""
    return name


def build_callouts(actions, W, H):
    """Labels with a pointer: what to do, and exactly where.
    "at" is the moment of the action - the player briefly holds the picture there."""
    out = []
    for a in actions:
        k, ui = a["kind"], a.get("ui") or {}
        if k in VERBS:
            nm = _short_name(ui)
            text = (f"{VERBS[k]} in the document" if is_document(ui) else
                    f"{VERBS[k]} “{nm}”" if nm else f"{VERBS[k]} here")
            if a.get("count", 1) > 1:
                text += f" {a['count']} times"
            out.append({"t0": a["t"] - 1.0, "t1": a["end"] + 1.4, "at": a["t"], "x": a["x"], "y": a["y"],
                        "kind": k, "text": text})
        elif k == "drag":
            sel = is_text_area(ui)
            out.append({"t0": a["t"] - 1.0, "t1": a["t"] + 0.5, "at": a["t"], "x": a["x"], "y": a["y"],
                        "kind": "drag", "text": "Start selecting here" if sel else "Drag from here"})
            out.append({"t0": a["t"] + 0.5, "t1": a["end"] + 1.4, "x": a["x2"], "y": a["y2"],
                        "kind": "drag", "text": "…and drag to here" if sel else "…to here"})
        elif k == "scroll":
            out.append({"t0": a["t"] - 0.4, "t1": a["end"] + 1.2, "at": a["t"], "x": a["sx"], "y": a["sy"],
                        "kind": "scroll", "text": f"Scroll {a['dir']}"})
        elif k == "key":
            out.append({"t0": a["t"] - 0.3, "t1": a["end"] + 1.5, "at": a["t"], "x": None, "y": None, "kind": "key",
                        "text": "Press " + a["label"] + (f"  ×{a['count']}" if a.get("count", 1) > 1 else "")})
        elif k == "type":
            c = {"t0": a["t"] - 0.2, "t1": a["end"] + 1.4, "kind": "type", "text": "Type:", "frames": a["frames"]}
            path = a.get("path") or []
            rect = ui.get("rect")
            if path:
                c["x"], c["y"], c["path"] = path[0][1], path[0][2], path
            elif rect and 0 < rect[2] - rect[0] < 0.4 * W and 0 < rect[3] - rect[1] < 0.4 * H:
                c["x"], c["y"] = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            else:
                c["x"] = c["y"] = None      # unknown spot: shown as a caption, without a pointer
            out.append(c)
    for c in out:
        c["t0"], c["t1"] = round(max(c["t0"], 0), 3), round(c["t1"], 3)
        if "at" in c:
            c["at"] = round(c["at"], 3)
        if c.get("x") is not None:
            c["x"], c["y"] = round(c["x"]), round(c["y"])
    return out


def derive_callouts(lesson):
    """For lessons built before callouts existed: rebuild them from the stored clicks/typing."""
    out, last_pt = [], None
    clicks = lesson.get("clicks", [])
    for t, x, y, kind in clicks:
        verb = VERBS.get(kind, "Left-click")
        out.append({"t0": round(max(t - 1.0, 0), 3), "t1": round(t + 1.4, 3), "at": t, "x": x, "y": y,
                    "kind": kind, "text": f"{verb} here"})
    for ty in lesson.get("typing", []):
        # older lessons don't know where the text went - show the typing as a caption
        out.append({"t0": round(max(ty["t0"] - 0.2, 0), 3), "t1": round(ty["t1"] + 1.4, 3), "x": None, "y": None,
                    "kind": "type", "text": "Type:", "frames": ty["frames"]})
    out.sort(key=lambda c: c["t0"])
    return out


# ----------------------------------------------------------------------------- calm camera
CAM_MOVE = 1.5        # seconds for a zoom in / zoom out
CAM_HOLD = 2.0        # stay on an area this long after its last action
CAM_GROUP = 2.8       # actions closer together than this are framed together
CAM_MIN_ZOOM = 1.3    # if a group needs less zoom than this, just show the whole screen
CAM_GROUP_SPAN = 7.0  # a group never covers more than this many seconds


def camera_from_callouts(lesson, zoom):
    """Camera path built from where the actions happen. Actions close together in time are framed
    together, so the camera moves once instead of darting from click to click."""
    W, H = lesson["width"], lesson["height"]
    pts, scrolls = [], []
    for c in lesson.get("callouts", []):
        k = c.get("kind")
        if k == "scroll":
            scrolls.append(c.get("at", c["t0"]))
            continue
        if k == "key" or c.get("x") is None:
            continue
        if k == "type":
            for (t, x, y) in (c.get("path") or [[c["t0"] + 0.2, c["x"], c["y"]]]):
                pts.append((t, x, y))
        else:
            pts.append((c.get("at", c["t0"] + 1.0), c["x"], c["y"]))
    pts.sort()

    def fit(box):
        x0, y0, x1, y1 = box
        bw, bh = max(x1 - x0, 1) + W * 0.12, max(y1 - y0, 1) + H * 0.12     # margin around the actions
        sc = max(1.0, min(zoom, W / bw, H / bh))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        vw, vh = W / sc, H / sc
        cx = min(max(cx, vw / 2), W - vw / 2)
        cy = min(max(cy, vh / 2), H - vh / 2)
        return (round(cx, 1), round(cy, 1), round(sc, 3))

    groups = []
    for (t, x, y) in pts:
        g = groups[-1] if groups else None
        if (g and t - g["t1"] <= CAM_GROUP and t - g["t0"] <= CAM_GROUP_SPAN
                and not any(g["t1"] < st <= t for st in scrolls)):
            box = (min(g["box"][0], x), min(g["box"][1], y), max(g["box"][2], x), max(g["box"][3], y))
            if fit(box)[2] >= max(CAM_MIN_ZOOM, zoom * 0.75):      # still a close-up: frame them together
                g["box"], g["t1"] = box, t
                continue
        groups.append({"t0": t, "t1": t, "box": (x, y, x, y)})

    full = (W / 2, H / 2, 1.0)
    kf = [[0.0, *full]]
    cur, cur_t = full, 0.0

    def add(t, c):
        nonlocal cur, cur_t
        t = round(max(t, kf[-1][0] + 0.05), 3)
        kf.append([t, *c])
        cur, cur_t = c, t

    for i, g in enumerate(groups):
        target = fit(g["box"])
        if target[2] < CAM_MIN_ZOOM:
            target = full
        arrive = g["t0"] - 0.25                      # be there just before the first action
        depart = arrive - CAM_MOVE
        if depart < cur_t:                           # not enough time: start now, but never rush below 0.7 s
            depart = cur_t
            arrive = max(arrive, cur_t + 0.7)
        if depart > cur_t:
            add(depart, cur)
        add(arrive, target)
        hold_end = g["t1"] + CAM_HOLD
        for st in scrolls:                           # scrolling: show the whole screen again
            if g["t1"] < st < hold_end:
                hold_end = st
                break
        nxt = groups[i + 1]["t0"] - 0.25 - CAM_MOVE if i + 1 < len(groups) else float("inf")
        if nxt - hold_end > 1.0 and cur != full:
            add(hold_end, cur)
            add(hold_end + CAM_MOVE, full)
        elif hold_end > cur_t:
            add(min(hold_end, max(nxt, cur_t + 0.05)), cur)
    return kf


def build(session_dir, out_dir=None, title=None, zoom=2.0, fast=False):
    meta, events = load_session(session_dir)
    W, H = meta["screen"]["w"], meta["screen"]["h"]
    title = title or meta.get("title") or "Untitled lesson"
    src = os.path.join(session_dir, meta.get("video", "capture.mkv"))
    if out_dir is None:
        out_dir = os.path.join(LESSONS_DIR, f"{slug(title)}_{os.path.basename(os.path.normpath(session_dir))}")
    os.makedirs(out_dir, exist_ok=True)

    print("• converting video…")
    video = os.path.join(out_dir, "video.mp4")
    make_video(src, video, fast)
    duration = probe_duration(video) or (meta.get("duration", 0) - meta.get("video_offset", 0))

    print("• analysing clicks and keystrokes…")
    actions, marks, scrolls, moves, raw_clicks = detect_actions(events, W, H)
    steps = build_steps(actions, marks, duration)
    camera = build_camera(actions, scrolls, moves, W, H, zoom)

    lesson = {
        "version": 1,
        "id": slug(title) + "_" + os.path.basename(os.path.normpath(session_dir)),
        "title": title,
        "description": "",
        "video": "video.mp4",
        "width": W, "height": H,
        "duration": round(duration, 3),
        "steps": steps,
        "camera": camera,
        "clicks": raw_clicks,
        "typing": [{"t0": round(a["t"], 3), "t1": round(a["end"], 3), "frames": a["frames"]}
                   for a in actions if a["kind"] == "type"],
        "callouts": build_callouts(actions, W, H),
        "keys": [[round(a["t"], 3), a["label"] + (f"  ×{a['count']}" if a["count"] > 1 else "")]
                 for a in actions if a["kind"] == "key"],
        "settings": {"zoom": True, "pauseAfterStep": False, "callouts": True},
        "callout_v": 3,
    }
    print(f"• {len(steps)} steps, writing the Word guide…")
    finish(lesson, out_dir)
    print(f"✓ lesson ready: {os.path.join(out_dir, 'index.html')}")
    return out_dir


def upgrade_callouts(lesson):
    """Lessons built before 25 Nov 2026: typing callouts guessed their spot from the last click
    (often wrong), and clicks had no hold point. Fix both."""
    if lesson.get("callout_v", 1) >= 2:
        return
    clicks = lesson.get("clicks", [])
    W, H = lesson["width"], lesson["height"]
    for c in lesson.get("callouts", []):
        if c.get("kind") == "type":
            if not c.get("path"):
                c["x"] = c["y"] = None
                # the old camera zoomed to a guessed spot while typing: show the whole screen instead
                lo, hi = c["t0"], c["t1"] - 0.5
                cam = [k for k in lesson.get("camera", []) if not (lo <= k[0] <= hi)]
                cam += [[round(lo + 0.01, 3), W / 2, H / 2, 1.0], [round(hi - 0.01, 3), W / 2, H / 2, 1.0]]
                lesson["camera"] = sorted(cam, key=lambda k: k[0])
        elif "at" not in c and c.get("text") != "…to here":
            near = [k[0] for k in clicks if c["t0"] - 0.05 <= k[0] <= c["t1"] and k[1] == c.get("x") and k[2] == c.get("y")]
            c["at"] = round(near[0] if near else c["t0"] + 0.9, 3)
    lesson["callout_v"] = 2


def upgrade_selection_wording(lesson):
    """Older lessons called text selection a 'drag' and Word's page "Page 1 content".
    Rename only the automatic wording, never your own edits."""
    auto_sel = re.compile(r"^(Drag|Drag to select text|Drag “Page \d+( content)?”)$")
    auto_doc = re.compile(r"^(Click|Double-click|Right-click) in “Page \d+ content”$")
    calls = sorted(lesson.get("callouts", []), key=lambda c: c.get("t0", 0))
    for st in lesson["steps"]:
        t = st.get("title", "")
        m = auto_doc.match(t)
        if m:
            st["title"] = f"{m.group(1)} in the document"
            continue
        if not auto_sel.match(t):
            continue
        st["title"] = "Select the text"
        for i, c in enumerate(calls):
            if (c.get("kind") == "drag" and c.get("text") == "Drag from here"
                    and st["start"] - 0.6 <= c.get("at", c["t0"] + 1) <= st["end"] + 0.6):
                c["text"] = "Start selecting here"
                nxt = next((d for d in calls[i + 1:] if d.get("kind") == "drag"), None)
                if nxt and nxt.get("text") == "…to here":
                    nxt["text"] = "…and drag to here"


def upgrade_callouts_v3(lesson):
    """Nov 2026 (2): keyboard steps get callouts; Word's page is called 'the document'."""
    if lesson.get("callout_v", 1) >= 3:
        return
    calls = lesson.setdefault("callouts", [])
    if not any(c.get("kind") == "key" for c in calls):
        for t, label in lesson.get("keys", []):
            calls.append({"t0": round(max(t - 0.3, 0), 3), "t1": round(t + 1.5, 3), "at": t, "x": None, "y": None,
                          "kind": "key", "text": "Press " + label})
    page = re.compile(r"^(Left-click|Double-click|Right-click|Middle-click) “Page \d+ content”$")
    for c in calls:
        m = page.match(c.get("text", ""))
        if m:
            c["text"] = f"{m.group(1)} in the document"
    calls.sort(key=lambda c: c.get("t0", 0))
    lesson["callout_v"] = 3


def extract_audio(lesson, out_dir):
    """Narration recorded or uploaded in edit mode arrives as data: URLs inside index.html.
    Save each as audio/<step>.m4a (plays everywhere, keeps index.html small)."""
    import base64
    for st in lesson["steps"]:
        a = st.get("audio") or ""
        if not a.startswith("data:"):
            continue
        head, _, b64 = a.partition(",")
        mime = head[5:].split(";")[0]
        ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp3": "mp3",
               "audio/wav": "wav", "audio/x-wav": "wav", "audio/mp4": "m4a", "audio/x-m4a": "m4a",
               "audio/aac": "aac"}.get(mime, "bin")
        os.makedirs(os.path.join(out_dir, "audio"), exist_ok=True)
        raw = os.path.join(out_dir, "audio", f"{st['id']}_src.{ext}")
        with open(raw, "wb") as f:
            f.write(base64.b64decode(b64))
        dst_name = f"audio/{st['id']}.m4a"
        try:
            run([ffbin("ffmpeg"), "-y", "-v", "error", "-i", raw, "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "96k",
                 os.path.join(out_dir, dst_name)])
            os.remove(raw)
            st["audio"] = dst_name
        except RuntimeError:
            keep = f"audio/{st['id']}.{ext}"
            os.replace(raw, os.path.join(out_dir, keep))
            st["audio"] = keep
        print("• narration saved:", st["audio"])


BUILDER_VERSION = "1.0.0"     # lessons made by an older builder are offered an Update


def finish(lesson, out_dir, only_missing=False):
    for st in lesson["steps"]:
        st["note"] = tidy_note(st.get("note"), st.get("app", ""))
    if "callouts" not in lesson:
        lesson["callouts"] = derive_callouts(lesson)
        lesson["callout_v"] = 2
    upgrade_callouts(lesson)
    upgrade_selection_wording(lesson)
    upgrade_callouts_v3(lesson)
    lesson["builder"] = BUILDER_VERSION
    lesson["generator"] = ("StepCast 1.0 by Dr Sivakumar Manickam (skumar@staff.odc.edu.om), "
                           "developed with the help of Claude (Anthropic)")
    extract_audio(lesson, out_dir)
    apply_branding(lesson, out_dir)
    b = lesson["branding"]
    st = lesson.setdefault("settings", {})
    st["actionPause"] = float(b.get("action_pause", 1.0))
    st["defaultSpeed"] = float(b.get("default_speed", 1.0))
    st["normalSpeed"] = float(b.get("normal_speed", 0.5))
    st["stepPause"] = float(b.get("step_pause", 1.0))      # seconds of calm before each new step
    # the camera is always rebuilt from where the actions are, so zoom changes in Settings apply on Update
    lesson["camera"] = camera_from_callouts(lesson, float(b.get("zoom", 2.0)))     # what "1×" means, as a share of the recorded speed
    st["showEdit"] = bool(b.get("show_edit_button", True))
    if lesson["branding"].get("guide_screenshots"):
        make_screenshots(lesson, out_dir, only_missing)
    try:
        from step_guide import make_step_guide
        lesson["guide"] = make_step_guide(lesson, out_dir)
        print("• Word step guide:", lesson["guide"])
    except ImportError:
        lesson["guide"] = ""
        print("! python-docx is not installed - run setup.bat again to get the Word guide")
    render_html(lesson, out_dir)


def read_lesson(lesson_dir):
    """index.html is the source of truth (edit mode saves into it); fall back to lesson.json."""
    html_p = os.path.join(lesson_dir, "index.html")
    if os.path.exists(html_p):
        with open(html_p, encoding="utf-8") as f:
            m = re.search(r'<script id="lesson-data" type="application/json">([\s\S]*?)</script>', f.read())
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    with open(os.path.join(lesson_dir, "lesson.json"), encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="Build an interactive HTML lesson from a StepCast recording")
    ap.add_argument("session", nargs="?", help="session folder written by record.py")
    ap.add_argument("-o", "--out", help="output lesson folder")
    ap.add_argument("--title", help="lesson title")
    ap.add_argument("--zoom", type=float, default=None, help="zoom level for clicks (default: branding.json 'zoom', else 2.0)")
    ap.add_argument("--fast", action="store_true", help="don't re-encode video (bigger file, faster build)")
    ap.add_argument("--rebuild", metavar="LESSON_DIR", help="after editing a lesson: refresh branding, screenshots and the Word guide")
    ap.add_argument("--open", action="store_true", help="open the lesson in the browser when done")
    a = ap.parse_args()

    if a.rebuild:
        lesson = read_lesson(a.rebuild)
        finish(lesson, a.rebuild, only_missing=True)
        out = a.rebuild
        print("✓ updated", os.path.join(out, "index.html"))
    elif a.session:
        zoom = a.zoom if a.zoom is not None else float(load_branding().get("zoom", 2.0))
        out = build(a.session, a.out, a.title, zoom, a.fast)
    else:
        ap.print_help()
        return
    if a.open:
        webbrowser.open(Path(os.path.abspath(os.path.join(out, "index.html"))).as_uri())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
