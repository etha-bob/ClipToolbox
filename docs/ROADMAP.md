# ClipToolbox Roadmap (living document)

Single source of truth for planned UX/feature work. Seeded from the 2026-07-12 usability audit
([USABILITY_REPORT.md](USABILITY_REPORT.md) — immutable snapshot; finding numbers below refer to it).

**Protocol** (enforced by CLAUDE.md): every session that does feature/UX work reads this file first,
sets items `in-progress`/`done` as it goes, appends a Session log entry, and commits roadmap updates
in the same commit as the work. Newly discovered work gets a new row, not silent scope creep.

**Now / Next:** The bold track (B0–B6) and the M6–M13 batch are done; L1 (silent-video) shipped
2026-07-16 and L2 (taskbar progress) shipped 2026-07-17. Remaining: **L3** (single-level undo for
trim/crop/mix — the last large item) is the next pick; the downgraded minor **M5** (700px-minsize
left-column clip) rounds out the list.

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
| M6 | Timeline: precise seeking around trim brackets — clicks near a bracket steal the seek and shift the trim (Ethan 2026-07-16). Fix: ruler band becomes a dedicated always-seek scrub lane (bracket/keyframe grabs live in the strip body), brackets grab with an offset + drag threshold instead of snapping to the cursor, and click-without-drag on a bracket seeks the playhead to that trim time | — | done 2026-07-16 |
| M7 | Timeline: zoomed-view navigation (Ethan 2026-07-16) — the 2px zoom indicator grows into a draggable navigator scrollbar (drag thumb pans the window, click jumps it), middle-mouse drag pans the strip 1:1, persistent filmstrip tile cache keeps pan recomposes cheap | — | done 2026-07-16 |
| M8 | Timeline: edge auto-scroll (Ethan 2026-07-16) — dragging the playhead/trim bracket/keyframe to the edge of a zoomed view pans the view so the drag continues past it (M7 follow-up) | — | done 2026-07-16 |
| M9 | Focus + crop compatibility (Ethan 2026-07-16) — Tab focus works with crop on: crop toolbar stays usable inside focus (preview/edit, add/delete, key nav, reset, clear) and the crop box drags in Edit mode; C inside focus toggles crop without leaving focus. Supersedes B5's mutual-exclusion decision | — | done 2026-07-16 |
| M10 | Preview mouse gestures (Ethan 2026-07-16) — hold left-click on the preview = play at 2x while held, double-click = toggle focus mode, right-click = play/pause | — | done 2026-07-16 |
| M11 | Watermark expansion (Ethan 2026-07-16) — Settings section for the timestamp watermark: text source (parsed filename timestamp / file creation date / full filename), date-only vs date+time, date format presets | — | done 2026-07-16 |
| M12 | Watermark: long date format + per-export text override (Ethan 2026-07-16, M11 follow-up) — a 4th date preset ("April 6th, 2025"); export drawer gains a per-clip CONFIGURED/CUSTOM/BOTH text mode with a freetext field (BOTH stacks configured on top, custom on bottom); mode/text reset on every clip load (clip-scoped, never persisted) | — | done 2026-07-16 |
| M13 | Two bug fixes (Ethan 2026-07-16): (a) the CUSTOM/BOTH freetext field never appeared — HaloSegmented stores its UPPERCASE label into `watermark_mode_var` but the logic compared lowercase; normalized via `watermark_text_mode()`. (b) crop-keyframe exports crashed with "Picture size 63113x34114 is invalid / Cannot allocate memory" — the animated-size scale (`out_w*iw/pw`) explodes on a heavily-zoomed crop; added `_clamp_export_zoom` (MAX_SCALE_DIM safety net) + built the compressed path's motion chain at the capped target resolution (`cap_size`) so a 16x zoom to a 1080p target keeps full zoom | — | done 2026-07-16 |

## Incremental track — large (L)

| ID | Item | Fixes | Status |
|----|------|-------|--------|
| L1 | Silent-video support: audio-optional probe/preview/export (`-an` path, skip amix) | F2 | done 2026-07-16 |
| L2 | ITaskbarList3 taskbar progress (COM spec in report §roadmap-13; only after M1) | F5 | done 2026-07-17 |
| L3 | Single-level undo for edit state (supersedes Q5 if done) | F8 | in-progress |

