"""
StepCast - record a task on screen and turn it into an interactive, step-by-step HTML lesson.

    Record    choose the whole screen, one window or an area; a red frame and a small REC bar
              show what is being recorded (neither appears in the video)
    Lessons   every lesson you have made: open it, edit it, update it, or build new recordings
    Settings  your name, unit, colour, logo, zoom level and pacing

Hotkeys while recording (never written into the lesson):
    Ctrl + Alt + End    stop recording
    Ctrl + Alt + P      pause / resume keystroke capture (privacy, e.g. passwords)

Project:     StepCast - interactive step-by-step screen lessons
Author:      Dr Sivakumar Manickam <skumar@staff.odc.edu.om>
             Head of Educational Technology & Resources, Oman Dental College
Credits:     Conceived, designed, tested and led by Dr Sivakumar Manickam.
             Developed with the help of Claude (Anthropic) as an AI coding assistant.
Version:     1.3
Copyright:   (c) 2026 Dr Sivakumar Manickam. Licensed under the MIT License (see LICENSE).
"""

__author__ = "Dr Sivakumar Manickam"
__email__ = "skumar@staff.odc.edu.om"
__credits__ = ["Dr Sivakumar Manickam (lead: idea, design, testing)", "Claude, Anthropic (AI coding assistant)"]
__version__ = "1.3"
__copyright__ = "(c) 2026 Dr Sivakumar Manickam"


import json
import os

import subprocess
import sys
import threading
import time
import webbrowser
import datetime as _dt
from pathlib import Path

import capture                      # sets DPI awareness first - keep this import before tkinter
from editserver import EditServer
from capture import IS_WIN, APP_DIR, SESSIONS_DIR
from paths import LESSONS_DIR, HOME_DIR, LOG_FILE, prepare_folders

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

try:
    from PIL import Image
except Exception:
    Image = None

VERSION = "1.3"
BRANDING = os.path.join(APP_DIR, "branding.json")

# ---------------------------------------------------------------- look & feel
ACCENT = "#0f766e"
ACCENT_HOVER = "#0b5f59"
SIDEBAR = "#0c2d2a"
SIDEBAR_HOVER = "#14423e"
BG = "#f4f6f8"
CARD = "#ffffff"
LINE = "#e4e7ec"
INK = "#1c2430"
MUTED = "#667085"
RED = "#dc2626"
RED_HOVER = "#b91c1c"
FONT = "Segoe UI" if IS_WIN else "DejaVu Sans"

ctk.set_appearance_mode("light")


def F(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def load_branding():
    b = {"app_name": "StepCast", "organisation": "ODC EdTech Unit", "author": "Dr Siva", "logo": "logo.png",
         "accent": ACCENT, "zoom": 2.0, "action_pause": 1.0, "default_speed": 1.0, "normal_speed": 0.5, "step_pause": 1.0,
         "show_edit_button": True, "guide_screenshots": False}
    try:
        with open(BRANDING, encoding="utf-8") as f:
            b.update(json.load(f))
    except Exception:
        pass
    return b


def fmt_dur(sec):
    sec = int(round(sec or 0))
    return f"{sec // 60}:{sec % 60:02d}"


def open_url(url):
    """Open a URL (with ?edit) in Chrome or Edge; Windows drops query strings for file:// otherwise."""
    if IS_WIN:
        cands = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for c in cands:
            if os.path.exists(c):
                subprocess.Popen([c, url])
                return
    webbrowser.open(url)


def open_folder(path):
    if IS_WIN:
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        try:
            subprocess.Popen(["xdg-open", path])
        except OSError:
            webbrowser.open(Path(path).as_uri())


def virtual_screen():
    if not IS_WIN:
        return 0, 0, 1920, 1080
    gsm = capture.ctypes.windll.user32.GetSystemMetrics
    return gsm(76), gsm(77), gsm(78), gsm(79)


# ============================================================================ overlays
class Countdown(tk.Toplevel):
    def __init__(self, master, region, seconds, done):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        x, y, w, h = region
        size = 220
        self.geometry(f"{size}x{size}+{int(x + w / 2 - size / 2)}+{int(y + h / 2 - size / 2)}")
        self.configure(bg="#111827")
        self.lbl = tk.Label(self, text="", fg="white", bg="#111827", font=(FONT, 96, "bold"))
        self.lbl.pack(expand=True, fill="both")
        tk.Label(self, text="Recording starts…", fg="#9ca3af", bg="#111827", font=(FONT, 12)).pack(pady=(0, 18))
        capture.exclude_from_capture(self)
        self.done, self.n = done, seconds
        self.tick()

    def tick(self):
        if self.n == 0:
            self.destroy()
            self.done()
            return
        self.lbl.configure(text=str(self.n))
        self.n -= 1
        self.after(1000, self.tick)


class RecordingOverlay:
    """Red frame around the recorded area + floating REC bar. Both are left out of the video."""
    T = 4   # frame thickness

    def __init__(self, master, region, recorder, show_frame, on_stop):
        self.master, self.rec, self.on_stop = master, recorder, on_stop
        x, y, w, h = region
        vx, vy, vw, vh = virtual_screen()
        self.wins = []
        if show_frame:
            t = self.T
            # outside the area where there is room, otherwise just inside the edge
            top = y - t if y - t >= vy else y
            bottom = y + h if y + h + t <= vy + vh else y + h - t
            left = x - t if x - t >= vx else x
            right = x + w if x + w + t <= vx + vw else x + w - t
            for gx, gy, gw, gh in ((left, top, (right + t) - left, t), (left, bottom, (right + t) - left, t),
                                   (left, top, t, (bottom + t) - top), (right, top, t, (bottom + t) - top)):
                s = tk.Toplevel(master)
                s.overrideredirect(True)
                s.attributes("-topmost", True)
                s.configure(bg="#ef4444")
                s.geometry(f"{gw}x{gh}+{gx}+{gy}")
                capture.exclude_from_capture(s)
                capture.make_click_through(s)
                self.wins.append(s)

        # ---- REC bar
        bar = tk.Toplevel(master)
        bar.overrideredirect(True)
        bar.attributes("-topmost", True)
        bar.configure(bg="#111827")
        inner = tk.Frame(bar, bg="#111827", padx=12, pady=7)
        inner.pack()
        self.dot = tk.Canvas(inner, width=14, height=14, bg="#111827", highlightthickness=0)
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill="#ef4444", outline="")
        self.dot.pack(side="left")
        tk.Label(inner, text="REC", fg="white", bg="#111827", font=(FONT, 11, "bold")).pack(side="left", padx=(6, 8))
        self.timer = tk.Label(inner, text="0:00", fg="#e5e7eb", bg="#111827", font=("Consolas", 12, "bold"))
        self.timer.pack(side="left", padx=(0, 14))
        self.keys = tk.Label(inner, text="", fg="#fbbf24", bg="#111827", font=(FONT, 9))
        self.keys.pack(side="left", padx=(0, 8))
        bstop = tk.Label(inner, text="■ Stop", fg="white", bg=RED, font=(FONT, 10, "bold"), padx=12, pady=3,
                         cursor="hand2")
        bstop.pack(side="left")
        bstop.bind("<Button-1>", lambda e: self.on_stop())
        bar.update_idletasks()
        bw, bh = bar.winfo_reqwidth(), bar.winfo_reqheight()
        bx = int(x + w / 2 - bw / 2)
        by = y - bh - 10 if y - bh - 10 >= vy else y + 12
        bar.geometry(f"+{bx}+{by}")
        capture.exclude_from_capture(bar)
        self.bar = bar
        self.wins.append(bar)
        # clicks on the bar must not become lesson steps
        recorder.ignore_rects.append((bx - 4, by - 4, bx + bw + 4, by + bh + 4))
        self.blink = True
        self.update()

    def update(self):
        if not self.wins:
            return
        self.timer.configure(text=fmt_dur(self.rec.elapsed()))
        self.blink = not self.blink
        self.dot.itemconfigure(self.dot_id, fill="#ef4444" if self.blink else "#7f1d1d")
        self.keys.configure(text="typing not recorded" if self.rec.keys_paused else "")
        self.bar.after(500, self.update)

    def close(self):
        for w in self.wins:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.wins = []


