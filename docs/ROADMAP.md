# ClipToolbox Roadmap (living document)

Single source of truth for planned UX/feature work. Seeded from the 2026-07-12 usability audit
([USABILITY_REPORT.md](USABILITY_REPORT.md) — immutable snapshot; finding numbers below refer to it).

**Protocol** (enforced by CLAUDE.md): every session that does feature/UX work reads this file first,
sets items `in-progress`/`done` as it goes, appends a Session log entry, and commits roadmap updates
in the same commit as the work. Newly discovered work gets a new row, not silent scope creep.

**Now / Next:** T1 + the Q1–Q4 batch are done. Suggested next: B3 (command palette), then decide
B1 vs. staying incremental. Q5–Q8 remain as small fillers.

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
| Q5 | UNDO-toast for trim CLEAR / CLEAR RECENTS (grab_set caveat: flip button label in-place inside Settings) | F8 | todo |
| Q6 | Reset leaked trim state on clip load | F10 | todo |
| Q7 | Supersede stale success toasts when a new export starts | F11 | todo |
| Q8 | Roster RESET leaves stale per-track % labels (`HaloSlider.set()` doesn't fire its command; discovered 2026-07-15) | — | todo |

## Incremental track — medium (M)

| ID | Item | Fixes | Status |
|----|------|-------|--------|
| M1 | Determinate export progress strip via new `on_progress(percent, attempt, attempts_max)` callback; honest per-attempt display; no ETA | F5 | todo |
| M2 | F1/? shortcut cheat-sheet overlay + legend hint (obsolete if B3 lands) | F7 | todo |
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
| B2 | One adaptive screen (landing becomes the workspace empty state; command strip shows filename) | F4 F12, Q1 M3 | todo |
| B3 | Command palette Ctrl+K (every action + hidden gestures, searchable, key hints) | F7, M2 | todo |
| B4 | Export drawer + persistent job history (name patterns, per-job progress/attempts, OPEN/RE-RUN) | F5 F11, Q7 M1 | todo |
| B5 | Focus/HUD mode (Tab collapses panels, translucent scanline controls per skin) | — | todo |
| B6 | First-run coach marks overlay | cold-start half of F7 | todo |

Bold sequencing if chosen: B3 → B0 → B1 → B4 → B2 → B5/B6.
XL items get a stage checklist added under their row when work starts (plan-mode design first).

## Session log (newest first)

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
