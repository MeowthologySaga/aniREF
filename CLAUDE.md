# aniREF

Desktop tool (Python + PySide6 + PyAV) for analyzing game animation reference videos,
extracting key poses and composing them into sequences. Design, data model, UI layout,
shortcuts and milestones: `docs/DESIGN.md` — keep it updated when decisions change.
Reply to the user in Korean; user-facing docs (README, DESIGN.md) are Korean.

Shipped to other animators via a public GitHub repo (GPL-3.0): Windows only, portable zip +
per-user Inno Setup installer built by GitHub Actions on tag push. Code must not assume a dev
environment (no hardcoded paths, settings/logs via `appdata.py`, works with no Python installed).

## Commands
- Run: `.\.venv\Scripts\python.exe -m aniref` (or `.venv\Scripts\aniref.exe`)
- Tests: `.\.venv\Scripts\python.exe -m pytest -q` (UI tests run headless)
- Probe a video: `.\.venv\Scripts\aniref-probe.exe <file>`
- Look at the UI without a screen: `.\.venv\Scripts\python.exe tools\screenshots.py <out_dir> ko|en`
  renders every screen with realistic data (headless). For one-off captures use
  `QT_QPA_PLATFORM=offscreen` + `QT_QPA_FONTDIR=C:\Windows\Fonts` (Korean renders as boxes without it)
  and `widget.grab().save(...)`.
- Build: `packaging\build.ps1` (PyInstaller + `aniREF.exe --selftest` gate; see packaging/README.md).

## Rules that matter
- Frame accuracy is the product. Never use QMediaPlayer or time-based seeking; all
  frame access goes through `core/media/decoder.py` (`VideoDecoder.get_frame(n)`).
- Frame numbers are 0-based source frame indices everywhere in code and JSON;
  add `settings.frame_base` only when displaying.
- Source frames (video) and anim frames (`settings.anim_fps`, Maya timeline) are different
  units; sequence timing (`SequenceItem.hold`) is in anim frames.
- `VideoDecoder` is not thread-safe; the UI uses it from one worker thread only.
- `core/` holds no widgets and stays unit-testable; UI lives in `ui/`.
- UI is Korean/English switchable: every user-visible string goes through `ui/i18n.py`,
  never a bare literal. Phase names (Anticipation, Contact, ...) stay English in both.
- Shortcuts live only in `ui/shortcuts.py`; menus, tooltips, the `?` overlay, the status bar and
  the guide read from it. Guide text references keys as `{a:action_id}`, never typed out.
- Shipping a feature includes its help: update `ui/help/content.py` (both languages), the
  roadmap block there, and the `WORKFLOW` availability flags in `ui/welcome.py`.
- Every keyboard action should give visible feedback (viewer OSD) — users work eyes-on-viewer.
- Feature packages (`ui/export`, `ui/sequence`, `ui/compare_board`, `ui/playblast`, `ui/settings`) register
  their own strings/icons/shortcuts/help pages at import (`i18n.register`, `icons.register`,
  `shortcuts.register`, `help.content.register_page`); `main_window.py` imports them before building actions.
- Panels talk through `ui/context.py` (`AppContext`): read `ctx.project`, change it only by pushing undo
  commands (`ctx.push`), refresh on `edited` / `projectChanged`. Windows that delete themselves on close
  (`WA_DeleteOnClose`) must be checked with `shiboken6.isValid` before touching them again.
- Any decoder change must keep `tests/test_decoder.py` passing (barcode test videos).
