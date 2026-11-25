"""
StepCast capture engine (Windows)
---------------------------------
Records a screen area with ffmpeg together with a timeline of mouse clicks,
keystrokes, the text cursor and the names of the UI controls you click
(Windows UI Automation). Used by record.py (the StepCast app).

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


import ctypes
import datetime as _dt
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

IS_WIN = os.name == "nt"

# --- DPI awareness must be set before anything reads coordinates -------------
if IS_WIN:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

try:
    from pynput import keyboard, mouse  # noqa: E402
except Exception:      # lets the app's screens be previewed on other systems
    keyboard = mouse = None

try:
    import uiautomation as uia  # noqa: E402
except Exception:  # recorder still works, step titles are just generic
    uia = None

from paths import CODE_DIR as APP_DIR, RECORDINGS_DIR as SESSIONS_DIR, find_tool, prepare_folders
MOVE_INTERVAL = 0.05          # seconds between logged mouse-move samples
TYPING_GAP_FOR_FOCUS = 1.5    # new typing burst -> ask UIA which field has focus
CARET_INTERVAL = 0.3          # while typing, ask where the text cursor is this often


def find_ffmpeg():
    return find_tool("ffmpeg")


def primary_screen_size():
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def dpi_scale():
    try:
        return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0
    except Exception:
        return 1.0


# =============================================================================
class Recorder:
    """region = (x, y, w, h) in screen pixels; None = main screen.
    ignore_rects: screen rectangles (our own REC bar) whose clicks are not recorded."""

    def __init__(self, title, fps=25, region=None, on_stopped=None, source=""):
        self.title = title or "Untitled lesson"
        self.fps = fps
        self.on_stopped = on_stopped
        self.source = source
        self.ignore_rects = []
        self._ignored_buttons = set()
        stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.dir = os.path.join(SESSIONS_DIR, stamp)
        os.makedirs(self.dir, exist_ok=True)

        if region is None:
            w, h = primary_screen_size()
            region = (0, 0, w, h)
        x, y, w, h = [int(v) for v in region]
        self.x, self.y = x, y
        self.w, self.h = w - w % 2, h - h % 2      # H.264 needs even dimensions

        self.t_launch = None
        self.video_offset = None  # seconds between launch and first video frame
        self.proc = None
        self.running = False
        self.keys_paused = False
        self.mods = set()
        self._last_move = 0.0
        self._last_key_t = -999.0
        self._last_caret_q = -999.0
        self._click_since_key = True

        self.log_q = queue.Queue()
        self.uia_q = queue.Queue()

    # -------------------------------------------------------------- helpers
    def now(self):
        return time.perf_counter() - self.t_launch

    def log(self, ev):
        self.log_q.put(ev)

    # -------------------------------------------------------------- threads
    def _writer(self):
        path = os.path.join(self.dir, "events.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            while True:
                ev = self.log_q.get()
                if ev is None:
                    break
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()

    def _uia_worker(self):
        if uia is None:
            # drain the queue so it never blocks
            while self.uia_q.get() is not None:
                pass
            return
        with uia.UIAutomationInitializerInThread():
            while True:
                job = self.uia_q.get()
                if job is None:
                    break
                if job["kind"] == "caret":
                    wait = job["t"] + 0.08 - self.now()   # let the app draw the new character first
                    if wait > 0:
                        time.sleep(wait)
                    pos = caret_position(uia)
                    if pos:
                        x, y, h, src = pos
                        self.log({"type": "caret", "ref_t": job["t"], "t": self.now(),
                                  "x": x, "y": y, "h": h, "src": src})
                    continue
                try:
                    if job["kind"] == "point":
                        ctrl = uia.ControlFromPoint(job["x"], job["y"])
                    else:
                        ctrl = uia.GetFocusedControl()
                    info = describe_control(ctrl)
                except Exception as e:  # never let UIA errors kill recording
                    info = {"error": str(e)[:120]}
                info.update({"type": "uia", "kind": job["kind"], "ref_t": job["t"], "t": self.now()})
                self.log(info)

    def _progress_reader(self):
        """ffmpeg -progress gives out_time_us; launch->first-frame offset is
        estimated as min(now - out_time). Encoder lag only makes it larger,
        so the minimum is the best estimate."""
        best = None
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "ignore").strip()
            if line.startswith("out_time_us="):
                try:
                    us = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                if us <= 0:
                    continue
                est = self.now() - us / 1e6
                if best is None or est < best:
                    best = est
                    self.video_offset = best

    # -------------------------------------------------------------- input hooks
    def on_move(self, x, y):
        t = self.now()
        if t - self._last_move >= MOVE_INTERVAL:
            self._last_move = t
            self.log({"type": "move", "t": t, "x": x, "y": y})

    def _ignored(self, x, y):
        return any(l <= x < r and t <= y < b for (l, t, r, b) in self.ignore_rects)

    def on_click(self, x, y, button, pressed):
        t = self.now()
        btn = getattr(button, "name", str(button))
        # clicks on StepCast's own REC bar are not part of the lesson
        if pressed and self._ignored(x, y):
            self._ignored_buttons.add(btn)
            return
        if not pressed and btn in self._ignored_buttons:
            self._ignored_buttons.discard(btn)
            return
        self.log({"type": "down" if pressed else "up", "t": t, "x": x, "y": y, "button": btn})
        if pressed:
            self._click_since_key = True
            self.uia_q.put({"kind": "point", "x": x, "y": y, "t": t})

    def on_scroll(self, x, y, dx, dy):
        self.log({"type": "scroll", "t": self.now(), "x": x, "y": y, "dy": dy})

    def on_press(self, key):
        name = key_name(key)
        if name in ("ctrl", "alt", "shift", "win"):
            self.mods.add(name)
            return
        # ---- our own hotkeys (never logged) ----
        if "ctrl" in self.mods and "alt" in self.mods:
            if name == "end":
                threading.Thread(target=self.stop, daemon=True).start()
                return
            if name == "p":
                self.keys_paused = not self.keys_paused
                self.log({"type": "privacy", "t": self.now(), "on": self.keys_paused})
                return
        if self.keys_paused:
            return
        t = self.now()
        char = getattr(key, "char", None)
        if char is not None and (not char.isprintable() or "ctrl" in self.mods or "alt" in self.mods):
            char = None  # Ctrl+B etc. -> treat as a shortcut, not text
        mods = sorted(m for m in self.mods if m != "shift" or char is None)
        self.log({"type": "key", "t": t, "key": name, "char": char, "mods": mods})
        # first key of a new typing burst: ask which field has focus
        if (t - self._last_key_t > TYPING_GAP_FOR_FOCUS) or self._click_since_key:
            self.uia_q.put({"kind": "focus", "t": t})
        # where is the text going? (throttled)
        if t - self._last_caret_q >= CARET_INTERVAL or name in ("enter", "tab") or self._click_since_key:
            self._last_caret_q = t
            self.uia_q.put({"kind": "caret", "t": t})
        self._last_key_t = t
        self._click_since_key = False

    def on_release(self, key):
        name = key_name(key)
        if name in ("ctrl", "alt", "shift", "win"):
            self.mods.discard(name)

    def mark(self):
        """Force a step boundary here (not exposed in the app; steps are automatic)."""
        if self.running:
            self.log({"type": "mark", "t": self.now()})

    def elapsed(self):
        return self.now() if self.running and self.t_launch else 0.0

    # -------------------------------------------------------------- start/stop
    def start(self):
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("ffmpeg was not found. Put ffmpeg.exe next to record.py or add it to PATH.")
        self.video_path = os.path.join(self.dir, "capture.mkv")
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "gdigrab", "-framerate", str(self.fps), "-draw_mouse", "1",
            "-offset_x", str(self.x), "-offset_y", str(self.y), "-video_size", f"{self.w}x{self.h}",
            "-i", "desktop",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-crf", "20", "-pix_fmt", "yuv420p",
            "-progress", "pipe:1", "-nostats",
            self.video_path,
        ]
        self.ffmpeg_log = open(os.path.join(self.dir, "ffmpeg.log"), "wb")
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        self.t_launch = time.perf_counter()
        self.started_at = _dt.datetime.now().isoformat(timespec="seconds")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.ffmpeg_log, creationflags=flags)
        self.running = True
        threading.Thread(target=self._writer, daemon=True).start()
        threading.Thread(target=self._uia_worker, daemon=True).start()
        threading.Thread(target=self._progress_reader, daemon=True).start()
        self.mouse_l = mouse.Listener(on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll)
        self.key_l = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.mouse_l.start()
        self.key_l.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        duration = self.now()
        try:
            self.mouse_l.stop()
            self.key_l.stop()
        except Exception:
            pass
        try:
            self.proc.stdin.write(b"q")
            self.proc.stdin.flush()
            self.proc.wait(timeout=15)
        except Exception:
            self.proc.terminate()
        self.ffmpeg_log.close()
        self.uia_q.put(None)
        time.sleep(0.3)
        self.log_q.put(None)
        meta = {
            "version": 1,
            "title": self.title,
            "started_at": self.started_at,
            "screen": {"w": self.w, "h": self.h},
            "region": {"x": self.x, "y": self.y, "w": self.w, "h": self.h},
            "source": self.source,
            "dpi_scale": dpi_scale(),
            "fps": self.fps,
            "video": "capture.mkv",
            "video_offset": self.video_offset if self.video_offset is not None else 0.5,
            "duration": duration,
            "uia": uia is not None,
        }
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        if self.on_stopped:
            self.on_stopped(self)


# =============================================================================
NOISE_NAMES = {"", "Ribbon", "Lower Ribbon", "Ribbon Tabs", "MsoDockTop", "MsoDockBottom",
               "Desktop", "Desktop 1", "Task Switching", "Running applications"}


# ---------------------------------------------------------------- text caret
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("flags", ctypes.c_ulong),
                ("hwndActive", ctypes.c_void_p), ("hwndFocus", ctypes.c_void_p),
                ("hwndCapture", ctypes.c_void_p), ("hwndMenuOwner", ctypes.c_void_p),
                ("hwndMoveSize", ctypes.c_void_p), ("hwndCaret", ctypes.c_void_p),
                ("rcCaret", _RECT)]


_IAccessible = None


def _msaa_caret(hwnd):
    """Ask the window's accessibility object where its caret is (works in Word, Notepad, most editors)."""
    global _IAccessible
    try:
        import comtypes
        import comtypes.client
        if _IAccessible is None:
            comtypes.client.GetModule("oleacc.dll")
            from comtypes.gen.Accessibility import IAccessible
            _IAccessible = IAccessible
        acc = ctypes.POINTER(_IAccessible)()
        OBJID_CARET = 0xFFFFFFF8
        hr = ctypes.oledll.oleacc.AccessibleObjectFromWindow(
            ctypes.c_void_p(hwnd), ctypes.c_ulong(OBJID_CARET),
            ctypes.byref(_IAccessible._iid_), ctypes.byref(acc))
        if hr != 0 or not acc:
            return None
        l, t, w, h = acc.accLocation(0)
        if w == 0 and h == 0 and l == 0 and t == 0:
            return None
        return l, t, w, h
    except Exception:
        return None