**L3 stage checklist** (design approved 2026-07-17 in plan mode; `feature/edit-undo`,
one commit per stage; decisions: single-level undo/redo *toggle* (Ctrl+Z swaps
current↔one slot, a new edit overwrites the slot); snapshot = `capture_video_session`
minus position — trim + crop keyframes + track enable/volume; mute/solo/playhead
excluded (transient); supersedes Q5's trim-clear toast, not the CLEAR RECENTS one;
`_undo_slot` cleared on clip change):

- [x] S1 Undo core (`_snapshot_edit`/`_restore_edit`/`push_undo`/`undo_edit`;
      `crop.apply_snapshot` that fully replaces incl. empty/disabled); `push_undo()`
      before each discrete mutator (trim set/clear, crop add/delete/clear/reset/
      retime/kf-delete, track-enable toggle via a checkbox ButtonPress bind,
      RESET-volumes); Ctrl+Z + Ctrl+Y/Ctrl+Shift+Z + palette `edit.undo`; replaced
      Q5's trim-clear toast with generic push+clear; `_undo_slot` cleared in both
      load_video and reset_clip_state. Verified: 17-check driver × both skins —
      discrete undo/redo round-trips (trim set, trim clear supersede-Q5, crop
      keyframe add, crop clear-all, track toggle), empty-slot no-op, clip-switch
      clears the slot; gallery both skins
- [ ] S2 Continuous-drag capture (trim bracket first-drag flag; volume slider
      ButtonPress + wheel first-notch); `_undo_slot` cleared on clip change; legend
      hint. Driver × both skins (drag undo restores pre-gesture state, clip-switch
      clears, mute/solo/position untouched) + gallery; roadmap close-out

**L1 stage checklist** (design approved 2026-07-16 in plan mode;
`feature/silent-video`, one commit per stage; decisions: "silent" strictly =
zero probed audio streams — an audio clip with all tracks deselected keeps the
existing "select at least one track" warning; preview builds a video-only
graph/pipe, export uses `-an`; the golden-checked command/mpv builders get their
`tools/dump_commands.py` sections regenerated):

- [x] S1 Core silent preview path: `after_probe` falls through to the editor for
      video-only clips (no dialog+return), `is_silent` state; `build_playback_filter`
      / `build_playback_stream_cmds` video-only when tracks empty; `PlaybackEngine`
      / mpv `play()` allow empty tracks; `start_preview` / `restart_playback_at`
      permit the empty path only when silent. Preview a real silent clip on ffplay + mpv
      (15-check driver × ffplay + mpv: pure video-only builders, silent preview/pause/
      resume/seek, normal-clip regression; playback golden output byte-identical)
- [x] S2 Silent export + crop: `build_export_spec` passes an empty filter_complex
      when silent; audio-optional standard + compressed command builders (`bool(filter_
      complex)` gates `-map [aout]`/`-c:a`, else `-an`) + `run_export_job` log; new
      SILENT golden sections in `dump_commands.py` (audio cases byte-identical); crop
      `enter_preview` allows silent. Verified: 9-check driver (real silent stream-copy +
      NVENC-compressed-with-crop exports both `done` w/ 0 audio streams, crop-preview on a
      silent clip) + audio-export regression (drive_fixes 11/11) green
- [x] S3 Roster "NO AUDIO — VIDEO ONLY" header + placeholder line, RESET disabled
      with no tracks (mute/solo/reset already guard on `track_controls`, confirmed
      inert); recents fire for silent clips; a normal clip reload restores the mix
      roster with no leftover placeholder. Verified: 8-check driver × both skins +
      silent-editor screenshot + gallery both skins

**L2 stage checklist** (design pre-specified in the usability report §roadmap-13;
`feature/taskbar-progress`; single-stage — no open design decisions: standard
single-pass export = determinate `TBPF_NORMAL` + `SetProgressValue(percent,100)`;
compression's multi-attempt tuner = `TBPF_INDETERMINATE` throughout; clear
`TBPF_NOPROGRESS` on finish/cancel/close; per-export COM lifecycle sidesteps
Explorer-restart pointer invalidation; all calls marshalled to the Tk/STA thread):

