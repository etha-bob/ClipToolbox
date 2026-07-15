# ClipToolbox Roadmap (living document)

Single source of truth for planned UX/feature work. Seeded from the 2026-07-12 usability audit
([USABILITY_REPORT.md](USABILITY_REPORT.md) — immutable snapshot; finding numbers below refer to it).

**Protocol** (enforced by CLAUDE.md): every session that does feature/UX work reads this file first,
sets items `in-progress`/`done` as it goes, appends a Session log entry, and commits roadmap updates
in the same commit as the work. Newly discovered work gets a new row, not silent scope creep.

**Now / Next:** T1, the full Q1–Q8 quick-win batch, and B3 (command palette) are done. Ethan
reprioritized **B2 (one adaptive screen) next**, ahead of the suggested B0 — in progress on
`feature/adaptive-single-screen` (B2 has no B0 dependency; its grid reuses the existing off-thread
thumbnail path). After B2: B0 → B1 → B4 per the bold sequencing.

Statuses: `todo` · `in-progress` · `done <date, commit>` · `dropped <reason>`

## Shipped

| ID | Item | Status |
|----|------|--------|
| T1 | Taskbar flash when exports finish unfocused (+ Settings toggle, IsIconic guard) | done 2026-07-12 |

## Incremental track — quick wins (S)