def caret_position(uia_mod=None):
    """Screen position of the text cursor in the foreground app: (x, y_middle, height, source) or None."""
    try:
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(_GUITHREADINFO)
        if not ctypes.windll.user32.GetGUIThreadInfo(0, ctypes.byref(info)):
            return None
        # 1) the classic Win32 caret
        if info.hwndCaret:
            r = info.rcCaret
            if r.bottom > r.top:
                pt = _POINT(r.left, r.top)
                ctypes.windll.user32.ClientToScreen(ctypes.c_void_p(info.hwndCaret), ctypes.byref(pt))
                h = r.bottom - r.top
                return pt.x, pt.y + h // 2, h, "win32"
        # 2) MSAA caret object on the focused window
        hwnd = info.hwndFocus or info.hwndActive
        if hwnd:
            loc = _msaa_caret(hwnd)
            if loc:
                l, t, w, h = loc
                return l, t + h // 2, h, "msaa"
    except Exception:
        pass
    # 3) UI Automation text selection (modern apps)
    if uia_mod is not None:
        try:
            ctrl = uia_mod.GetFocusedControl()
            tp = ctrl.GetPattern(uia_mod.PatternId.TextPattern)
            if tp:
                rng = tp.GetSelection()[0]
                rects = rng.GetBoundingRectangles()
                if not rects:
                    rng = rng.Clone()
                    rng.ExpandToEnclosingUnit(uia_mod.TextUnit.Character)
                    rects = rng.GetBoundingRectangles()
                if rects:
                    r = rects[-1]
                    return r.right, (r.top + r.bottom) // 2, r.bottom - r.top, "uia"
        except Exception:
            pass
    return None


