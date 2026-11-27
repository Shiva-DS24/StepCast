# Changelog

StepCast follows [Semantic Versioning](https://semver.org/).

## [1.0.0] – 2026-11-27

First public, open-source release (MIT licence).

- Windows recorder: FFmpeg screen capture, input hooks and Windows UI Automation, recorded in parallel.
- Lesson builder: automatic step detection and naming, a calm auto-zoom camera path, action and typing callouts, and novice pacing.
- Self-contained offline HTML lesson player with step navigation, per-step narration and an in-browser editor.
- Printable Word step guide generated for every lesson.
- Synthetic test recording (`app/tests/make_mock_session.py`) and a demo lesson, so the builder can be tested without Windows.

Before this release, StepCast went through internal versions (0.x–1.3) during teaching use at Oman Dental College. Those versions were not published. Lessons built with them are offered a one-click **Update** to 1.0.0, which keeps the teacher's edits.