class AreaPicker(tk.Toplevel):
    """Drag a rectangle over the screen to choose what to record."""

    def __init__(self, master, done):
        super().__init__(master)
        self.done = done
        vx, vy, vw, vh = virtual_screen()
        self.vx, self.vy = vx, vy
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.35)
        except tk.TclError:
            pass
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.c = tk.Canvas(self, bg="black", highlightthickness=0, cursor="crosshair")
        self.c.pack(fill="both", expand=True)
        mons = capture.monitors()
        m = next((m for m in mons if m["primary"]), mons[0])
        self.c.create_text(m["x"] - vx + m["w"] / 2, m["y"] - vy + 60, fill="white", font=(FONT, 22, "bold"),
                           text="Drag to select the area to record   ·   Esc to cancel")
        self.rect = self.lbl = None
        self.c.bind("<ButtonPress-1>", self.press)
        self.c.bind("<B1-Motion>", self.drag)
        self.c.bind("<ButtonRelease-1>", self.release)
        self.bind("<Escape>", lambda e: self.finish(None))
        self.focus_force()

    def press(self, e):
        self.x0, self.y0 = e.x, e.y
        self.rect = self.c.create_rectangle(e.x, e.y, e.x, e.y, outline="#ef4444", width=4)
        self.lbl = self.c.create_text(e.x, e.y - 18, fill="white", font=(FONT, 14, "bold"), anchor="w")

    def drag(self, e):
        if self.rect:
            self.c.coords(self.rect, self.x0, self.y0, e.x, e.y)
            self.c.coords(self.lbl, min(self.x0, e.x), min(self.y0, e.y) - 18)
            self.c.itemconfigure(self.lbl, text=f"{abs(e.x - self.x0)} × {abs(e.y - self.y0)}")

    def release(self, e):
        if not self.rect:
            return
        x, y = min(self.x0, e.x), min(self.y0, e.y)
        w, h = abs(e.x - self.x0), abs(e.y - self.y0)
        if w < 80 or h < 60:
            self.c.delete(self.rect)
            self.c.delete(self.lbl)
            self.rect = None
            return
        self.finish((x + self.vx, y + self.vy, w, h))

    def finish(self, region):
        self.destroy()
        self.done(region)


# ============================================================================ widgets
class Card(ctk.CTkFrame):
    def __init__(self, master, title=None, subtitle=None, **kw):
        super().__init__(master, fg_color=CARD, corner_radius=14, border_width=1, border_color=LINE, **kw)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if title:
            ctk.CTkLabel(self, text=title, font=F(14, "bold"), text_color=INK, anchor="w").pack(
                fill="x", padx=20, pady=(16, 0))
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=F(12), text_color=MUTED, anchor="w", justify="left",
                         wraplength=640).pack(fill="x", padx=20, pady=(2, 0))
        self.body.pack(fill="x", padx=20, pady=(10, 18))