def describe_control(ctrl):
    if ctrl is None:
        return {}
    r = ctrl.BoundingRectangle
    info = {
        "name": (ctrl.Name or "")[:120],
        "ctype": ctrl.ControlTypeName,
        "auto_id": (ctrl.AutomationId or "")[:80],
        "rect": [r.left, r.top, r.right, r.bottom],
    }
    try:
        info["is_password"] = bool(ctrl.IsPassword)
    except Exception:
        info["is_password"] = False
    ancestors = []
    p = ctrl
    for _ in range(10):
        try:
            p = p.GetParentControl()
        except Exception:
            break
        if p is None:
            break
        nm = (p.Name or "")[:80]
        if p.ControlTypeName == "WindowControl" or nm in NOISE_NAMES:
            if p.ControlTypeName == "WindowControl" and "window" not in info:
                info["window"] = nm
            continue
        ancestors.append([nm, p.ControlTypeName])
    info["ancestors"] = ancestors
    try:
        top = ctrl.GetTopLevelControl()
        if top is not None:
            info["app"] = (top.Name or "")[:120]
    except Exception:
        pass
    return info


def key_name(key):
    if isinstance(key, keyboard.Key):
        n = key.name
        for m in ("ctrl", "alt", "shift"):
            if n.startswith(m):
                return m
        if n.startswith("cmd"):
            return "win"
        return n
    if getattr(key, "vk", None) is not None:
        vk = key.vk
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            return chr(vk).lower()
    ch = getattr(key, "char", None)
    return (ch or "?").lower()