- [x] S1 `win32.TaskbarProgress` (hand-rolled ITaskbarList3 vtable ctypes:
      CoInitializeEx STA + CoCreateInstance + HrInit(3)/SetProgressValue(9)/
      SetProgressState(10)/Release(2); begin/value/clear/shutdown, fresh object per
      export, failure resets the pointer); wired into `start_export` (indeterminate
      when compressing else determinate 0%), `on_progress` (value only when
      attempts_max==1), `on_finished`/`cancel_export`/`on_close` (clear). Verified:
      16-check driver × both skins — real COM against a live Tk HWND (create/HrInit/
      set/clear all succeed against the live shell; safe no-ops when no object) + real
      standard export (begin-determinate → value(s) → clear) and real compressed export
      (begin-indeterminate → clear, zero value() calls) spied through the pipeline;
      gallery both skins. (Automated taskbar-strip grab inconclusive — the in-process
      test window groups under python.exe's button; the succeeding shell COM calls are
      the authoritative proof.)

## Bold track — surface rebuilds (choose per surface: patch OR rebuild, never both)

| ID | Item | Absorbs | Status |
|----|------|---------|--------|
| B0 | Background render queue utility (thumbnails/waveforms off the Tk thread via `ui()` marshaling) — prerequisite for B1/B4 | — | done 2026-07-15 |
| B1 | Real timeline: filmstrip lane, per-track waveforms, fat trim regions, always-visible keyframe lane, progress painted on the strip | F5 F6 F13, M1 M4, most of F7 | done 2026-07-15 |
| B2 | One adaptive screen (landing becomes the workspace empty state; command strip shows filename) | F4 F12, Q1 M3 | done 2026-07-15 |
| B3 | Command palette Ctrl+K (every action + hidden gestures, searchable, key hints) | F7, M2 | done 2026-07-15 |
| B4 | Export drawer + persistent job history (name patterns, per-job progress/attempts, OPEN/RE-RUN) | F5 F11, Q7 M1 | done 2026-07-16 |
| B5 | Focus/HUD mode (Tab collapses panels, translucent scanline controls per skin) | — | done 2026-07-16 |
| B6 | First-run coach marks overlay | cold-start half of F7 | done 2026-07-16 |

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

**B6 stage checklist** (designed 2026-07-16, autonomous session; decisions: fires once per
install ~700 ms after the FIRST successful probe — that's when the pointed-at controls exist —
gated by new `coach_marks_seen` setting; skipped silently if a modal is up (no-audio-tracks
dialog) so it retries next load; re-invocable via palette `help.coach` (workspace-ready only —
the legend's CTRL+K hint closes the discoverability loop, and the report's re-invocable ask);
look = SettingsOverlay's alpha-scrim pattern + a `-transparentcolor` overlay canvas so five
chamfered skin-panel callouts w/ keycap hint lines + accent connector lines float over the
dimmed editor, targets updated to TODAY'S surfaces (timeline gestures incl. Ctrl+wheel zoom &
[ ] trim; transport Space/C/K + toolbar toggles; EXPORT CLIP → Ctrl+E drawer; roster's
zero-affordance gestures right-click solo / double-click reset / wheel volume; legend card
covering Ctrl+K palette + Tab focus) + a GOT IT card; Esc / any click / GOT IT dismiss and
persist; showing exits focus mode and closes the drawer first; card drawing factored into a
reusable helper so the gallery demos it per skin; magic transparent color = near-black so
chamfer AA fringes read as dark edges):

- [x] S1 `ui/views/coach.py` (scrim + transparent overlay + callout renderer + connectors +
      dismissal paths), `coach_marks_seen` setting, first-probe trigger + modal guard, palette
      `help.coach`, gallery callout demo; driver both skins (20 checks: fires once, Esc/GOT
      IT/click dismissals, disk persistence, no re-fire, palette re-invoke, focus interlock)
- [x] S2 Acceptance: 12 checks × both skins (980x700 minsize clamping + live-resize reflow,
      Settings-grab guard leaves the flag unburned, drawer hidden by the tour, persistence
      round-trip across a second in-process app instance), S1 re-run green on final code,
      one placement fix (dropped the toolbar card's plain-text line — it overlapped the
      EXPORT card at minsize and the labeled checkboxes already carry that info)

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
- [x] S3 Palette `view.focus`, acceptance drivers (20 checks × both skins: palette toggle +
      crop-greyed predicate, drawer-over-focus Esc ordering, real GO export finishing inside
      focus; 5-check mpv run pixel-proving the chips over mpv's differently-parented window;
      S1 re-run green on final code), roadmap close-out

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