| ID | Item | Fixes | Status |
|----|------|-------|--------|
| Q1 | Filename in window title; reset on menu; render orphaned `file_label_var` | F4 | done 2026-07-15 |
| Q2 | One accurate error for unreadable files, return to landing (no dialog cascade) | F3 | done 2026-07-15 |
| Q3 | Settings: Esc cancels, DONE saves (split `close()`) | F9 | done 2026-07-15 |
| Q4 | Session-restore toast with RESET action; don't count inert crop keyframes; session dot on recent rows | F6, F14 | done 2026-07-15 |
| Q5 | UNDO-toast for trim CLEAR / CLEAR RECENTS (grab_set caveat: flip button label in-place inside Settings) | F8 | done 2026-07-15 |
| Q6 | Reset leaked trim state on clip load | F10 | done 2026-07-15 |
| Q7 | Supersede stale success toasts when a new export starts | F11 | done 2026-07-15 |
| Q8 | Roster RESET leaves stale per-track % labels (`HaloSlider.set()` doesn't fire its command; discovered 2026-07-15) | — | done 2026-07-15 |

## Incremental track — medium (M)

| ID | Item | Fixes | Status |
|----|------|-------|--------|
| M1 | Determinate export progress strip via new `on_progress(percent, attempt, attempts_max)` callback; honest per-attempt display; no ETA | F5 | todo |
| M2 | F1/? shortcut cheat-sheet overlay + legend hint (obsolete if B3 lands) | F7 | dropped (absorbed by B3 2026-07-15) |
| M3 | Landing menu keyboard navigation (obsolete if B2 lands) | F12 | todo |
| M4 | Animated "starting preview" cue | F13 | todo |

## Incremental track — large (L)

| ID | Item | Fixes | Status |
|----|------|-------|--------|
| L1 | Silent-video support: audio-optional probe/preview/export (`-an` path, skip amix) | F2 | todo |
| L2 | ITaskbarList3 taskbar progress (COM spec in report §roadmap-13; only after M1) | F5 | todo |
| L3 | Single-level undo for edit state (supersedes Q5 if done) | F8 | todo |

## Bold track — surface rebuilds (choose per surface: patch OR rebuild, never both)

| ID | Item | Absorbs | Status |
|----|------|---------|--------|
| B0 | Background render queue utility (thumbnails/waveforms off the Tk thread via `ui()` marshaling) — prerequisite for B1/B4 | — | todo |
| B1 | Real timeline: filmstrip lane, per-track waveforms, fat trim regions, always-visible keyframe lane, progress painted on the strip | F5 F6 F13, M1 M4, most of F7 | todo |
| B2 | One adaptive screen (landing becomes the workspace empty state; command strip shows filename) | F4 F12, Q1 M3 | in-progress |
| B3 | Command palette Ctrl+K (every action + hidden gestures, searchable, key hints) | F7, M2 | done 2026-07-15 |
| B4 | Export drawer + persistent job history (name patterns, per-job progress/attempts, OPEN/RE-RUN) | F5 F11, Q7 M1 | todo |
| B5 | Focus/HUD mode (Tab collapses panels, translucent scanline controls per skin) | — | todo |
| B6 | First-run coach marks overlay | cold-start half of F7 | todo |

**B2 stage checklist** (design agreed 2026-07-15 in plan mode; decisions: full-body hero empty
state, Ctrl+W + ✕ chip closes the clip (Esc never unloads), strip = LOAD·EXPORT·CANCEL |
filename+✕ | status·SETTINGS with QUIT dropped, recents grid gets arrows/Enter/Delete):

- [x] S1 Groundwork: dedupe duplicated `main()`; probe-generation token (`_load_token`/`_probe_done`)
      guarding `after_probe`/`after_probe_failed`/auto-preview timer (fixes latent leave-within-300ms race)
- [x] S2 `ui/views/empty_state.py`: self-contained `RecentsGrid` (thumb cards, session dots,
      right-click menu, selection ring) + full-body hero (wordmark, drop-zone, relocated build line) + gallery card
- [x] S3 The flip: `show_empty_state`/`show_editor`, `close_clip()`/`reset_clip_state()` with probe
      gates, `active_screen` removed everywhere, palette `file.close` (Ctrl+W), landing.py deleted
- [ ] S4 Command strip in shell row 0; workspace actions row removed; EXPORT disabled w/o clip;
      ✕ chip + SETTINGS join `set_busy` lockdown
- [ ] S5 Grid keyboard nav (arrows/Enter/Delete) + legend states + roadmap close-out (M3 dropped)

Bold sequencing if chosen: B3 → B0 → B1 → B4 → B2 → B5/B6 (B2 pulled forward 2026-07-15 by Ethan).
XL items get a stage checklist added under their row when work starts (plan-mode design first).

## Session log (newest first)

- **2026-07-15** — Shipped B3 (command palette) on `feature/command-palette` (stacked on the
  unmerged `feature/q-batch-quick-wins` so the roadmap stays coherent; rebases onto main once the
  Q-batch merges). New `ui/commands.py` is a single registry of ~28 actions — each with a key hint,
  an `enabled()` predicate mirroring the `shortcut()` guards, and search keywords — plus a
  subsequence fuzzy `score()`. New `ui/views/palette.py` (`CommandPalette`) reuses the
  SettingsOverlay pattern (dim scrim + grabbed card Toplevel, `<Configure>` reposition): a HaloEntry
  search box over a scrolled results list; runnable commands render bright and are keyboard-navigable
  (Up/Down wrap across enabled rows only, Enter runs, Esc/Ctrl+K close), unavailable ones render
  greyed **but keep their shortcut visible** so the palette doubles as the cheat-sheet — this is why
  M2 is dropped and F7 is covered. Wired Ctrl+K in `app.py` (toggle, guarded against export/modals/
  typing; works on landing *and* workspace) and added a `CTRL+K COMMANDS` legend hint to both
  screens (dropped the redundant `CTRL+E EXPORT` legend chip since the palette surfaces export).
  Verified: widget gallery both skins + a 17-assertion in-process driver (real ffprobe on a synthetic
  clip) exercising landing/workspace open, greyed-vs-enabled rows, `exp` fuzzy filter ranking Export
  first, arrow nav skipping greyed rows, and Enter-runs-then-teardown — screenshotted in halo2 and
  reach. Lesson: `_scroll_into_view` fired during `__init__` before the canvas was mapped, so
  `winfo_height()==1` scrolled the selected top row out of view — guard with the configured height and
  a "fits, stay at top" early-out. No new deps.
- **2026-07-15** — Shipped the rest of the Q-batch (Q5–Q8) on `feature/q-batch-quick-wins`:
  trim CLEAR now posts an UNDO toast that restores the IN/OUT points, and CLEAR RECENT CLIPS
  (unreachable by a toast button behind the Settings grab) flips to "UNDO CLEAR" in place (Q5);
  loading a clip drops the trim toggle + full-range values before the probe so nothing leaks
  into the next clip or lingers after a failed load (Q6); a new export dismisses any stale
  "Export complete" toast via a new `tag`/`dialogs.dismiss_tagged` mechanism (Q7); roster RESET
  now refreshes the per-track "NN%" labels itself, since `HaloSlider.set()` is deliberately
  silent — added `app.track_volume_labels` keyed by row, cleared alongside `track_state_strips`
  (Q8). Verified: widget gallery both skins + a 20-assertion in-process driver (real ffprobe,
  real 2-track/1-track synthetic clips, real toasts, real SettingsOverlay). No new deps.
- **2026-07-15** — Shipped the Q-batch (Q1–Q4) on `feature/q-batch-quick-wins`: filename in
  title + status-strip middle column; corrupt files now show one accurate error and return to
  the menu; Settings Esc cancels / DONE saves; session restores announce via toast with a
  RESET action (inert crop keyframes no longer counted) and recent rows carry a session dot.
  Verified with the widget gallery (both skins) plus a 36-assertion in-process driver (real
  mpv engine, real corrupt-file probe). Lessons: screen-grab screenshots need ~300 ms of
  settle or they catch DWM tearing (offset "ghost" panels); `CLIPTOOLBOX_SKIN` env var forces
  a skin for app-level checks. Discovered Q8 (roster RESET leaves stale % labels). Ethan's
  local `.gitignore` edit (ignore `sessions.json`) intentionally left uncommitted.
- **2026-07-12** — Usability audit (3 scripted in-app runs, 14 findings) → USABILITY_REPORT.md.
  Shipped T1 (4 files, ~110 lines); verification caught the minimized-window foreground quirk
  (IsIconic guard). Roadmap created; Ethan directed emphasis toward the bold track.