# =============================================================================
# Windows helpers: monitors, windows, and keeping StepCast's own overlays out of the video
# =============================================================================
class _MONITORINFOEX(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT), ("rcWork", _RECT),
                ("dwFlags", ctypes.c_ulong), ("szDevice", ctypes.c_wchar * 32)]


def monitors():
    """[{name, x, y, w, h, primary}] - physical pixels."""
    if not IS_WIN:
        return [{"name": "Display 1", "x": 0, "y": 0, "w": 1920, "h": 1080, "primary": True}]
    out = []
    MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.POINTER(_RECT), ctypes.c_ssize_t)

    def cb(hmon, hdc, lprc, data):
        mi = _MONITORINFOEX()
        mi.cbSize = ctypes.sizeof(_MONITORINFOEX)
        ctypes.windll.user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(mi))
        r = mi.rcMonitor
        out.append({"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top,
                    "primary": bool(mi.dwFlags & 1)})
        return 1
    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    except Exception:
        pass
    if not out:     # fall back to the main screen
        w, h = primary_screen_size()
        out.append({"x": 0, "y": 0, "w": w, "h": h, "primary": True})
    out.sort(key=lambda m: (not m["primary"], m["x"], m["y"]))
    for i, m in enumerate(out, 1):
        m["name"] = f"Display {i}  ({m['w']}×{m['h']}{', main' if m['primary'] else ''})"
    return out