- **2026-07-17** — Shipped **L2 taskbar progress (ITaskbarList3)** on `feature/taskbar-progress`,
  one commit. New `win32.TaskbarProgress` hand-rolls the COM interface over its vtable with pure
  ctypes (no comtypes/pywin32): `CoInitializeEx` STA + `CoCreateInstance(CLSID_TaskbarList,
  IID_ITaskbarList3)` then calls `HrInit`(vtable 3) / `SetProgressValue`(9) / `SetProgressState`(10)
  / `Release`(2) through `WINFUNCTYPE` protos built from the vtable function pointers. Lifecycle is
  per-export — `begin()` lazily creates a fresh object, `clear()`/`shutdown()` release it — which
  sidesteps the pointer invalidation an Explorer restart would cause on a long-lived object; any
  failed call resets the pointer so the next `begin()` rebuilds. All calls run on the Tk/STA thread
  (the worker marshals via `app.ui`). Wired into the export pipeline: `start_export` calls
  `begin(indeterminate = compression_target_mb is not None)` — the multi-attempt compression tuner
  has no honest determinate mapping so it shows `TBPF_INDETERMINATE` (marquee), while a single-pass
  standard export shows a `TBPF_NORMAL` 0..100 bar fed by `on_progress` (only when `attempts_max<=1`);
  `on_finished` / `cancel_export` / `on_close` clear it (`TBPF_NOPROGRESS` + release). No-ops off
  Windows or if COM is unavailable, so the wiring needs no guards. Verified: 16-check driver × both
  skins — the raw COM object created and every call (`HrInit`/`SetProgressValue`/`SetProgressState`)
  succeeded against the live Windows shell on a real Tk HWND (authoritative: wrong GUIDs/ordinals
  would fail `CoCreateInstance`/`HrInit` and leave `_ptr` None), plus real standard (determinate
  begin→value(s)→clear) and compressed (indeterminate begin→clear, zero value() calls) exports
  spied through the pipeline; gallery both skins. Lesson: a determinate taskbar bar wants a single
  monotonic 0..100; the export's attempt-based `on_progress` (which resets per compression attempt)
  only maps cleanly for the single-pass path, so gating `value()` on `attempts_max<=1` and leaving
  compression on the marquee is the honest choice the report already called.

