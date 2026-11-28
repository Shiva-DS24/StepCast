r"""
Where StepCast keeps things.

    StepCast\                  <- HOME_DIR: what the teacher sees
        Install StepCast.bat
        Start StepCast.bat
        READ ME FIRST.pdf
        lessons\               <- finished lessons
        recordings\            <- raw recordings
        app\                   <- CODE_DIR: the program (this file lives here)

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
__version__ = "1.0.0"

import glob
import os
import shutil

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
# The program lives in StepCast\app; lessons and recordings sit next to it, in StepCast\.
HOME_DIR = os.path.dirname(CODE_DIR) if os.path.basename(CODE_DIR).lower() == "app" else CODE_DIR
LESSONS_DIR = os.path.join(HOME_DIR, "lessons")
RECORDINGS_DIR = os.path.join(HOME_DIR, "recordings")
LOG_FILE = os.path.join(HOME_DIR, "stepcast_error.log")


def prepare_folders():
    """Create lessons/ and recordings/; move recordings from older versions (sessions/)."""
    old = os.path.join(HOME_DIR, "sessions")
    if os.path.isdir(old) and not os.path.exists(RECORDINGS_DIR):
        try:
            os.rename(old, RECORDINGS_DIR)
        except OSError:
            pass
    for d in (LESSONS_DIR, RECORDINGS_DIR):
        os.makedirs(d, exist_ok=True)


def find_tool(name):
    """Find ffmpeg / ffprobe: next to StepCast, on PATH, or where 'winget install Gyan.FFmpeg' puts it
    (PATH changes from a fresh install are only seen after signing out, so look there directly)."""
    exe = name + (".exe" if os.name == "nt" else "")
    for d in (CODE_DIR, HOME_DIR, os.path.join(HOME_DIR, "tools"), os.path.join(CODE_DIR, "tools")):
        p = os.path.join(d, exe)
        if os.path.exists(p):
            return p
    p = shutil.which(name)
    if p:
        return p
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", "")
        cands = [os.path.join(la, "Microsoft", "WinGet", "Links", exe)]
        cands += glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", exe))
        cands += glob.glob(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "ffmpeg*", "bin", exe))
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        cands += [os.path.join(pf, "WinGet", "Links", exe)]
        cands += glob.glob(os.path.join(pf, "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", exe))
        cands += [os.path.join("C:\\", "ffmpeg", "bin", exe)]
        for p in cands:
            if os.path.exists(p):
                return p
    return None
