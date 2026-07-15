# ClipToolbox — session guide

Windows-only Tkinter video clip editor (custom PIL-rendered "Halo" widgets, no ttk).
Run: `python ClipToolbox.py` · ffmpeg/ffplay bundled in `ffmpeg/bin`, optional mpv in `mpv/`.

## Living roadmap protocol (required)

`docs/ROADMAP.md` is the single source of truth for planned feature/UX work.

- **Session start:** before any feature/UX work, read `docs/ROADMAP.md`. If the user didn't name an
  item, propose the next `todo` respecting its Now/Next line.
- **Starting an item:** set its status to `in-progress`. For L/XL/B items, design first (plan mode),
  then record the agreed stages as a checklist under the item's row before implementing.
- **Finishing:** set `done <date>` (+ commit hash once known) and append a Session log entry (date,
  what shipped, anything learned worth keeping). Roadmap updates ship **in the same commit** as the
  work they describe.
- **Discovered work:** add a new row with a fresh ID instead of doing it silently; fixed-in-passing
  items still get a log mention. Reprioritizations the user states in chat get written into the file.
- `docs/USABILITY_REPORT.md` is an immutable audit snapshot — never rewrite it; add errata to the
  roadmap instead. Finding numbers (F1–F14) refer to it.
- Scope discipline: one roadmap item per branch/PR (a batch of Q-items counts as one).

## Verification expectations

- Widget/skin regressions: `python -m cliptoolbox.ui.gallery --skin halo2 --screenshot out.png`
  (and `--skin reach`) must render cleanly after UI changes.
- App-flow changes: drive the real app, don't just compile. Proven pattern: an in-process driver in
  the scratchpad that builds `HaloApp`, chains scenarios with `root.after`, monkeypatches
  `filedialog.asksaveasfilename`, and screenshots via `win32.capture_window_frame`
  (see USABILITY_REPORT.md appendix). Snapshot and restore `config.json` + `sessions.json` around
  any run — the app persists settings on close.
- Threading rule: worker threads never touch Tk — marshal through `app.ui(...)`.

## Conventions

- Zero new runtime dependencies without explicit approval; win32 work is raw ctypes in
  `cliptoolbox/core/win32.py` (c_void_p HWNDs, guarded helpers).
- All rendering goes through `skin.py`/`theme` tokens so both skins keep working; verify both.
- Commit style: `feat:`/`fix:`/`docs:` single-purpose commits.
