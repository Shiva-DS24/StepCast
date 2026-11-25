"""
StepCast edit helper
--------------------
A tiny web server that runs only on this computer (127.0.0.1) while the StepCast app is open.
When you press Edit in StepCast, the lesson opens through it, so "Save lesson" can write
straight into the lesson folder (and refresh the Word guide and narration files) - no downloads.

Only pages opened from StepCast can save: every save must carry a secret token that StepCast
puts in the address, and only folders inside the lessons folder can be written.

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
import mimetypes
import os
import secrets
import shutil
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, quote

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 200 * 1024 * 1024        # narration is embedded as audio data, allow generous lessons

mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/webm", ".webm")
mimetypes.add_type("video/mp4", ".mp4")


class EditServer:
    def __init__(self, lessons_dir):
        self.root = os.path.realpath(lessons_dir)
        self.token = secrets.token_urlsafe(18)
        self.httpd = None
        self.port = None
        self.lock = threading.Lock()        # one save at a time

    def start(self):
        if self.httpd:
            return
        os.makedirs(self.root, exist_ok=True)
        server = self

        class Handler(_Handler):
            srv = server
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd = None

    def edit_url(self, lesson_dir):
        self.start()
        rel = os.path.relpath(os.path.realpath(lesson_dir), self.root).replace(os.sep, "/")
        return f"http://127.0.0.1:{self.port}/{quote(rel)}/index.html?edit&token={self.token}"

    # ---- the save itself (runs on a server thread)
    def save(self, folder, lesson):
        d = os.path.realpath(os.path.join(self.root, folder))
        if os.path.dirname(d) != self.root or not os.path.exists(os.path.join(d, "index.html")):
            raise ValueError("Unknown lesson folder")
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import build_lesson
        with self.lock:
            # keep one backup of the previous version, just in case
            try:
                shutil.copyfile(os.path.join(d, "index.html"), os.path.join(d, "index.backup.html"))
            except OSError:
                pass
            build_lesson.finish(lesson, d, only_missing=True)    # writes index.html, Word guide, audio files
        return {"ok": True, "guide": bool(lesson.get("guide")),
                "narrated": sum(1 for s in lesson.get("steps", []) if s.get("audio"))}


class _Handler(BaseHTTPRequestHandler):
    srv = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):          # keep quiet (pythonw has no console)
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------------------------------------------------------------- files (with video seeking)
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/ping":
            return self._json(200, {"ok": True})
        rel = unquote(u.path).lstrip("/")
        p = os.path.realpath(os.path.join(self.srv.root, rel))
        if not p.startswith(self.srv.root + os.sep) or not os.path.isfile(p):
            return self._json(404, {"error": "not found"})
        size = os.path.getsize(p)
        ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].partition("-")
            try:
                if a:
                    start = int(a)
                    end = int(b) if b else size - 1
                else:                       # last N bytes
                    start = max(0, size - int(b))
            except ValueError:
                start, end = 0, size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        length = end - start + 1
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store" if p.endswith(".html") else "no-cache")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1 << 16, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def do_HEAD(self):
        self.do_GET()

    # ---------------------------------------------------------------- save
    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path != "/api/save":
            return self._json(404, {"error": "not found"})
        if q.get("token", [""])[0] != self.srv.token:
            return self._json(403, {"error": "This page was not opened from StepCast, so it cannot save here."})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._json(413, {"error": "The lesson is too large to save."})
        try:
            lesson = json.loads(self.rfile.read(n).decode("utf-8"))
            result = self.srv.save(q.get("lesson", [""])[0], lesson)
            self._json(200, result)
        except Exception as e:
            traceback.print_exc()
            self._json(500, {"error": str(e)})