def window_rect(hwnd):
    """Visible bounds of a window (without the invisible resize border)."""
    r = _RECT()
    try:
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
                                                      ctypes.byref(r), ctypes.sizeof(r)) == 0:
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def list_windows(exclude_pid=None):
    """Visible application windows: [{hwnd, title}]"""
    if not IS_WIN:
        return [{"hwnd": 1, "title": "Document1 - Word"}, {"hwnd": 2, "title": "Moodle - Microsoft Edge"}]
    user32 = ctypes.windll.user32
    out = []
    pid_self = exclude_pid or os.getpid()
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        try:                      # never let one odd window stop the whole list
            add(hwnd)
        except Exception:
            pass
        return True

    def add(hwnd):
        h = ctypes.c_void_p(hwnd)
        if not user32.IsWindowVisible(h):
            return
        n = user32.GetWindowTextLengthW(h)
        if n == 0:
            return
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        title = buf.value.strip()
        if not title or title in ("Program Manager", "Windows Input Experience", "Settings"):
            return
        ex = user32.GetWindowLongW(h, -20)                             # GWL_EXSTYLE
        if ex & 0x00000080:                                            # WS_EX_TOOLWINDOW
            return
        if user32.GetWindow(h, 4):                                     # GW_OWNER: dialogs/popups of another window
            return
        cloaked = ctypes.c_int(0)
        try:
            ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)
        except Exception:
            pass
        if cloaked.value:                                              # hidden UWP shells, other desktops
            return
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == pid_self:
            return
        minimized = bool(user32.IsIconic(h))
        if not minimized:
            x, y, w, hh = window_rect(hwnd)
            if w < 120 or hh < 80:
                return
        out.append({"hwnd": hwnd, "title": title + ("   (minimized)" if minimized else "")})
    proc = EnumWindowsProc(cb)          # keep a reference while Windows calls back
    user32.EnumWindows(proc, 0)
    return out


def bring_to_front(hwnd):
    if not IS_WIN:
        return
    user32 = ctypes.windll.user32
    try:
        if user32.IsIconic(ctypes.c_void_p(hwnd)):
            user32.ShowWindow(ctypes.c_void_p(hwnd), 9)        # SW_RESTORE
            time.sleep(0.4)
        # Windows only lets the foreground app hand over focus; a harmless Alt tap unlocks it
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    except Exception:
        pass


def hwnd_of(tk_window):
    """Top-level HWND of a Tk window."""
    tk_window.update_idletasks()
    return ctypes.windll.user32.GetAncestor(ctypes.c_void_p(tk_window.winfo_id()), 2)   # GA_ROOT


def exclude_from_capture(tk_window):
    """Keep a window visible to you but out of the recording (Windows 10 2004+)."""
    if not IS_WIN:
        return False
    try:
        WDA_EXCLUDEFROMCAPTURE = 0x11
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd_of(tk_window)),
                                                                   WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


def make_click_through(tk_window):
    """Mouse clicks pass through the window to whatever is underneath."""
    if not IS_WIN:
        return
    try:
        h = ctypes.c_void_p(hwnd_of(tk_window))
        ex = ctypes.windll.user32.GetWindowLongW(h, -20)
        ctypes.windll.user32.SetWindowLongW(h, -20, ex | 0x80000 | 0x20)   # WS_EX_LAYERED | WS_EX_TRANSPARENT
    except Exception:
        pass