- **2026-07-16 (latest+2)** — Shipped **L1 silent-video support** on `feature/silent-video`
  (design approved in plan mode), 3 stage commits. A clip with zero audio streams is no
  longer a dead end (F2): `after_probe` sets `is_silent` (zero audio + decodable video) and
  falls through to the normal editor instead of the "No audio tracks" dialog+return; only a
  file with neither audio nor video stops. **S1 (preview):** `build_playback_filter` returns a
  video-only `[vout]` graph (no amix/`[aout]`) when tracks are empty, `build_playback_stream_cmds`
  maps only `[vout]` and drops `-c:a` (keyed off whether the filter contains `[aout]`), and both
  `PlaybackEngine.play()` and `MpvPlaybackEngine.play()` stopped raising on an empty track list
  (mpv's `build_mpv_lavfi` already emitted video-only); `start_preview`/`restart_playback_at`
  allow the empty path only when `is_silent`, so a normal clip with all tracks deselected keeps
  the "select at least one track" warning. **S2 (export):** `build_export_spec` passes an empty
  `filter_complex` when silent; the standard + compressed command builders read
  `bool(filter_complex)` as "has audio" and emit `-an` (no `[aout]` map / `-c:a`) otherwise,
  covering stream-copy, NVENC crop-reencode, and compressed; `dump_commands.py` gained three
  SILENT golden sections (the audio cases stayed byte-identical); crop `enter_preview` no longer
  blocks a silent clip. **S3 (UI):** roster shows "NO AUDIO — VIDEO ONLY" + a placeholder line,
  RESET disables with no tracks, and the mute/solo/reset gestures were already `track_controls`-
  guarded (inert); a normal reload restores the mix roster cleanly. Verified: S1 15-check driver
  × ffplay + mpv (video-only builders, silent preview/pause/resume/seek, normal-clip regression);
  S2 9-check driver (real 1080p silent stream-copy + NVENC-compressed-with-crop exports both
  `done` with 0 audio streams via ffprobe, silent crop-preview) + audio-export regression
  (drive_fixes 11/11); S3 8-check driver × both skins + silent-editor screenshot; gallery both
  skins. Lesson: a driver that reads a custom widget's disabled state must check its internal
  `_state`, not `cget("state")` — HaloButton is a `tk.Canvas`, whose own `state` attribute is
  unrelated to the widget's logical state (a green test would have missed a real regression).

- **2026-07-16 (latest+1)** — Fixed two bugs Ethan hit testing M12, on `feature/watermark-options`
  (touching app.py, core/motion.py, ui/crop_controller.py — none in the frozen diff-verifiable
  set). **(a) The CUSTOM/BOTH freetext field never showed.** `HaloSegmented` stores its verbatim
  UPPERCASE display label ("CUSTOM") into the bound var, but `on_watermark_mode_changed` /
  `get_timestamp_watermark_settings` compared against lowercase ("custom"), so the branch never
  fired. M12's driver had set the var directly in lowercase, bypassing the widget — the classic
  "tested the state, not the click" gap. Fix: the var now holds the uppercase label (so the
  segmented control's own selection highlight works too) and a new `watermark_text_mode()`
  helper normalizes to the lowercase id at the two read sites; init + both clip-reset paths set
  "CONFIGURED". **(b) Crop-keyframe exports crashed** — "Picture size 63113x34114 is invalid /
  Cannot allocate memory". The animated-SIZE motion chain (`motion.py` tier 3) scales the whole
  frame up by `out_w*iw/pw` before cropping, so a heavy zoom (a ~234px crop on a 3840px source
  at 4K output) demands a ~63000px-wide intermediate — past ffmpeg's ~INT_MAX-pixel limit, and
  a multi-GB alloc that OOMs. Two-part fix: (1) `_clamp_export_zoom` (new, motion.py) bumps any
  crop rect that would push the scale past `MAX_SCALE_DIM`=32000 per side up around its centre —
  a universal crash guard that also covers the 16px `CROP_MIN_SIZE` degenerate case, enforced
  per-dimension so a thin rect can't sneak a tiny width past an adequate area; (2) the compressed
  export now builds the motion chain at the capped target resolution (new `motion.cap_size`,
  threaded through `crop.export_prefilter(trim_start, max_dims)` from `build_export_spec`) instead
  of source res — the path downscales to 1080p afterward anyway, so building at 1080p makes the
  intermediate proportional to the real output and keeps the user's full 16x zoom (at 1920 out,
  the 32000 clamp's 230px floor sits just under their 234px crop, so nothing is clamped). The
  standard (uncompressed 4K) path stays source-res but is protected by the clamp (caps ~8x — the
  most ffmpeg can allocate at 4K anyway). Verified: a 10-check motion driver with REAL 4K ffmpeg
  exports (standard-4K-via-clamp + compressed-1080p-via-cap both succeed; the 234px zoom is kept
  at 1080p and clamped at 4K; a 16px degenerate crop is bounded on both axes) + an 11-check
  in-process app driver × both skins (freetext field appears on a REAL segmented-control click of
  CUSTOM/BOTH, custom/both text resolves, CONFIGURED hides it, and a **real NVENC compressed
  export with animated-size crop keyframes — the user's exact failing case — completes `done` at
  1080p** instead of erroring); M11b's 28-check watermark driver re-run green (two stale
  lowercase-var assertions updated to `watermark_text_mode()`); drawer screenshot confirming the
  field renders; gallery both skins. Lesson: a segmented control bound to a persisted/logic var
  must either use the id as its label or map explicitly (as settings.py's source/format rows do)
  — binding uppercase display labels to a var the logic reads as lowercase silently no-ops, and a
  driver that `.set()`s the var directly will never catch it. Drive the widget, not the variable.

- **2026-07-16 (latest)** — Shipped M12 (watermark long-date preset + per-export text override,
  Ethan's M11 follow-up) on `feature/watermark-options`. Settings gained a 4th date preset,
  "long" (`filters.watermark_date_part` special-cases it — strftime has no ordinal-day
  directive — via a new `_ordinal_day` helper: "April 6th, 2025"), generated the same way as the
  other three so the segmented button's example label can never drift from what export burns.
  The export drawer gained a per-clip text-mode row under the watermark checkbox: CONFIGURED
  (Settings' source, the existing behavior) / CUSTOM (a new freetext field, this clip only) /
  BOTH (stacks them, configured line on top, custom on the bottom — `get_timestamp_watermark_
  settings` now returns a list of 1-2 lines instead of a single string). New
  `app.watermark_mode_var`/`watermark_custom_text_var` are clip-scoped like trim: reset in both
  `load_video` (direct clip-to-clip switch, the Q6 leak path) and `reset_clip_state`
  (close/probe-fail), with an explicit `on_watermark_mode_changed()` call after each — `Halo
  Segmented`'s `command` only fires from a click, not a programmatic `.set()`, so the
  custom-text row's visibility needs an explicit sync or it silently keeps showing (empty) from
  the previous clip's mode. **Real bug hunted down via the verify-with-a-frame-grab
  discipline** (a naive "export succeeded" check would have shipped this broken): drawtext's
  `text=` option cannot reliably embed an apostrophe — neither a bare `\'` nor ffmpeg's own
  documented shell-style `'\''` trick actually works once ANY
  later drawtext option in the same filter is ALSO quoted (`alpha=`, `enable=`) — both silently
  desync the surrounding AVOption quote-tracking and corrupt the rendered text (sometimes a hard
  "No such filter: '0.500)'" parse error from the alpha expression's commas leaking out
  unquoted, sometimes a QUIET corruption that exit-code-only checks miss entirely — caught only
  by actually opening the extracted frame). The fix: `filters.write_watermark_textfile` writes
  the (possibly two-line) text to a content-hashed cache file under
  `%APPDATA%/ClipToolbox/watermarks/`, and the filter reads it via drawtext's `textfile=`
  instead — no command-line escaping of the content at all, stress-tested clean against
  percent signs, brackets, semicolons, embedded Windows paths, and mixed quotes. Cached under
  AppData rather than a temp dir specifically because `ExportJobSpec` bakes the resolved filter
  string in verbatim for RE-RUN, which can replay a job after a restart — the referenced file
  must still be there. Added `expansion=none` defensively since custom text can now contain a
  literal `%`. Layout fix in passing: an earlier change (moving the Date label to its own row
  to fit the wider "long" example) pushed the Settings card past the 700px minsize by ~16
  logical px — reverted to the original inline label+segmented row, which fits all four
  presets including "April 6th, 2025" with no clipping. Verified: 28-check driver × both
  skins (ordinal-day edge cases incl. 1st/2nd/3rd/11th/21st, cache-file content/hashing/reuse,
  mode-switch UI sync, clip-load reset, a real "both"-mode export with an apostrophe in the
  custom text, frame-extracted and read); a 6-case special-character stress test (`%`, `[]`,
  quotes, backslashed paths, colons, `;`/`,`) each frame-verified; M11's original 21-check
  driver re-run green on both skins after the settings layout fix; gallery both skins.

- **2026-07-16 (later)** — Shipped M8–M11 (all requested by Ethan mid-session): M8 on
  `feature/timeline-navigation`, M9+M10 on `feature/focus-crop`, M11 on
  `feature/watermark-options` (stacked in that order), one commit each. **M8 — timeline edge
  auto-scroll:** dragging the playhead/trim bracket/keyframe against the edge of a zoomed view
  arms a 50 ms after-loop that pans 2.5–10% of the span per tick (ramping with overshoot) and
  re-applies the live drag, so the dragged item rides the scrolling edge; disarms inward/on
  release, stops itself at the clip ends (17-check driver incl. after-info leak assert).
  **M9 — focus + crop compatibility:** B5's mutual exclusion removed — Tab enters focus with the
  crop editor open, C toggles crop inside focus, the crop toolbar re-packs under the timeline
  strip while the transport row is hidden (and back after it on exit via
  `CropController.reposition_toolbar`), and new `app.on_crop_editing_changed` has the HUD chips
  yield the preview to the editor and return for preview-mode playback; palette `view.focus`
  ungreyed (22 checks × both skins incl. a corner drag committing a keyframe on the enlarged
  editor). **M10 — preview mouse gestures:** embedded player windows are now input-DISABLED
  (new `win32.disable_window_input`; ffplay inside `embed_external_window_hidden`, mpv at hwnd
  discovery) so real clicks over live video fall through to Tk — verified with an actual
  SendInput right-click — and ffplay's built-in mouse seek/fullscreen can't fire; the posted-
  spacebar pause still lands (disabled windows still receive posted messages — verified native)
  and the player stops stealing keyboard focus. Gestures: hold LMB 450 ms = 2× while held
  (from pause it skims and re-parks paused), double-click = focus toggle, right-click =
  play/pause. Engines grew `set_rate`/`rate` (protocol updated): mpv sets `speed` live; ffplay
  bakes setpts+atempo into the spawn graph AFTER the amix (Parsed_volume_i targets unmoved),
  position = start + clock×rate, paused pipelines drop on rate change, stop() resets
  (20 ffplay + 19 mpv checks incl. measured ~2× vs ~1× position rates). **M11 — watermark
  expansion:** new Settings section (Text source FILENAME TIME / FILE DATE / FILENAME; Date
  format presets labeled by concrete examples from `filters.WATERMARK_DATE_FORMATS`; include-
  time-of-day toggle; live per-clip preview line that also surfaces resolve errors before
  export). New pure `filters.resolve_watermark_text` / `format_watermark_datetime` /
  `extract_recording_datetime` (old string extractor kept as wrapper); settings keys
  `watermark_source`/`watermark_date_format`/`watermark_include_time`; the parsed-source error
  now points at Settings (21 checks × both skins incl. a real re-encoded export frame-grabbed
  to prove the burned text). Layout callout: adding the section overflowed the settings card at
  the 700 px minsize — reclaimed via tighter section padding and the About block condensing to
  two lines (font info merged into the version line). Lesson: PowerShell 5.1 mangles embedded
  double quotes in git-commit here-strings passed to native git — keep commit messages
  quote-free.

- **2026-07-16** — Shipped M6 + M7 (timeline seek/navigation polish, both requested by Ethan
  this session) on `feature/timeline-navigation` (stacked on `feature/coach-marks`), one commit
  each; same-surface pair batched on one branch like a Q-batch. **M6 — the fix for "clicking
  near a trim bracket steals the seek":** the ruler band is now a dedicated always-seek scrub
  lane — trim-bracket hit-testing (grab + hover) moved into the strip body below it, so
  clicking the ruler seeks precisely even directly over a trim point; brackets grab with an
  offset instead of snapping to the cursor and only move after a px(3) drag threshold; and a
  click-without-drag on a bracket seeks the playhead to that trim time (new
  `bind_seek_request` hook → `app.seek_absolute`). Handle visuals shortened to start below the
  ruler so they match the hit zone. **M7 — zoomed-view navigation:** the minimap grew 2→6
  logical px (filmstrip lane absorbs the difference; SEEKBAR_H unchanged) and became a real
  navigator scrollbar — when zoomed, an accent thumb (min-width px(10), hover/drag brightening)
  marks the visible window; dragging it pans, clicking the track jumps the window centered on
  the click then keeps dragging (classic scrollbar semantics); middle-mouse drag pans the strip
  1:1 in view-space from anywhere (fleur cursor); `follow()` yields while either drag is live.
  Filmstrip tiles now cache scaled per (idx, slot_w, lane_h) across recomposes (cleared on
  set_filmstrip, capped 512) so pan drags re-slot from cached tiles instead of re-running
  LANCZOS resizes. Palette `view.resetzoom` gained pan/minimap keywords. Verified: two
  widget-level drivers (19 + 20 checks: ruler-click over bracket x, offset drag, click-seek,
  sub-threshold jiggle, kf-lane priority, hover bands, thumb drag/jump/clamp, pan clamp,
  follow interlock, tile-cache reuse, disabled inertness) + a 14-check in-process app driver ×
  both skins with a real synthetic clip (real probe, event_generate at real coordinates,
  ctrl-wheel zoom through the WheelRouter path, trim survival across navigation); gallery both
  skins. Lesson: a first-run-state driver must write `coach_marks_seen: true` into its temp
  config — a virgin config re-fires the B6 tour 700 ms after the first probe and its scrim
  swallows the test clicks.

- **2026-07-16** — Shipped B6 (first-run coach marks) on `feature/coach-marks` (stacked on
  `feature/focus-hud`), 2 stage commits, autonomous session — the bold track (B0–B6) is now
  complete and F7 is fully closed. New `ui/views/coach.py`: the SettingsOverlay two-layer
  pattern extended with a `-transparentcolor` overlay Toplevel (magic key #010101, near-black
  so the chamfer's AA fringe reads as a dark edge) over the 0.45 alpha scrim, so five
  chamfered skin-panel callouts with keycap hint lines + accent connectors float over the
  dimmed editor: TIMELINE (drag/wheel/Ctrl+wheel/[ ]), PLAYBACK & TOOLS (Space, frame step,
  C/K), EXPORT (Ctrl+E drawer), AUDIO MIX (the audit's zero-affordance gestures — right-click
  solo, double-click reset, wheel volume), EVERYTHING ELSE (Ctrl+K, Tab), plus a GOT IT card
  ("shows once — reopen from the CTRL+K palette"). Fires once per install, 700 ms after the
  first successful probe (new `coach_marks_seen` setting, saved on dismissal); the deferred
  trigger carries the load token and yields to modals/grabs WITHOUT burning the flag, so a
  first load that hits the no-audio-tracks dialog gets the tour on the next clip instead.
  Esc / any click / GOT IT dismiss; re-invocable via palette `help.coach` (workspace-ready
  only); showing exits focus mode and hides the drawer first; callouts clamp into the window
  and reflow on live resize. `draw_callout` is a standalone renderer, demoed in the gallery
  per skin. Verified: two in-process drivers × both skins (S1: 20 checks — first-load fire,
  all five cards present, three dismissal paths, on-disk persistence, no re-fire, palette
  re-invoke, focus interlock; S2: 12 checks — minsize clamping, live-resize reflow, modal
  guard, drawer interlock, and a persistence round-trip across a second in-process app
  instance); gallery both skins. Lessons: (1) screenshot drivers that set `-topmost` on the
  root push it ABOVE sibling overlay Toplevels — raise the whole stack into the topmost band
  in order; (2) a second Tk root in one process needs the module-level skin PhotoImage cache
  reset (`skin._skin = None`) — the cached images belong to the destroyed interpreter.

- **2026-07-16** — Shipped B5 (focus/HUD mode) on `feature/focus-hud` (stacked on
  `feature/export-drawer`), 3 stage commits, autonomous session. Tab (clip loaded, not typing,
  no modal) collapses everything around the video: the command strip, right column (roster +
  log), and the transport/frame/export rows hide, and the preview bezel grows to fill the
  workspace; the timeline strip stays beneath the video as the one control surface, so trim
  brackets, keyframes, Ctrl+wheel zoom and the export sweep all keep working full-width. Tab or
  Esc exits (Esc keeps its cancel-export → leave-entry → close-drawer priorities); the legend
  stays and swaps to focus hints, and the editor legend now advertises TAB FOCUS (WHEEL hint
  retired to the palette). HUD chips overlay the preview letterbox via new
  `skin.render_hud_chip` — a scanline panel pre-blended toward black (Tk can't alpha-composite
  over an embedded player HWND; blending toward the black letterbox reads as translucent) —
  with per-skin looks from existing tokens only (Reach's zero chamfer → straight-edged steel).
  `ui/views/hud.py`: clip-name chip top-left (follows clip swaps via the file-label trace) and
  a transport chip bottom-right — native-canvas glyph (play/pause/starting/stopped shapes, no
  font roulette) + timecode riding the existing time-var traces, zero PIL on the 10 Hz path.
  Focus is transient (never persisted), survives clip swaps, works during exports (Tab back out
  any time); crop-edit and focus are mutually exclusive (entering with CROP on is refused with
  a status hint; C inside focus exits focus first). close_clip/failed-probe exit via
  reset_clip_state; the drawer stays orthogonal (Ctrl+E slides it over focus). Palette gained
  `view.focus` (greyed while cropping). Discovery: `anchor_child_window` re-raises the ffplay
  window to HWND_TOP on every first-frame reveal, burying Tk siblings — the chips are the
  app's first widgets over LIVE video (stills/cropbox always had the player hidden), so new
  `win32.raise_window_to_top` (async, no move/size/focus) re-asserts them on playback-state
  transitions + 120/450 ms follow-ups. Verified: three in-process drivers × both skins (S1: 37
  checks — layout flip, pack-order restore incl. export_row's pack-first priority, crop
  refusal + C-handoff, Tab-in-entry traversal, Ctrl+W-in-focus, clip-swap survival; S2: 16
  checks — chip text/glyph state machine over a real engine, plus a pixel probe proving the
  chips paint above live video; S3: 20 checks — palette toggle, drawer-over-focus Esc order,
  real GO export finishing inside focus; +5-check mpv run for the other z-order shape);
  gallery both skins with a HUD-chip demo band. Lessons: (1) key-event drivers must
  `focus_force()` before `event_generate` — the embedded player steals keyboard focus
  mid-run and the event then has no focus window; (2) Tab traversal lives on the `all`
  bindtag, so a toplevel binding returning "break" cleanly suppresses it while letting
  entry-focused Tabs fall through by returning None.

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