def page_header(master, title, subtitle, wrap=720):
    ctk.CTkLabel(master, text=title, font=F(24, "bold"), text_color=INK, anchor="w").pack(fill="x", pady=(26, 0))
    ctk.CTkLabel(master, text=subtitle, font=F(13), text_color=MUTED, anchor="w", justify="left",
                 wraplength=wrap).pack(fill="x", pady=(2, 16))


def button(master, text, command, kind="primary", width=None, height=34):
    colors = {
        "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white"),
        "danger": dict(fg_color=RED, hover_color=RED_HOVER, text_color="white"),
        "ghost": dict(fg_color="transparent", hover_color="#eef2f2", text_color=INK, border_width=1,
                      border_color=LINE),
    }[kind]
    kw = dict(text=text, command=command, height=height, corner_radius=9, font=F(13, "bold"), **colors)
    if width:
        kw["width"] = width
    return ctk.CTkButton(master, **kw)


MENU = dict(fg_color="#eef2f2", button_color="#dfe7e6", button_hover_color="#cfdbd9", text_color=INK)


# ============================================================================ pages
class RecordPage(ctk.CTkScrollableFrame):
    MODES = ["Whole screen", "One window", "An area"]

    def __init__(self, app):
        super().__init__(app.holder(), fg_color=BG)
        self.app = app
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=34)
        self.wrap = wrap
        page_header(wrap, "New recording",
                    "Choose what to record, then press Start. Work slowly and pause briefly between steps; "
                    "StepCast turns each click, typed text and shortcut into a step.")
        self.saved_card = None
        self.anchor = None
        if not IS_WIN:
            note = ctk.CTkFrame(wrap, fg_color="#eff6ff", corner_radius=14, border_width=1, border_color="#bfdbfe")
            note.pack(fill="x", pady=(0, 14))
            ctk.CTkLabel(note, text="Recording needs Windows", font=F(14, "bold"), text_color="#1e3a8a",
                         anchor="w").pack(fill="x", padx=20, pady=(14, 0))
            ctk.CTkLabel(note, text="On this computer you can open, edit and update lessons (Lessons page) and change "
                                    "Settings. To record new lessons, use StepCast on a Windows 10 or 11 PC. "
                                    "Finished lessons play on any computer, tablet or phone.",
                         font=F(12), text_color="#1e40af", anchor="w", justify="left",
                         wraplength=640).pack(fill="x", padx=20, pady=(2, 14))

        c = Card(wrap, "Lesson title")
        c.pack(fill="x", pady=(0, 14))
        self.anchor = c
        self.title_e = ctk.CTkEntry(c.body, placeholder_text="e.g. Inserting a table in Word", height=38, font=F(14))
        self.title_e.pack(fill="x")

        c = Card(wrap, "What to record")
        c.pack(fill="x", pady=(0, 14))
        self.mode = ctk.CTkSegmentedButton(c.body, values=self.MODES, command=self.mode_changed, height=36,
                                           font=F(13, "bold"), selected_color=ACCENT,
                                           selected_hover_color=ACCENT_HOVER, fg_color="#7b8a99",
                                           unselected_color="#7b8a99", unselected_hover_color="#66768a")
        self.mode.pack(anchor="w")
        self.mode.set(self.MODES[0])
        self.opts = ctk.CTkFrame(c.body, fg_color="transparent")
        self.opts.pack(fill="x", pady=(14, 0))
        self.area = None
        self.mon_list, self.win_list = [], []
        self.mode_changed(self.MODES[0])

        c = Card(wrap, "Options")
        c.pack(fill="x", pady=(0, 14))
        row = ctk.CTkFrame(c.body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Frame rate", font=F(13), text_color=INK).pack(side="left")
        self.fps = ctk.CTkOptionMenu(row, values=["15", "20", "25", "30"], width=80, **MENU)
        self.fps.set("25")
        self.fps.pack(side="left", padx=(10, 28))
        self.countdown = ctk.CTkSwitch(row, text="3-second countdown", font=F(13), progress_color=ACCENT)
        self.countdown.select()
        self.countdown.pack(side="left", padx=(0, 24))
        self.frame_sw = ctk.CTkSwitch(row, text="Red frame around the recorded area", font=F(13),
                                      progress_color=ACCENT)
        self.frame_sw.select()
        self.frame_sw.pack(side="left")

        self.start_btn = button(wrap, "●   Start recording", self.start, "danger", height=50)
        self.start_btn.configure(font=F(16, "bold"))
        if not IS_WIN:
            self.start_btn.configure(state="disabled", text="●   Recording needs Windows", fg_color="#cbd5e1")
        self.start_btn.pack(fill="x", pady=(4, 14))

        c = Card(wrap, "While recording")
        c.pack(fill="x", pady=(0, 30))
        for keys, what in (("Ctrl + Alt + End", "Stop recording (or ■ Stop on the REC bar)"),
                           ("Ctrl + Alt + P", "Pause / resume typing capture, e.g. before a password")):
            r = ctk.CTkFrame(c.body, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=keys, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                         fg_color="#f1f5f4", corner_radius=6, text_color=INK, width=150).pack(side="left")
            ctk.CTkLabel(r, text=what, font=F(13), text_color=MUTED).pack(side="left", padx=12)
        ctk.CTkLabel(c.body, text="Steps are created automatically from your clicks, typing and shortcuts – you "
                                  "can rename, merge or split them afterwards in Edit. The red frame and the REC bar "
                                  "are only visible to you: they are left out of the video, and clicks on the REC "
                                  "bar are not recorded.",
                     font=F(12), text_color=MUTED, anchor="w", justify="left", wraplength=640).pack(fill="x", pady=(8, 0))

    # ---- source options
    def mode_changed(self, mode):
        for w in self.opts.winfo_children():
            w.destroy()
        if mode == "Whole screen":
            self.mon_list = capture.monitors()
            names = [m["name"] for m in self.mon_list]
            self.mon = ctk.CTkOptionMenu(self.opts, values=names, width=320, **MENU)
            self.mon.set(names[0])
            self.mon.pack(side="left")
            if len(names) == 1:
                ctk.CTkLabel(self.opts, text="Your whole screen will be recorded.", font=F(12),
                             text_color=MUTED).pack(side="left", padx=12)
        elif mode == "One window":
            self.win_list = capture.list_windows()
            names = [w["title"][:70] for w in self.win_list] or ["(no windows found)"]
            self.win = ctk.CTkOptionMenu(self.opts, values=names, width=420, dynamic_resizing=False, **MENU)
            self.win.set(names[0])
            self.win.pack(side="left")
            button(self.opts, "↻", lambda: self.mode_changed("One window"), "ghost", width=40).pack(side="left", padx=8)
            ctk.CTkLabel(self.opts, text="Keep the window where it is while recording.", font=F(12),
                         text_color=MUTED).pack(side="left", padx=4)
        else:
            button(self.opts, "⬚  Select area…", self.pick_area, "ghost").pack(side="left")
            txt = (f"{self.area[2]} × {self.area[3]} pixels" if self.area else "No area selected yet")
            ctk.CTkLabel(self.opts, text=txt, font=F(13), text_color=INK if self.area else MUTED).pack(side="left", padx=12)

    def pick_area(self):
        self.app.iconify()

        def done(region):
            self.app.deiconify()
            if region:
                self.area = region
            self.mode_changed("An area")
        self.app.after(300, lambda: AreaPicker(self.app, done))

    def region(self):
        mode = self.mode.get()
        if mode == "Whole screen":
            m = next(m for m in self.mon_list if m["name"] == self.mon.get())
            return (m["x"], m["y"], m["w"], m["h"]), f"screen: {m['name']}"
        if mode == "One window":
            w = next((w for w in self.win_list if w["title"][:70] == self.win.get()), None)
            if not w:
                raise ValueError("Choose a window to record (press ↻ to refresh the list).")
            capture.bring_to_front(w["hwnd"])
            self.app.update()
            time.sleep(0.5)
            x, y, ww, hh = capture.window_rect(w["hwnd"])
            vx, vy, vw, vh = virtual_screen()
            x2, y2 = min(x + ww, vx + vw), min(y + hh, vy + vh)
            x, y = max(x, vx), max(y, vy)
            return (x, y, x2 - x, y2 - y), f"window: {w['title']}"
        if not self.area:
            raise ValueError("Select the area to record first.")
        return self.area, "area"

    # ---- recording
    def start(self):
        try:
            region, source = self.region()
        except ValueError as e:
            messagebox.showinfo("StepCast", str(e))
            return
        self.app.begin_recording(self.title_e.get().strip(), int(self.fps.get()), region, source,
                                 bool(self.countdown.get()), bool(self.frame_sw.get()))

    def show_saved(self, title, duration, session_dir):
        if self.saved_card:
            self.saved_card.destroy()
        c = ctk.CTkFrame(self.wrap, fg_color="#ecfdf5", corner_radius=14, border_width=1, border_color="#a7f3d0")
        c.pack(fill="x", pady=(0, 14), before=self.anchor)
        ctk.CTkLabel(c, text="✓  Recording saved", font=F(15, "bold"), text_color="#065f46", anchor="w").pack(
            fill="x", padx=20, pady=(14, 0))
        ctk.CTkLabel(c, text=f"“{title}”  ·  {fmt_dur(duration)}  ·  turn it into a lesson now, or later from Lessons.",
                     font=F(12), text_color="#047857", anchor="w").pack(fill="x", padx=20)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(10, 16))
        button(row, "Build lesson", lambda: self.app.build_session(session_dir, title)).pack(side="left")
        button(row, "Show recording folder", lambda: open_folder(session_dir), "ghost").pack(side="left", padx=8)
        self.saved_card = c


