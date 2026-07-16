# ClipToolbox Roadmap (living document)

Single source of truth for planned UX/feature work. Seeded from the 2026-07-12 usability audit
([USABILITY_REPORT.md](USABILITY_REPORT.md) — immutable snapshot; finding numbers below refer to it).

**Protocol** (enforced by CLAUDE.md): every session that does feature/UX work reads this file first,
sets items `in-progress`/`done` as it goes, appends a Session log entry, and commits roadmap updates
in the same commit as the work. Newly discovered work gets a new row, not silent scope creep.

**Now / Next:** T1, the Q1–Q9 batch, B3 (command palette), B2 (one adaptive screen — pulled
forward by Ethan ahead of B0), and B0 (background render queue) are done. B1 (real timeline) and
B4 (export drawer) are now unblocked; suggested next is B1 per the bold sequencing. M1 (export
progress) remains the highest-value standalone alternative.

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
| Q9 | Timestamp watermark: burn the filename's recording time bottom-left with fade-out (ported from an older fork; discovered 2026-07-15) | — | done 2026-07-15 |

## Incremental track — medium (M)

| ID | Item | Fixes | Status |
|----|------|-------|--------|
| M1 | Determinate export progress strip via new `on_progress(percent, attempt, attempts_max)` callback; honest per-attempt display; no ETA | F5 | todo |
| M2 | F1/? shortcut cheat-sheet overlay + legend hint (obsolete if B3 lands) | F7 | dropped (absorbed by B3 2026-07-15) |
| M3 | Landing menu keyboard navigation (obsolete if B2 lands) | F12 | dropped (absorbed by B2 2026-07-15: the recents grid is arrow/Enter/Delete-navigable) |
| M4 | Animated "starting preview" cue | F13 | todo |
| M5 | Left column can't shrink: below ~884px window height w/ trim+crop toolbars open the compression card clips bottom-first (pre-B1 legacy, measured 2026-07-15; export stays visible since it packs first). Fix = collapsible sections or responsive preview height | — | todo |

## Incremental track — large (L)

| ID | Item | Fixes | Status |
|----|------|-------|--------|
| L1 | Silent-video support: audio-optional probe/preview/export (`-an` path, skip amix) | F2 | todo |
| L2 | ITaskbarList3 taskbar progress (COM spec in report §roadmap-13; only after M1) | F5 | todo |
| L3 | Single-level undo for edit state (supersedes Q5 if done) | F8 | todo |

## Bold track — surface rebuilds (choose per surface: patch OR rebuild, never both)

| ID | Item | Absorbs | Status |
|----|------|---------|--------|
| B0 | Background render queue utility (thumbnails/waveforms off the Tk thread via `ui()` marshaling) — prerequisite for B1/B4 | — | done 2026-07-15 |
| B1 | Real timeline: filmstrip lane, per-track waveforms, fat trim regions, always-visible keyframe lane, progress painted on the strip | F5 F6 F13, M1 M4, most of F7 | in-progress |
| B2 | One adaptive screen (landing becomes the workspace empty state; command strip shows filename) | F4 F12, Q1 M3 | done 2026-07-15 |
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
- [x] S4 Command strip in shell row 0; workspace actions row removed; EXPORT disabled w/o clip;
      ✕ chip + SETTINGS join `set_busy` lockdown
- [x] S5 Grid keyboard nav (arrows/Enter/Delete) + legend states + roadmap close-out (M3 dropped)

**B1 stage checklist** (design agreed 2026-07-15 in plan mode; decisions: grow `HaloSeekbar`
in place keeping the DoubleVar/zoom/bind contracts; 3-tier redraw split so the 10 Hz path does
no PIL; lane stack minimap 2 / ruler 14 / filmstrip 44 / audio 32 / keyframes 12 = SEEKBAR_H 104;
slot-based filmstrip from one `fps=`+`tile` ffmpeg pass (~40 tiles, never stretched); per-stream
`showwavespic` white-on-transparent tinted per mix state via new `WAVE` token; export sweep over
the trimmed region w/ honest per-attempt reset + `on_progress(percent, attempt, attempts_max)`;
STARTING scanner cue in the ruler band; branch `feature/real-timeline`, one commit per stage):

