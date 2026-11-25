# StepCast: developer notes

**StepCast 1.3**: interactive, step-by-step screen lessons.
**Developed by Dr Sivakumar Manickam** ([skumar@staff.odc.edu.om](mailto:skumar@staff.odc.edu.om)), Head of Educational Technology & Resources, Oman Dental College, with the help of Claude (Anthropic) as an AI coding assistant.

> Teachers: you don't need this file. Read **`READ ME FIRST.pdf`** in the StepCast folder.

## What it does

1. **Record** (Windows). `capture.py` records a screen area with ffmpeg (`gdigrab`) and logs a timeline alongside it: mouse clicks, drags, scrolls, keystrokes, the text-cursor position (Win32 caret, MSAA or UI Automation) and the names of the UI controls you click (Windows UI Automation).
2. **Build**. `build_lesson.py` turns a recording into a lesson folder. It works out the steps and their names, the callouts (speech bubbles pointing at each action), and a calm camera path (zoom and pan). It also writes a Word step guide (`step_guide.py`) and a self-contained `index.html` made from `player_template.html`.
3. **Play**. The lesson is plain HTML, CSS and JavaScript. It has a steps menu, a CSS-transform camera, callouts, holds at each click, a pause between steps, narration per step, progress tracking and an edit mode. It runs offline and inside Moodle.
4. **Edit**. When a lesson is opened with **Edit** in the app, `editserver.py` (a local server on 127.0.0.1 with a token) lets the page save straight back into its folder. Saving also re-runs `build_lesson.finish()`, which refreshes the Word guide and turns narration into audio files.

## Layout

```
StepCast/
  Install StepCast.bat / Start StepCast.bat       Windows install / start
  install-linux-mac.sh / start-linux-mac.sh       Linux & macOS (manage/edit; no recording)
  READ ME FIRST.pdf                               teacher guide
  lessons/            built lessons (one folder each: index.html, video.mp4, step_guide.docx, audio/, assets/)
  recordings/         raw recordings (capture.mkv, events.jsonl, meta.json)
  app/
    record.py         the StepCast app (CustomTkinter): Record / Lessons / Settings
    capture.py        recorder engine, caret + UI Automation, monitors/windows, capture-excluded overlays
    build_lesson.py   recording -> lesson; also `--rebuild` to refresh an existing lesson
    step_guide.py     Word step guide (python-docx)
    editserver.py     local save helper for edit mode
    player_template.html   the lesson player
    paths.py          folder layout, ffmpeg lookup
    branding.json     app name, unit, author, colour, logo, pacing defaults
    logo.png / logo.ico
    requirements.txt
    tests/make_mock_session.py   fake recording for testing the builder and player without Windows
    examples/demo_lesson/        a lesson built from the mock recording
```

## Running from source

```
cd app
python -m pip install -r requirements.txt        # plus ffmpeg + ffprobe on PATH
python record.py                                   # the app
python build_lesson.py ../recordings/<stamp> --title "My lesson" --open
python build_lesson.py --rebuild ../lessons/<folder>
python tests/make_mock_session.py /tmp/mock && python build_lesson.py /tmp/mock -o /tmp/lesson
```

`branding.json` keys: `app_name`, `organisation`, `author`, `logo`, `accent`, `zoom`, `action_pause` (s), `step_pause` (s), `normal_speed` (what "1×" means, as a share of the recorded speed; default 0.5), `default_speed`, `show_edit_button`, `guide_screenshots`.

## Notes

- Recording needs Windows 10 version 2004 or newer, or Windows 11, so that the overlays can be left out of the capture (`SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`).
- Lessons store their data as JSON inside `index.html` (`<script id="lesson-data">`). `lesson.json` is a copy.
- `BUILDER_VERSION` in `build_lesson.py` marks lessons made by older builds, and the app offers **Update** for them. Updating keeps titles, callouts and narration, and rebuilds the camera from the callouts.

## Credits

StepCast was conceived, designed, tested and led by **Dr Sivakumar Manickam** (skumar@staff.odc.edu.om), Oman Dental College. He defined its features and teaching approach, tested every version in real teaching, and directed each improvement. The code was written with the help of **Claude** (Anthropic), working as an AI coding assistant under his direction.

© 2026 Dr Sivakumar Manickam.