class LessonsPage(ctk.CTkScrollableFrame):
    def __init__(self, app):
        super().__init__(app.holder(), fg_color=BG)
        self.app = app
        self.wrap = ctk.CTkFrame(self, fg_color="transparent")
        self.wrap.pack(fill="both", expand=True, padx=34)

    def refresh(self):
        for w in self.wrap.winfo_children():
            w.destroy()
        page_header(self.wrap, "Lessons", "Open a lesson, edit its steps, callouts and narration, or update it after editing.")
        btns = ctk.CTkFrame(self.wrap, fg_color="transparent")
        btns.pack(fill="x", pady=(0, 14))
        button(btns, "↻ Refresh", self.refresh, "ghost").pack(side="left", padx=(0, 6))
        self.btns = btns
        button(btns, "Lessons folder", lambda: open_folder(os.makedirs(LESSONS_DIR, exist_ok=True) or LESSONS_DIR),
               "ghost").pack(side="left")

        lessons, pending = scan_library()
        old = [l["dir"] for l in lessons if l["outdated"]]
        if old:
            button(self.btns, f"Update all ({len(old)})", lambda: self.app.update_lessons(old)).pack(side="left", padx=(6, 0))
        if pending:
            ctk.CTkLabel(self.wrap, text="RECORDINGS NOT BUILT YET", font=F(11, "bold"), text_color=MUTED,
                         anchor="w").pack(fill="x", pady=(4, 6))
            for p in pending:
                self.pending_row(p)
            ctk.CTkFrame(self.wrap, height=10, fg_color="transparent").pack()
        ctk.CTkLabel(self.wrap, text=f"YOUR LESSONS  ·  {len(lessons)}", font=F(11, "bold"), text_color=MUTED,
                     anchor="w").pack(fill="x", pady=(4, 6))
        if not lessons:
            Card(self.wrap, "No lessons yet", "Record a task on the Record page, then build it into a lesson.").pack(fill="x")
        for les in lessons:
            self.lesson_row(les)
        ctk.CTkFrame(self.wrap, height=24, fg_color="transparent").pack()

    def lesson_row(self, les):
        c = ctk.CTkFrame(self.wrap, fg_color=CARD, corner_radius=12, border_width=1, border_color=LINE)
        c.pack(fill="x", pady=4)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(side="right", padx=12)
        idx = os.path.join(les["dir"], "index.html")
        button(row, "Open", lambda: open_url(Path(idx).as_uri()), width=66).pack(side="left", padx=3)
        button(row, "Edit", lambda: open_url(self.app.editor.edit_url(les["dir"])), "ghost", width=60).pack(side="left", padx=3)
        button(row, "Update", lambda: self.app.update_lesson(les["dir"]), "primary" if les["outdated"] else "ghost",
               width=72).pack(side="left", padx=3)
        button(row, "Folder", lambda: open_folder(les["dir"]), "ghost", width=66).pack(side="left", padx=3)
        ctk.CTkLabel(c, text="▶", width=42, height=42, corner_radius=10, fg_color="#e6f4f2",
                     text_color=ACCENT, font=F(16, "bold")).pack(side="left", padx=(14, 12), pady=12)
        txt = ctk.CTkFrame(c, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkLabel(txt, text=les["title"], font=F(14, "bold"), text_color=INK, anchor="w").pack(fill="x")
        meta = [f"{les['steps']} steps", fmt_dur(les["duration"]), les["date"]]
        if les["narrated"]:
            meta.append(f"🔊 {les['narrated']} narrated")
        ctk.CTkLabel(txt, text="   ·   ".join(meta), font=F(12), text_color=MUTED, anchor="w").pack(fill="x")
        if les["outdated"]:
            ctk.CTkLabel(txt, text="Made with an older StepCast – press Update", font=F(11, "bold"),
                         text_color="#b45309", anchor="w").pack(fill="x")

    def pending_row(self, p):
        c = ctk.CTkFrame(self.wrap, fg_color="#fffbeb", corner_radius=12, border_width=1, border_color="#fde68a")
        c.pack(fill="x", pady=4)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(side="right", padx=12)
        button(row, "Build lesson", lambda: self.app.build_session(p["dir"], p["title"])).pack(side="left", padx=3)
        button(row, "Folder", lambda: open_folder(p["dir"]), "ghost", width=66).pack(side="left", padx=3)
        ctk.CTkLabel(c, text="●", text_color="#d97706", font=F(16), width=30).pack(side="left", padx=(14, 6), pady=12)
        txt = ctk.CTkFrame(c, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True, pady=8)
        ctk.CTkLabel(txt, text=p["title"], font=F(14, "bold"), text_color=INK, anchor="w").pack(fill="x")
        ctk.CTkLabel(txt, text=f"Recorded {p['date']}   ·   {fmt_dur(p['duration'])}", font=F(12),
                     text_color=MUTED, anchor="w").pack(fill="x")


class SettingsPage(ctk.CTkScrollableFrame):
    def __init__(self, app):
        super().__init__(app.holder(), fg_color=BG)
        self.app = app
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=34)
        page_header(wrap, "Settings", "These apply to lessons you build from now on. To apply them to an existing "
                                      "lesson, press Update on the Lessons page.")
        b = load_branding()
        self.b = b

        c = Card(wrap, "Branding", "Shown in the top bar of every lesson and in the Word step guide.")
        c.pack(fill="x", pady=(0, 14))
        for key, label in (("app_name", "App name"), ("organisation", "Unit / organisation"), ("author", "Author")):
            r = self.row(c.body, label)
            ctk.CTkLabel(r, text=b.get(key, ""), font=F(13, "bold"), text_color=INK, anchor="w").pack(side="left")
        r = self.row(c.body, "Colour")
        ctk.CTkLabel(r, text="", width=34, height=24, corner_radius=6, fg_color=b.get("accent", ACCENT)).pack(side="left")
        ctk.CTkLabel(r, text=b.get("accent", ACCENT), font=F(13), text_color=MUTED).pack(side="left", padx=8)
        r = self.row(c.body, "Logo")
        logo = os.path.join(APP_DIR, b.get("logo", "logo.png"))
        if Image and os.path.exists(logo):
            try:
                ctk.CTkLabel(r, image=ctk.CTkImage(Image.open(logo), size=(30, 30)), text="").pack(side="left")
            except Exception:
                pass
        ctk.CTkLabel(r, text=b.get("logo", ""), font=F(13), text_color=MUTED).pack(side="left", padx=8)

        c = Card(wrap, "Video & pacing", "Slower pacing helps beginners follow each click.")
        c.pack(fill="x", pady=(0, 14))
        self.zoom = self.slider(c.body, "Zoom on clicks", 1.0, 3.0, float(b.get("zoom", 2.0)), "{:.1f}×", 20)
        self.pause = self.slider(c.body, "Hold at each click", 0.0, 2.5, float(b.get("action_pause", 1.0)), "{:.1f} s", 25)
        self.spause = self.slider(c.body, "Pause between steps", 0.0, 3.0, float(b.get("step_pause", 1.0)), "{:.1f} s", 30)
        r = self.row(c.body, "Normal speed (1×)")
        self.speeds = {"0.4× of recorded": 0.4, "0.5× of recorded (default)": 0.5, "0.6× of recorded": 0.6,
                       "0.75× of recorded": 0.75, "Same as recorded": 1.0}
        self.speed = ctk.CTkOptionMenu(r, values=list(self.speeds), width=230, **MENU)
        cur = float(b.get("normal_speed", 0.5))
        self.speed.set(next((k for k, v in self.speeds.items() if abs(v - cur) < 0.01), "0.5× of recorded (default)"))
        self.speed.pack(side="left")
        ctk.CTkLabel(r, text="What 1× means in the player. Students can still choose faster or slower.",
                     font=F(12), text_color=MUTED).pack(side="left", padx=10)

        c = Card(wrap, "Lesson page")
        c.pack(fill="x", pady=(0, 14))
        self.sw_edit = ctk.CTkSwitch(c.body, text="Show the ✎ Edit lesson button on the start screen",
                                     font=F(13), progress_color=ACCENT)
        self.sw_edit.pack(anchor="w", pady=3)
        if b.get("show_edit_button", True):
            self.sw_edit.select()
        self.sw_shots = ctk.CTkSwitch(c.body, text="Include screenshots in the Word step guide", font=F(13),
                                      progress_color=ACCENT)
        self.sw_shots.pack(anchor="w", pady=3)
        if b.get("guide_screenshots"):
            self.sw_shots.select()

        button(wrap, "Save settings", self.save, height=42).pack(anchor="w", pady=(4, 18))

        c = Card(wrap, "About StepCast")
        c.pack(fill="x", pady=(0, 30))
        ctk.CTkLabel(c.body, text=f"StepCast {VERSION}", font=F(13, "bold"), text_color=INK, anchor="w").pack(fill="x")
        ctk.CTkLabel(c.body, text="Developed by Dr Sivakumar Manickam  ·  skumar@staff.odc.edu.om\n"
                                  "Head of Educational Technology & Resources, Oman Dental College\n"
                                  "Conceived, designed, tested and led by Dr Sivakumar Manickam, "
                                  "developed with the help of Claude (Anthropic) as an AI coding assistant.",
                     font=F(12), text_color=MUTED, anchor="w", justify="left", wraplength=640).pack(fill="x", pady=(2, 0))

    def row(self, parent, label):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=5)
        ctk.CTkLabel(r, text=label, font=F(13), text_color=INK, width=170, anchor="w").pack(side="left")
        return r

    def slider(self, parent, label, lo, hi, val, fmt, steps):
        r = self.row(parent, label)
        lbl = ctk.CTkLabel(r, text=fmt.format(val), font=F(13, "bold"), text_color=INK, width=60)
        s = ctk.CTkSlider(r, from_=lo, to=hi, number_of_steps=steps, width=280, button_color=ACCENT,
                          button_hover_color=ACCENT_HOVER, progress_color=ACCENT,
                          command=lambda v: lbl.configure(text=fmt.format(v)))
        s.set(val)
        s.pack(side="left")
        lbl.pack(side="left", padx=10)
        return s

    def save(self):
        b = load_branding()            # branding itself is fixed; only pacing/options change here
        b["zoom"] = round(self.zoom.get(), 1)
        b["action_pause"] = round(self.pause.get(), 1)
        b["step_pause"] = round(self.spause.get(), 1)
        b["normal_speed"] = self.speeds[self.speed.get()]
        b["show_edit_button"] = bool(self.sw_edit.get())
        b["guide_screenshots"] = bool(self.sw_shots.get())
        with open(BRANDING, "w", encoding="utf-8") as f:
            json.dump(b, f, indent=2, ensure_ascii=False)
        self.b = b
        self.app.toast("Settings saved.")
        self.app.refresh_sidebar()


