# ClipToolbox Roadmap (living document)

Single source of truth for planned UX/feature work. Seeded from the 2026-07-12 usability audit
([USABILITY_REPORT.md](USABILITY_REPORT.md) — immutable snapshot; finding numbers below refer to it).

**Protocol** (enforced by CLAUDE.md): every session that does feature/UX work reads this file first,
sets items `in-progress`/`done` as it goes, appends a Session log entry, and commits roadmap updates
in the same commit as the work. Newly discovered work gets a new row, not silent scope creep.

**Now / Next:** T1, the Q1–Q9 batch, B3, B2, B0, B1, and B4 (export drawer + job history —
absorbing Q7/M1's surfaces and defusing most of M5) are done. The bold track's remainder is
B5 (focus/HUD mode) then B6 (coach marks). L1 (silent-video support) is the highest-value
incremental alternative; L2 (taskbar progress) is now easy on top of the job pipeline.

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
| M1 | Determinate export progress strip via new `on_progress(percent, attempt, attempts_max)` callback; honest per-attempt display; no ETA | F5 | done 2026-07-15 (absorbed by B1 S6) |
| M2 | F1/? shortcut cheat-sheet overlay + legend hint (obsolete if B3 lands) | F7 | dropped (absorbed by B3 2026-07-15) |
| M3 | Landing menu keyboard navigation (obsolete if B2 lands) | F12 | dropped (absorbed by B2 2026-07-15: the recents grid is arrow/Enter/Delete-navigable) |
| M4 | Animated "starting preview" cue | F13 | done 2026-07-15 (absorbed by B1 S7) |
| M5 | Left column can't shrink: below ~884px window height w/ trim+crop toolbars open the compression card clips bottom-first (pre-B1 legacy, measured 2026-07-15; export stays visible since it packs first). Fix = collapsible sections or responsive preview height. 2026-07-16: B4 moved the compression/watermark cards into the drawer — toolbars-open requirement re-measured at ~734 logical px (was ~796), so every window ≥734 now fits; only the 700 minsize floor still clips ~34px. Downgraded to minor | — | todo |

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
| B1 | Real timeline: filmstrip lane, per-track waveforms, fat trim regions, always-visible keyframe lane, progress painted on the strip | F5 F6 F13, M1 M4, most of F7 | done 2026-07-15 |
| B2 | One adaptive screen (landing becomes the workspace empty state; command strip shows filename) | F4 F12, Q1 M3 | done 2026-07-15 |
| B3 | Command palette Ctrl+K (every action + hidden gestures, searchable, key hints) | F7, M2 | done 2026-07-15 |
| B4 | Export drawer + persistent job history (name patterns, per-job progress/attempts, OPEN/RE-RUN) | F5 F11, Q7 M1 | done 2026-07-16 |
| B5 | Focus/HUD mode (Tab collapses panels, translucent scanline controls per skin) | — | in-progress |
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

**B5 stage checklist** (designed 2026-07-16, autonomous session per Ethan's standing direction;
decisions: Tab toggles focus with a clip loaded (not typing, no modal; allowed during export so
you can watch the strip render full-size and still Tab back out); focus hides the command strip,
right column (roster+log), transport/frame/export rows and grows the preview bezel to fill the
workspace — the timeline strip stays beneath it as the one control surface, so trim brackets,
keyframes, zoom and the export sweep all keep working; Esc also exits (after its cancel-export /
leave-entry / close-drawer priorities); legend stays and swaps to focus hints; HUD chips overlay
the preview letterbox (clip name top-left, playback glyph + timecode bottom-right) rendered by a
new `skin.render_hud_chip` scanline panel pre-blended toward black — faked translucency, honest
over the black letterbox, per-skin via existing tokens only (no new tokens); live text via var
traces updating native canvas items (no PIL at 10 Hz); crop-edit and focus are mutually
exclusive (entering focus with CROP on is refused with a status hint; C inside focus exits focus
first, then toggles crop); drawer stays orthogonal (Ctrl+E slides it over focus); close_clip /
failed probe exit focus via reset_clip_state; focus survives clip swaps; transient — never
persisted):

- [x] S1 Layout flip: view refs (workspace grid/left/right, bezel, command strip), enter/exit/
      toggle in app.py, Tab/Esc wiring + guards (typing, modal, crop refusal), focus legend
      hints, reset_clip_state exits, paused-still refresh at the new size; in-process driver
      (37 checks × both skins incl. pack-order restore, C-in-focus handoff, clip-swap survival)
- [x] S2 HUD: `skin.render_hud_chip` + `ui/views/hud.py` (name chip, transport glyph+timecode
      chip on var traces), wired to enter/exit + playback-state refresh, gallery demo both skins
      (16 checks × both skins incl. a pixel probe proving the chips out-stack the live player
      window — `anchor_child_window` re-raises it to HWND_TOP on every first-frame reveal, so
      the HUD re-asserts via new `win32.raise_window_to_top` on playback-state transitions)
- [ ] S3 Palette `view.focus`, acceptance driver (export-in-focus, drawer-over-focus, Ctrl+W,
      clip swap, Tab-in-entry traversal) both skins, roadmap close-out

**B4 stage checklist** (designed 2026-07-16, autonomous session per Ethan's standing direction;
decisions: right-side slide-in drawer over the editor in `screen_container` (~440px, non-modal),
toggled by EXPORT CLIP / Ctrl+E, Esc closes; the compression + watermark cards MOVE into the
drawer (same attribute names — `set_busy`/session code untouched; also relieves M5's left-column
budget); destination + name-pattern entry (`{clip} {trim} {crop} {stamp} {size} {res} {date}
{time}` tokens, collisions get `_2…`) with live resolved-name preview, new settings keys
`export_name_pattern`/`export_destination`; GO exports straight to the destination, SAVE AS…
keeps the old dialog with the pattern name prefilled; job history = `core/jobs.py`
(`ExportJobSpec` snapshots the exact `run_export_job` args so RE-RUN replays verbatim even
across restarts; `jobs.json` atomic-write persistence, cap 20); job rows carry per-attempt
progress + ATTEMPT n/m, final size, OPEN/FOLDER/RE-RUN (CANCEL while running); the drawer opens
clip-less too (history + RE-RUN without a loaded clip); completion toast's action becomes
SHOW JOBS pointing into the list (Q7 tag kept); still one export at a time; no new skin tokens):

- [x] S1 `core/jobs.py`: name-pattern resolver + unique-path, `ExportJobSpec`/`ExportJob`/
      `JobHistory` with `jobs.json` persistence; pure-Python test driver
- [x] S2 `ui/views/drawer.py`: slide-in shell, destination + pattern + live name preview,
      compression/watermark cards moved in, GO + SAVE AS row; EXPORT button/Ctrl+E/Esc wiring,
      `set_busy` lockdown, settings keys
- [x] S3 Job list: rows (status rail, progress, attempts, size, actions), export pipeline wired
      to job records via the existing callbacks, history persisted, toast → SHOW JOBS pointer
- [x] S4 RE-RUN + clip-less drawer + palette commands + gallery job-row demo (RE-RUN itself
      landed a stage early, in S3, since the row buttons wanted real handlers)
- [x] S5 Acceptance: S2+S3 drivers re-run on the final code (both green), M5 re-measured
      (~796→~734), roadmap close-out

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
- [x] S2 Trim as first-class region: `render_trim_handle` (grip-notch bars outside the kept
      region), exclusion-zone dimming in the display tier, hover/drag states, px(12) hit margin
- [x] S3 Filmstrip lane: `core/strips.py`, `build_timeline_assets` in `after_probe`, slot compose,
      cache + `cancel_group("timeline")` (driver: 40/6-tile clips, cache-hit mtime, mid-decode close)
- [x] S4 Waveform lanes: per-stream `showwavespic` (white-on-transparent, PIL-tinted via `WAVE`
      token), mix-state dim/solo mirroring the roster, 0/1/2/3/4+ band division + "+N" tag
- [x] S5 Keyframe lane: inert (ghosted) diamond state, always-visible when keyframes exist,
      right-click delete; inert edits skip the pipeline; only-inert restores stay silent (Q4)
- [x] S6 Export progress: `on_progress(percent, attempt, attempts_max)` + sweep over the trimmed
      region + attempt counter + seekbar disabled during export (M1/F5; real 2-attempt NVENC run)
- [x] S7 STARTING cue (M4/F13): ping-pong scanner in the ruler band around the playhead,
      tracked off `on_playback_state`, leak-free `after` loop (verified via `after info`)
- [x] S8 Cleanup + close-out: `trim_flag` renderer + `TRIM_KEEP` token deleted (consumer-free),
      gallery timeline demos fed synthetic PIL strips/waves (no ffmpeg), acceptance pass both skins

**B0 stage checklist** (done 2026-07-15):

- [x] S1 `core/render_queue.py`: `RenderQueue` + `CancelToken` (bounded daemon pool,
      PriorityQueue, dedup/coalesce by key, `cancel_group`, `shutdown`). Pure Python — no Tk.
- [x] S2 Migrated `get_recent_thumbnail` onto the queue; constructed `render_queue` in
      `__init__`, `shutdown()` in `on_close`, cancel `"thumbnails"` on clip load (`show_editor`).
- [x] S3 Verified (pure-Python queue test, app-flow driver both skins, gallery both skins) + close-out.

Bold sequencing if chosen: B3 → B0 → B1 → B4 → B2 → B5/B6 (B2 pulled forward 2026-07-15 by Ethan).
XL items get a stage checklist added under their row when work starts (plan-mode design first).

## Session log (newest first)

- **2026-07-16** — Shipped B4 (export drawer + job history) on `feature/export-drawer`
  (stacked on `feature/real-timeline`), 5 stage commits, autonomous session. The save-dialog
  export flow is replaced by a right-side slide-in drawer (~440px, non-modal, over
  `screen_container`): destination folder (BROWSE + ↺ back-to-outputs), a name-pattern entry
  with live resolved-name preview (`{clip} {trim} {crop} {stamp} {size} {res} {date} {time}`;
  conditional tokens emit their legacy suffix so the default pattern reproduces the old
  save-dialog name byte-for-byte; unknown tokens stay literal; collisions get `_2…`), the
  compression + watermark cards moved in from the left column (attribute names unchanged, so
  `set_busy`/settings persistence never noticed), START EXPORT (straight to the destination,
  no dialog) + SAVE AS… (classic dialog, pattern-prefilled), and a JOB HISTORY list. New
  `core/jobs.py`: `ExportJobSpec` snapshots the exact `run_export_job` arguments, so RE-RUN
  replays a row verbatim (same output path, ffmpeg -y) — even with no clip loaded, even in a
  later session; `jobs.json` persists the newest 20 (atomic writes; a job stored as `running`
  loads as interrupted-cancelled). Rows carry a status rail, honest per-attempt progress +
  ATTEMPT n/m (fed by the existing on_progress pipe), final size, OPEN/FOLDER/RE-RUN, CANCEL
  while running. Completion toasts now say SHOW JOBS and point into the list (Q7's supersede
  tag kept); Ctrl+E opens the drawer clip-less and mid-export (to get back to the progress
  row); the palette gained `export.jobs`; the empty-state legend advertises CTRL+E JOBS once
  history exists. `export_video_dialog` was split into `build_export_spec` (validations +
  snapshot) → `export_go`/`export_save_as` → `start_export(spec)` — start_export derives its
  status/log lines from the spec alone so reruns share the same door (the watermark-duration
  log line moved to the toggle only). Settings grew `export_name_pattern`/`export_destination`;
  `jobs.json` joined .gitignore. Layout bonus: the card move dropped the editor's toolbars-open
  height requirement ~796→~734 logical px (M5 re-measured and downgraded). Verified: 24-check
  pure-Python jobs test; three in-process drivers × both skins (S2: 24 checks incl. real
  trimmed stream-copy GO exports and `_2` collision handling; S3: 30 checks incl. a real NVENC
  compressed run, a mid-render cancel leaving an honest CANCELLED row, RE-RUN overwriting its
  output, and a restart round-trip; S4: 16 checks incl. clip-less RE-RUN end-to-end); gallery
  both skins with new synthetic job-row demos. Lessons: (1) app drivers must DELETE
  config/sessions/jobs after backing them up — restore-on-exit alone leaks the user's real
  settings into the assertions; (2) stream-copy exports finish in <150 ms, so "running-state"
  assertions need an NVENC compressed run to observe; (3) Windows cp1252 consoles choke on
  characters like "→" in driver output — `sys.stdout.reconfigure(encoding="utf-8")` first.

- **2026-07-15** — Shipped B1 (real timeline) on `feature/real-timeline`, 8 stage commits. The
  40px seekbar grew in place into a 104px multi-lane strip (minimap / ruler / filmstrip / audio
  band / keyframe lane), keeping the DoubleVar position contract, zoom math, and all bind_* call
  sites untouched. Rendering split into three tiers so the 10 Hz position path does no PIL work:
  a cached composed base (lane wells, slotted filmstrip tiles, tinted waveforms, frame grid), a
  cached display PhotoImage (base + trim-exclusion dimming), and cheap native items on top
  (playhead, fat trim handles, diamonds, export sweep, STARTING scanner). New `core/strips.py`
  extracts assets via the B0 render queue (group "timeline"): one `fps=`+`tile` ffmpeg pass →
  ≤40 filmstrip tiles (slot-filled, never stretched — zoom re-slots), one `showwavespic` pass
  per stream (white-on-transparent, PIL-tinted per mix state via the new `WAVE` token; solo →
  accent, silenced → dim). Trim is a first-class region (grip-notch handles outside the kept
  span, exclusions darkened). Keyframes render whenever they exist — ghosted "inert" when crop
  is off (structural F6 fix) with right-click delete. Export progress paints on the strip:
  `on_progress(percent, attempt, attempts_max)` threaded through the existing `-progress` pipe
  parser, fill sweeping exactly the trimmed region, honest per-attempt resets, ATTEMPT n/8
  counter (M1/F5); the seekbar is now DISABLED during export (pre-existing gap). Engine STARTING
  shows a ping-pong scanner around the playhead (M4/F13). Old `trim_flag` renderer and
  `TRIM_KEEP` token deleted; gallery timelines feed on synthetic PIL strips (no ffmpeg).
  Verified: five in-process drivers (layout budget incl. pre-B1 stash baseline, filmstrip
  cache/cancel, waveforms + mix tints, keyframe session round-trip, real NVENC exports w/
  2-attempt compression + cancel, STARTING timer-leak assert via `after info`) + gallery both
  skins. Layout discoveries: the left column NEVER fit the stock 780px window with both toolbars
  open (pre-B1, measured via stash) and the export button silently lost the pack fight —
  `export_row` now packs first (middle content clips instead) and the stock window is 1150x900;
  logged M5 for the structural fix. Lessons: (1) skin tokens live in three places — both skins
  AND theme.py's re-export list; the gallery doesn't catch a missing re-export if no demo hits
  that code path. (2) lavfi `sine` generates at 1/8 amplitude — waveform test clips need
  `volume=8` or the honest linear display looks broken when it isn't.

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