- [x] S1 Lane scaffold: 3-tier redraw split, lane geometry, SEEKBAR_H 104 + `WAVE` both skins,
      preview-scale/pady vertical budget, gallery layout rework, measurement driver. Budget
      reality (measured, incl. pre-B1 stash baseline): the left column never fit 780 with
      toolbars open — export_row is now packed FIRST (bottom-pinned wins clipping fights) and
      the stock window is 1150x900 (plain stack req 764, toolbars-open 796, avail at 900 = 812)
- [ ] S2 Trim as first-class region: `render_trim_handle`, exclusion-zone dimming, fat hit targets
- [ ] S3 Filmstrip lane: `core/strips.py`, `build_timeline_assets` in `after_probe`, slot compose,
      cache + `cancel_group("timeline")`
- [ ] S4 Waveform lanes: per-stream extraction, mix-state tinting, 0/1/2/3/4+ band division
- [ ] S5 Keyframe lane: inert state, always-visible, right-click delete (structural F6 fix)
- [ ] S6 Export progress: `on_progress` protocol + sweep + attempt counter + seekbar-disable gap (M1/F5)
- [ ] S7 STARTING cue (M4/F13)
- [ ] S8 Cleanup + close-out: delete `trim_flag`, gallery timeline demos, roadmap done + log

**B0 stage checklist** (done 2026-07-15):

- [x] S1 `core/render_queue.py`: `RenderQueue` + `CancelToken` (bounded daemon pool,
      PriorityQueue, dedup/coalesce by key, `cancel_group`, `shutdown`). Pure Python — no Tk.
- [x] S2 Migrated `get_recent_thumbnail` onto the queue; constructed `render_queue` in
      `__init__`, `shutdown()` in `on_close`, cancel `"thumbnails"` on clip load (`show_editor`).
- [x] S3 Verified (pure-Python queue test, app-flow driver both skins, gallery both skins) + close-out.

Bold sequencing if chosen: B3 → B0 → B1 → B4 → B2 → B5/B6 (B2 pulled forward 2026-07-15 by Ethan).
XL items get a stage checklist added under their row when work starts (plan-mode design first).

## Session log (newest first)

