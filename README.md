# StepCast

**Turn a screen recording into a step-by-step interactive lesson.**

StepCast records a teacher doing a task in any Windows application (for example, inserting a table in Word) and turns the recording into a self-contained HTML lesson that students can follow at their own pace. It also produces a printable Word step guide.

While the teacher works at normal speed, StepCast records the screen together with a log of clicks, keystrokes, the text-cursor position and the names of the buttons and menus used (Windows UI Automation). From this it automatically:

- splits the video into **named steps** (e.g. *Open the "Insert" tab*, *Click "Table"*)
- adds a **calm auto-zoom camera** that frames where the action happens
- adds **speech-bubble callouts** showing what is clicked, and what is typed, letter by letter
- slows the lesson to a **novice-friendly pace**, with a pause before each step
- writes a **Word step guide** with a numbered table of the steps

Teachers can then edit step titles and callouts and record narration for each step in the browser. A lesson is a folder of plain files that works offline, from a USB stick or network share, or inside a VLE such as Moodle (upload as a *File* resource and set `index.html` as the main file). No plugin or server is needed.

## Platform support

| Task | Windows 10 (2004+) / 11 | Linux / macOS |
| --- | --- | --- |
| Record | Yes (developed and tested) | No (recording uses Windows UI Automation) |
| Build, edit and update lessons | Yes (developed and tested) | Build pipeline tested on Linux from source (see below); installer scripts **not yet verified** |
| Play lessons | Any modern browser | Any modern browser |

## Install (Windows, for teachers)

1. Download this repository (green **Code** button → **Download ZIP**) and unzip it.
2. Double-click **`Install StepCast.bat`**. It installs Python 3.12 and FFmpeg with `winget` if needed, installs the Python libraries, and creates desktop and Start-menu shortcuts.
3. Start StepCast from the desktop icon, or double-click **`Start StepCast.bat`**.

The illustrated teacher guide is **`READ ME FIRST.pdf`**.

## Try the build pipeline without Windows (for reviewers and developers)

You can build a lesson on any OS from a synthetic recording that imitates a Word demonstration. You need Python 3.10+ and FFmpeg/ffprobe on your `PATH`.

```bash
pip install python-docx pillow
python app/tests/make_mock_session.py /tmp/stepcast_mock      # creates capture.mkv, events.jsonl, meta.json
python app/build_lesson.py /tmp/stepcast_mock -o /tmp/stepcast_lesson --open
```

This produces `index.html`, `video.mp4`, `lesson.json` and `step_guide.docx` in `/tmp/stepcast_lesson`. A lesson already built from the same mock recording is included in `app/examples/demo_lesson/` (open its `index.html` in a browser).

## Repository layout

```
Install StepCast.bat, Start StepCast.bat        Windows install / start
install-linux-mac.sh, start-linux-mac.sh        Linux & macOS (lesson management; not yet verified)
READ ME FIRST.pdf                               teacher guide
lessons/, recordings/                           created on use (kept out of git)
app/
  record.py            desktop app (Record / Lessons / Settings)
  capture.py           screen capture, input hooks, caret tracking, UI Automation
  build_lesson.py      recording -> lesson (steps, callouts, camera, pacing)
  step_guide.py        Word step guide
  editserver.py        local save helper for the in-browser editor (127.0.0.1 + token)
  player_template.html lesson player and editor (plain HTML/CSS/JS, no dependencies)
  paths.py             folder layout and FFmpeg lookup
  branding.json        name, organisation, colours, logo, pacing defaults
  tests/make_mock_session.py   synthetic recording for testing without Windows
  examples/demo_lesson/        lesson built from the synthetic recording
```

Developer notes are in [`app/README.md`](app/README.md).

## Privacy

All recording and processing happens on the teacher's computer; nothing is uploaded. Text typed into password fields is masked, and keystroke capture can be paused with **Ctrl + Alt + P**. Use dummy data when recording software that shows patient or student information.

## Authors and credits

- **Dr Sivakumar Manickam**, Oman Dental College: concept, design, development lead and testing ([skumar@staff.odc.edu.om](mailto:skumar@staff.odc.edu.om))
- **Shreya Sivakumar**: installation testing, troubleshooting and verification

The code was written with the help of Claude (Anthropic) as an AI coding assistant, under the first author's design, direction and testing.

## Licence

[MIT](LICENSE)

## Citation

A software paper describing StepCast is in preparation. Citation details and a DOI will be added here.