# ============================================================================ library
def scan_library():
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    from build_lesson import read_lesson, BUILDER_VERSION
    lessons, built = [], set()
    if os.path.isdir(LESSONS_DIR):
        for name in os.listdir(LESSONS_DIR):
            d = os.path.join(LESSONS_DIR, name)
            if not os.path.exists(os.path.join(d, "index.html")):
                continue
            try:
                L = read_lesson(d)
            except Exception:
                continue
            mt = os.path.getmtime(os.path.join(d, "index.html"))
            lessons.append({"dir": d, "title": L.get("title", name), "steps": len(L.get("steps", [])),
                            "duration": L.get("duration", 0), "mtime": mt,
                            "date": _dt.datetime.fromtimestamp(mt).strftime("%d %b %Y"),
                            "narrated": sum(1 for s in L.get("steps", []) if s.get("audio")),
                            "outdated": L.get("builder") != BUILDER_VERSION})
            built.add(name[-17:])                         # lesson folders end with the recording's date stamp
            if L.get("id"):
                built.add(L["id"][-17:])
    lessons.sort(key=lambda x: -x["mtime"])
    pending = []
    if os.path.isdir(SESSIONS_DIR):
        for name in sorted(os.listdir(SESSIONS_DIR), reverse=True):
            d = os.path.join(SESSIONS_DIR, name)
            mp = os.path.join(d, "meta.json")
            if name in built or not os.path.exists(mp):
                continue
            try:
                with open(mp, encoding="utf-8") as f:
                    m = json.load(f)
            except Exception:
                continue
            try:
                date = _dt.datetime.strptime(name, "%Y-%m-%d_%H%M%S").strftime("%d %b %Y, %H:%M")
            except ValueError:
                date = name
            pending.append({"dir": d, "title": m.get("title", "Untitled lesson"), "date": date,
                            "duration": m.get("duration", 0)})
    return lessons, pending