- **2026-07-15** — B0: added `cliptoolbox/core/render_queue.py`, a pure-Python `RenderQueue`
  (bounded daemon-worker pool draining a `PriorityQueue`) + `CancelToken`. Results marshal to the
  Tk thread via a caller-supplied `marshal` (`HaloApp.ui`), so the module never touches Tk and
  workers only ever produce plain data — the thumbnail's `ImageTk.PhotoImage` is still built on the
  Tk thread inside `on_done`, unchanged. `submit(key, work, on_done, *, group, priority, on_error)`
  dedups/coalesces identical in-flight work by `key`, `cancel_group()` drops pending jobs and kills
  running subprocesses (via the token's attached `Popen`), `shutdown()` cancels all and sentinels
  the workers out. Migrated `get_recent_thumbnail` off its raw per-call `threading.Thread` onto the
  queue (group `"thumbnails"`, keyed on the cache path); `show_editor` cancels that group since the
  recents grid is gone once a clip loads; `on_close` shuts the queue down. No user-visible change —
  this is the B1/B4 prerequisite. Verified: a 10-assertion pure-Python queue test (bounded
  concurrency ≤ workers, dedup runs work once + fans out to all waiters, priority ordering,
  `cancel_group` drops-pending + terminates a running fake process, clean shutdown with no
  post-shutdown callbacks); an in-process `HaloApp` driver on both skins (4 synthetic clips seeded
  into recents → all thumbnails render through the queue, screenshot-confirmed; loading a clip
  cancels `"thumbnails"` without error and workers survive); gallery both skins. Snapshotted/restored
  `config.json` + `sessions.json` around the run. No new deps. Lesson: closed a dedup/retire race by
  snapshotting a job's coalesced callbacks under the lock at retire time — a same-key `submit` that
  lands after `work()` finishes either lands before the registry pop (its callback is in the
  snapshot) or after it (it sees no live job and enqueues fresh), never dropped.
- **2026-07-15** — Q9: ported the timestamp watermark from an older `app.py` fork. Recording time
  is pulled from the source filename (six date/time parts, e.g. `2025 04 06 02 06 50`) and burned
  bottom-left via `drawtext`, ramping in then fading out after a chosen visible duration (default
  3000 ms, 500 ms fade). Kept the fork's filter math verbatim in
  `core/filters.py` (`extract_recording_timestamp`, `build_timestamp_watermark_filter`); wired it
  through the existing crop `video_filter`/`video_prefilter` plumbing rather than adding an export
  arg — watermark-alone forces the standard path's NVENC re-encode, and riding the compressed
  path's prefilter (before scale) keeps drawtext's `h`-relative sizing proportional post-downscale.
  New Compression-card row (checkbox + fade-ms entry), locked during export. Verified: real
  bundled-ffmpeg render + frame grab (timestamp legible bottom-left), live `HaloApp` build
  exercising the enable/no-timestamp/bad-duration paths, gallery both skins. No new deps.
- **2026-07-15** — Shipped B2 (one adaptive screen) on `feature/adaptive-single-screen` (stacked
  on the unmerged `feature/command-palette`). The landing/workspace split is gone: the editor is
  the only screen and a new full-body hero (`ui/views/empty_state.py`) lifts over it when no clip
  is loaded — wordmark, drop-zone line (DnD promoted to the primary path; the latent
  `dnd_hint_var` finally renders on init failure), the relocated build line, and a `RecentsGrid`
  of up to 8 thumbnail cards (72px thumbs via the existing off-thread extractor, now
  height-parameterized; session dots; right-click Reveal/Remove; arrows/Enter/Delete navigation —
  which is what absorbs M3/F12). The shell status strip became the persistent command strip:
  LOAD · EXPORT (disabled w/o clip) · CANCEL | filename + ✕ chip | status · SETTINGS; QUIT
  collapsed into the titlebar/palette. `active_screen` is gone; guards key off
  `video_path`/`is_exporting`. New `close_clip()` (Ctrl+W / ✕ / palette `file.close`, replacing
  "Back to menu") persists the session, dismisses the restore toast (new tag), and resets through
  the same `reset_clip_state()` the failed-probe path uses; Esc no longer unloads anything.
  Verified: gallery both skins + three in-process drivers, 25 + 16×2 + 22×2 assertions (flip,
  close/persist, restore toast, Esc/Ctrl+W via `event_generate`, export lockdown, ellipsis,
  minsize layout, grid nav incl. missing-card Enter, Q5 CLEAR/UNDO repaint). Lessons: (1) a
  mid-probe close must NOT persist — capture would see load_video's cleared defaults and
  `sessions.save` prunes default states, deleting the stored entry; a `_load_token` +
  `_probe_done` gate covers it and also fixed a latent race where the auto-preview `after(300)`
  fired after leaving the screen. (2) Cold probes take ~1.8 s (4 ffprobe spawns) — drivers need
  ~3 s settle before asserting post-probe state. Fixed in passing: duplicated `main()` block at
  the bottom of app.py. `HaloMenuItem` is now app-unused (kept as a gallery/widgets catalog
  entry). No new deps.
  Post-review tweaks (Ethan): EXPORT CLIP moved off the command strip to a prominent primary
  button pinned at the bottom of the editor's left column (under the compression settings it
  depends on); LOAD CLIP is now editor-only too, so the empty state's strip is just filename +
  status + SETTINGS while the hero owns loading (drop / double-click / Ctrl+O / recents); added
  double-click-anywhere-on-the-hero to browse. Verified 16/16 both skins.
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
