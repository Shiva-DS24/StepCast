# StepCast

[![DOI](https://zenodo.org/badge/github/1471309411.svg)](https://doi.org/10.5281/zenodo.24575109)

**Turn a screen recording into a step-by-step interactive lesson.**

StepCast records a teacher doing a task in any Windows application (for example, inserting a table in Word) and turns the recording into a self-contained HTML lesson that students can follow at their own pace. It also produces a printable Word step guide.

While the teacher works at normal speed, StepCast records the screen together with a log of clicks, keystrokes, the text-cursor position and the names of the buttons and menus used (Windows UI Automation). From this it automatically:

- splits the video into **named steps** (e.g. *Open the "Insert" tab*, *Click "Table"*)
- adds a **calm auto-zoom camera** that frames where the action happens
- adds **speech-bubble callouts** showing what is clicked, and what is typed, letter by letter
- slows the lesson to a **novice-friendly pace**, with a pause before each step
- writes a **Word step guide** with a numbered table of the steps

Teachers can then edit step titles and callouts and record narration for each step in the browser. A lesson is a folder of plain files that works offline, from a USB stick or network share, or inside a VLE such as Moodle (upload as a *File* resource and set `index.html` as the main file). No plugin or server is needed.

**Demo video (4 min):** [docs/StepCast_demo.mp4](docs/StepCast_demo.mp4) shows a lesson being recorded, built, played and edited.

## Requirements

- **Teachers** (recording, building and editing lessons): **Windows 10 (version 2004 or later) or Windows 11.** StepCast is a Windows application: recording relies on Windows UI Automation and Windows screen-capture features.
- **Students** (watching lessons): any device with a modern web browser.

## Install (Windows, for teachers)

1. Download this repository (green **Code** button → **Download ZIP**) and unzip it.
2. Double-click **`Install StepCast.bat`**. It installs Python 3.12 and FFmpeg with `winget` if needed, installs the Python libraries, and creates desktop and Start-menu shortcuts.
3. Start StepCast from the desktop icon, or double-click **`Start StepCast.bat`**.

The illustrated teacher guide is **`READ ME FIRST.pdf`**.

## Testing the lesson builder from source (for reviewers and developers)

The lesson builder (`build_lesson.py`) is plain Python and can be run from source, including by reviewers who do not have Windows, using a synthetic recording that imitates a Word demonstration. You need Python 3.10+ and FFmpeg/ffprobe on your `PATH`.

```bash
pip install python-docx pillow
python app/tests/make_mock_session.py /tmp/stepcast_mock      # creates capture.mkv, events.jsonl, meta.json
python app/build_lesson.py /tmp/stepcast_mock -o /tmp/stepcast_lesson --open
```

This produces `index.html`, `video.mp4`, `lesson.json` and `step_guide.docx` in `/tmp/stepcast_lesson`. A lesson already built from the same mock recording is included in `app/examples/demo_lesson/` (open its `index.html` in a browser).

## Repository layout

```
Install StepCast.bat, Start StepCast.bat        Windows install / start
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

## Third-party software

StepCast's own code is MIT-licensed. It does not include or redistribute any third-party software. The installer downloads the following from their official sources onto the teacher's computer, and StepCast uses them unmodified, each under its own licence:

| Component | Used for | Licence |
|---|---|---|
| [FFmpeg](https://ffmpeg.org) (Gyan.FFmpeg build via winget) | Screen capture and video encoding, run as a separate program | LGPL 2.1+ / GPL (this build) |
| [Python](https://www.python.org) | Runs StepCast | PSF License |
| [pynput](https://github.com/moses-palmer/pynput) | Mouse and keyboard hooks | LGPL 3.0 |
| [uiautomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) | Windows UI Automation access | Apache 2.0 |
| [python-docx](https://github.com/python-openxml/python-docx) | Word step guide | MIT |
| [Pillow](https://python-pillow.org) | Image handling | MIT-CMU (HPND) |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | Desktop interface | MIT |

## Licence

[MIT](LICENSE)

## Citation

If you use StepCast in your teaching or research, please cite it. The repository includes a [`CITATION.cff`](CITATION.cff) file, so GitHub's **Cite this repository** button gives the reference in APA or BibTeX format.

StepCast is archived on Zenodo. To cite all versions, use DOI [10.5281/zenodo.24575109](https://doi.org/10.5281/zenodo.24575109). To cite version 1.0.0 specifically, use DOI [10.5281/zenodo.24575110](https://doi.org/10.5281/zenodo.24575110).

A software paper describing StepCast is in preparation; its DOI will be added here and in `CITATION.cff` once published.