# ============================================================================ app
class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.title("StepCast")
        self.geometry("1120x760")
        self.minsize(960, 640)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.rec = None
        self.overlay = None
        self.busy = False
        self.editor = EditServer(LESSONS_DIR)      # lets "Save lesson" write straight into the lesson folder
        try:
            if IS_WIN and os.path.exists(os.path.join(APP_DIR, "logo.ico")):
                self.iconbitmap(default=os.path.join(APP_DIR, "logo.ico"))
            elif Image and os.path.exists(os.path.join(APP_DIR, "logo.png")):
                self._icon = tk.PhotoImage(file=os.path.join(APP_DIR, "logo.png"))
                self.iconphoto(True, self._icon)
        except Exception:
            pass

        # ---- sidebar
        sb = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0, width=230)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sb.pack_propagate(False)
        top = ctk.CTkFrame(sb, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(24, 26))
        logo = os.path.join(APP_DIR, "logo.png")
        if Image and os.path.exists(logo):
            img = ctk.CTkImage(Image.open(logo), size=(36, 36))
            ctk.CTkLabel(top, image=img, text="").pack(side="left")
        t = ctk.CTkFrame(top, fg_color="transparent")
        t.pack(side="left", padx=10)
        ctk.CTkLabel(t, text="StepCast", font=F(20, "bold"), text_color="white", anchor="w").pack(fill="x")
        ctk.CTkLabel(t, text="Screen lessons", font=F(11), text_color="#9fc9c4", anchor="w").pack(fill="x")

        self.nav = {}
        for key, label in (("record", "●   Record"), ("lessons", "▤   Lessons"), ("settings", "⚙   Settings")):
            b = ctk.CTkButton(sb, text=label, anchor="w", height=42, corner_radius=10, font=F(14, "bold"),
                              fg_color="transparent", hover_color=SIDEBAR_HOVER, text_color="#d1e7e4",
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=14, pady=3)
            self.nav[key] = b
        self.who = ctk.CTkLabel(sb, text="", font=F(11), text_color="#8fb8b3", anchor="w", justify="left")
        self.who.pack(side="bottom", fill="x", padx=22, pady=(0, 20))
        self.refresh_sidebar()

        # ---- content + status bar
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkFrame(self, fg_color="#e9eef0", corner_radius=0, height=36)
        self.status.grid(row=1, column=1, sticky="ew")
        self.status_lbl = ctk.CTkLabel(self.status, text=self.ready_text(), font=F(12), text_color=MUTED, anchor="w")
        self.status_lbl.pack(side="left", padx=16, pady=4)
        self.prog = ctk.CTkProgressBar(self.status, width=180, mode="indeterminate", progress_color=ACCENT)

        # each page lives in its own plain frame; switching pages raises that frame
        self.holders = {}
        self.pages = {}
        for key, cls in (("record", RecordPage), ("lessons", LessonsPage), ("settings", SettingsPage)):
            self._next_key = key
            page = cls(self)
            page.pack(fill="both", expand=True)
            self.pages[key] = page
        self.show("record")
        self.after(300, self.poll)

    def holder(self):
        h = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        h.grid(row=0, column=0, sticky="nsew")
        self.holders[self._next_key] = h
        return h

    def ready_text(self):
        bits = []
        if IS_WIN and not capture.find_ffmpeg():
            bits.append("⚠ ffmpeg not found – install it with:  winget install Gyan.FFmpeg")
        if IS_WIN and capture.uia is None:
            bits.append("⚠ uiautomation not installed – step names will be generic (run setup.bat)")
        return "   ".join(bits) or f"Ready  ·  StepCast {VERSION}"

    def refresh_sidebar(self):
        b = load_branding()
        self.who.configure(text=f"StepCast {VERSION}\nDr Sivakumar Manickam")

    def report_callback_exception(self, exc, val, tb):
        import traceback
        msg = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(_dt.datetime.now().isoformat() + "\n" + msg + "\n")
        except OSError:
            pass
        messagebox.showerror("StepCast – something went wrong", f"{val}\n\nDetails were saved to {LOG_FILE}")

    def show(self, key):
        for k, b in self.nav.items():
            b.configure(fg_color=SIDEBAR_HOVER if k == key else "transparent",
                        text_color="white" if k == key else "#d1e7e4")
        if key == "lessons":
            self.pages["lessons"].refresh()
        self.holders[key].tkraise()

    def toast(self, text, busy=False):
        self.status_lbl.configure(text=text, text_color=INK if busy else MUTED)
        if busy:
            self.prog.pack(side="right", padx=16)
            self.prog.start()
        else:
            self.prog.stop()
            self.prog.pack_forget()

    # ------------------------------------------------------------- recording
    def begin_recording(self, title, fps, region, source, countdown, show_frame):
        if not IS_WIN:
            messagebox.showinfo("StepCast", "Recording works on Windows only.")
            return
        if not capture.find_ffmpeg():
            messagebox.showerror("StepCast", "ffmpeg was not found.\n\nInstall it with:  winget install Gyan.FFmpeg\n"
                                             "or put ffmpeg.exe and ffprobe.exe in the StepCast folder.")
            return
        self.iconify()

        def go():
            try:
                self.rec = capture.Recorder(title, fps, region=region, source=source)
                self.rec.start()
            except Exception as e:
                self.deiconify()
                messagebox.showerror("StepCast", str(e))
                return
            self.overlay = RecordingOverlay(self, region, self.rec, show_frame, self.stop_recording)
        self.after(350, (lambda: Countdown(self, region, 3, go)) if countdown else go)

    def stop_recording(self):
        if self.rec and self.rec.running:
            threading.Thread(target=self.rec.stop, daemon=True).start()

    def poll(self):
        """Main-thread check: a recording may have been stopped by the hotkey on another thread."""
        r = self.rec
        if r is not None and not r.running and r.t_launch is not None and not getattr(r, "_handled", False):
            meta_p = os.path.join(r.dir, "meta.json")
            if os.path.exists(meta_p):
                r._handled = True
                duration = 0
                try:
                    with open(meta_p, encoding="utf-8") as f:
                        duration = json.load(f).get("duration", 0)
                except Exception:
                    pass
                if self.overlay:
                    self.overlay.close()
                    self.overlay = None
                self.deiconify()
                self.lift()
                self.show("record")
                self.pages["record"].show_saved(r.title, duration, r.dir)
                self.toast("Recording saved.")
        self.after(250, self.poll)

    # ------------------------------------------------------------- building
    def run_builder(self, args, log_dir, ok_msg, on_ok=None):
        if self.busy:
            messagebox.showinfo("StepCast", "Please wait – StepCast is still working on the previous lesson.")
            return
        self.busy = True
        self.toast("Working… this can take a minute", busy=True)

        def work():
            py = sys.executable
            if py.lower().endswith("pythonw.exe"):
                cand = py[:-len("pythonw.exe")] + "python.exe"
                if os.path.exists(cand):
                    py = cand
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            res = subprocess.run([py, os.path.join(APP_DIR, "build_lesson.py")] + args, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", env=env,
                                 creationflags=0x08000000 if IS_WIN else 0)
            log_path = os.path.join(log_dir, "build.log")
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write((res.stdout or "") + (res.stderr or ""))
            except OSError:
                pass

            def finish():
                self.busy = False
                if res.returncode == 0:
                    self.toast(ok_msg)
                    if on_ok:
                        on_ok()
                else:
                    self.toast("Build failed – see build.log")
                    messagebox.showerror("StepCast – build failed",
                                         (res.stderr or res.stdout or "")[-1500:] + "\n\nFull log: " + log_path)
            self.after(0, finish)
        threading.Thread(target=work, daemon=True).start()

    def ask_title(self, current):
        d = ctk.CTkToplevel(self)
        d.title("Build lesson")
        d.geometry("440x190")
        d.resizable(False, False)
        d.transient(self)
        d.grab_set()
        ctk.CTkLabel(d, text="Lesson title", font=F(14, "bold"), text_color=INK, anchor="w").pack(fill="x", padx=22, pady=(20, 6))
        e = ctk.CTkEntry(d, height=36, font=F(14))
        e.insert(0, "" if current in ("", "Untitled lesson") else current)
        e.pack(fill="x", padx=22)
        e.focus_set()
        result = {"v": None}
        row = ctk.CTkFrame(d, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=18)

        def ok(*_):
            result["v"] = e.get().strip() or "Untitled lesson"
            d.destroy()
        button(row, "Build lesson", ok).pack(side="right")
        button(row, "Cancel", d.destroy, "ghost").pack(side="right", padx=8)
        e.bind("<Return>", ok)
        self.wait_window(d)
        return result["v"]

    def build_session(self, session_dir, title):
        new = self.ask_title(title)
        if new is None:
            return
        mp = os.path.join(session_dir, "meta.json")
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
            m["title"] = new
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(m, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        self.run_builder([session_dir, "--title", new, "--open"], session_dir, f"Lesson “{new}” built.",
                         on_ok=lambda: self.show("lessons"))

    def update_lessons(self, dirs):
        """Update several lessons one after another."""
        if not dirs:
            self.pages["lessons"].refresh()
            return
        first, rest = dirs[0], dirs[1:]
        self.run_builder(["--rebuild", first], first, f"Updated {os.path.basename(first)}",
                         on_ok=lambda: self.update_lessons(rest))

    def update_lesson(self, lesson_dir):
        self.run_builder(["--rebuild", lesson_dir], lesson_dir, "Lesson updated.",
                         on_ok=lambda: self.pages["lessons"].refresh())


if __name__ == "__main__":
    prepare_folders()
    App().mainloop()
