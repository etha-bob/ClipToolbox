# ClipToolbox Usability Report

**Date:** 2026-07-12 · **Build:** v2.0 (branch `feature/halo-reach-skin`) · **Config under test:** mpv engine, Reach skin, NVENC available, 200 % DPI

## Methodology

Three-part audit:

1. **Static UX audit** of the full UI layer (shortcuts, tooltips, dialogs, widgets, settings, theming, confirmations, busy states).
2. **Scripted hands-on sessions** driving the real app in-process (real Tk mainloop, real ffmpeg/mpv/NVENC) through 25+ scenario steps across three runs — landing/edit flows, export flows, and notification verification — with a per-step screenshot and a journal of every status line, dialog, and toast the app emitted. Synthetic test media generated with the bundled ffmpeg: a 2-track clip (eng/spa), a video-only clip, a 92 MB high-bitrate clip (forces real multi-attempt compression), and a corrupt file.
3. **Feature work:** the top notification gap was fixed in this pass (taskbar flash on background export completion, see below) and verified with scripted positive/negative assertions.

Screenshots and journals live in the session scratchpad (`shots/`, `journal_*.json`); they are not committed.

---

## What already works well

Credit where due — these tested excellently and should be treated as load-bearing patterns:

- **The activity log narrative.** The compression tuner explains itself remarkably well ("attempt 1/8: encode budget 9.90 MB internal… File is under the limit but leaves room unused. Retrying with a 10.10 MB budget"). Power users can reconstruct exactly what happened.
- **Completion toast** with filename, Discord-aware size ("9.86 MB in Windows/Discord (10.34 decimal MB)") and an OPEN FOLDER action instead of auto-opening the folder.
- **Compression accuracy:** the 8 MB target produced a 7.96 MB file in 2 attempts (~38 s for a 92 MB/60 s source, H.265 NVENC).
- **Contextual legend bar** (footer key hints change per screen and during export), tooltips on the less obvious controls, live bitrate estimate that tracks the trim duration.
- **Session persistence** (trim/crop/mix/playhead per video, keyed by path + size validation) restores across app restarts and processes — confirmed working end-to-end.
- **Busy-state handling during export:** editing controls disable, CANCEL EXPORT swaps in, Esc cancels, cancel takes effect immediately.
- **Direct-manipulation touches:** per-track right-click solo, double-click volume reset, wheel volume, Ctrl+wheel timeline zoom, per-handle crop cursors, Shift-drag to free the crop aspect.
- **Crash-safe threading discipline** (worker → UI queue → Tk pump) held up under scripted abuse; no hangs or corruption in any run.

---

## Findings (severity-ranked)

| # | Severity | Finding | Evidence |
|---|----------|---------|----------|
| 1 | **Major — fixed this pass** | No notification when an export finishes while the app is unfocused; completion was a silent toast | Design gap; now: taskbar flash (see "Shipped") |
| 2 | **Major** | Video-only clips (no audio) are a hard dead end: preview and export both refuse; the workspace still looks fully operational | Hands-on: `no_audio.mp4` |
| 3 | **Major** | Unreadable file → two stacked dialogs ("FFprobe Error", then "No audio tracks"), then a stranded workspace whose placeholder claims "No audio tracks found." (wrong reason) with an enabled-looking EXPORT button | Hands-on: `corrupt.mp4` |
| 4 | **Major** | Loaded filename appears nowhere persistent; window title is always "ClipToolbox" | All shots; `file_label_var` is set but never rendered |
| 5 | **Major** | Export progress is a status-bar text line only. The seekbar does not move during export, and each compression attempt restarts the percentage at 0 (a 2-attempt export shows two full 0→100 % cycles) | Export journal, shots 20/23 |
| 6 | **Major** | Session restore silently shapes the next export: restored trim (0:04–0:14) cut the exported file in half, disclosed only by one log line and the bracket positions. Restored crop keyframes are invisible while crop is off (they are inert — verified in code — but the "Restored saved setup: … 2 crop keyframe(s)" message doesn't say so) | Hands-on: reload + export run |
| 7 | Minor | ~22 shortcuts exist; the legend surfaces ≤6 and there is no help overlay/F1. Hidden gestures (right-click solo, double-click reset, time-label click, Ctrl+Shift+C, Shift+wheel, Shift+drag aspect) have no affordance at all | Static audit |
| 8 | Minor | Destructive actions are inconsistent: crop CLEAR confirms; trim CLEAR and CLEAR RECENT CLIPS fire instantly; nothing is undoable | Static audit |
| 9 | Minor | Settings: Esc **saves** (bound to the same `close()` as DONE) — universal expectation is Esc = cancel. Apply timing is also mixed (skin = restart with note; engine/cache = live) | Static audit |
| 10 | Minor | Workspace state leaks across loads: the trim-enabled checkbox stays on for the next clip (with full-range values); after a failed load the previous clip's trim row lingers | Shots 11, 23 |
| 11 | Minor | A success toast (12 s lifetime) from the previous export stays visible while the **next** export is already running — "COMPLETE" on screen during active compression | Shot 23 |
| 12 | Polish | Landing menu is mouse-only (no arrow/Enter navigation, no focus semantics) | Static audit |
| 13 | Polish | "Starting preview…" placeholder is static text for the multi-second engine spin-up; no motion/spinner cue | Shots 3, 13 |
| 14 | Polish | Recent clips carry no marker for "has a saved session", so restores (finding 6) arrive unannounced | Shot 15 |

**Developer-facing cleanups spotted in passing** (no user impact): `main()` and its `__main__` block are defined twice in `app.py` (~2760/2790); the "USER EDIT ME" window-size knobs in `constants.py` are never read (`build_ui` hardcodes 1150×780); `HaloButton._measure_text` has a dead first line; `dnd_hint_var`/`file_label_var` are written but never displayed.

### Keyboard coverage matrix

| Context | Works | Gaps |
|---------|-------|------|
| Landing | Ctrl+O, Ctrl+,, Esc | Menu items unreachable by keyboard (finding 12) |
| Workspace | Space, ←/→ (+Shift fine), Home/End (+Shift trim), `,`/`.` frame-step, 0–9 jump, `[`/`]` trim, m mute, c crop, k keyframe, Ctrl+0 zoom reset, Ctrl+E export, Ctrl+Shift+C timestamp, Esc menu | None functional — all verified via synthetic key events — but most are undiscoverable (finding 7) |
| During export | Esc = cancel (legend says so) | — |
| Dialogs | Return = default, Esc = dismiss/No | — |
| Settings | Return/Esc close | Esc saves instead of cancelling (finding 9) |

### Skin parity

Both skins funnel through the same renderers (`skin.py`), so widget states stay consistent; Reach differs deliberately (silver-band hover, no brackets, Bahnschrift when installed). Hands-on runs used Reach; the widget gallery (`python -m cliptoolbox.ui.gallery --screenshot …`) renders both without errors. No parity defects found.

---

## Shipped in this pass: taskbar flash on background export completion

**Behavior:** when an export **completes or fails** while ClipToolbox is not the foreground app, its taskbar button flashes and stays highlighted until you click back into the app (Windows `FLASHW_TIMERNOFG` — the OS stops the flash on focus, no bookkeeping). Nothing happens if you're already looking at the app, and a user-initiated cancel never flashes. On by default; toggle in **Settings → Window → "Flash the taskbar when exports finish in background"**.

**Implementation** (4 files, ~70 lines, zero new dependencies):

- `cliptoolbox/core/win32.py` — `GetForegroundWindow`/`IsIconic`/`FlashWindowEx` ctypes bindings + `_FLASHWINFO`; helpers `is_foreground_process()` and `flash_taskbar(hwnd, until_focused=True)`. Foreground logic: the foreground HWND's PID vs ours (embedded player windows are WS_CHILD and can never hold foreground, so a PID check covers every window we own), **plus an iconic check** — Windows keeps reporting a minimized window as "foreground" until the user activates something else, so a minimized app must count as background. The scripted verification caught this live: without the `IsIconic` guard, exports finishing while minimized never flashed.
- `cliptoolbox/app.py` — `notify_export_attention()` (Tk-thread-only; checks the setting, then the foreground state, then flashes `chrome.get_root_hwnd(root)`), queued via the existing `app.ui(...)` marshaling as the first act of both `on_complete` and `on_error`.
- `cliptoolbox/settings.py` — `notify_flash_taskbar: bool = True` (auto-persisted; older configs pick up the default).
- `cliptoolbox/ui/views/settings.py` — the checkbox row + persistence in `close()`.

**Verification** — scripted against the real app (`drive_app.py flash` mode). Assertions wrap `flash_taskbar` at the app seam: was it called, what did `is_foreground_process()` decide, and did `FlashWindowEx` accept the call. (A taskbar screenshot was also captured, but in the synthetic iconified case Windows renders the active-window underline and the attention underline too similarly to differentiate at crop scale — the alt-tab manual smoke below is the unambiguous visual.) Two things the verification itself surfaced: `FlashWindowEx`'s return value reports prior *caption-active* state, not flash state (useless under DWM — early probe-based assertions were discarded), and the minimized-foreground quirk above, which was a real pre-ship bug. Final results:

| Scenario | Expectation | Result |
|----------|-------------|--------|
| Export completes while iconified | flashing | **PASS** |
| Export completes while foreground | not flashing | **PASS** |
| Setting disabled, export completes iconified | not flashing | **PASS** |
| Export cancelled mid-flight while iconified | not flashing | **PASS** |
| Export errors (unwritable target) while iconified | flashing | **PASS** |

Manual smoke: Ctrl+E, alt-tab away — the button flashes on completion and stops the instant the app is clicked.

---

## Enhancement roadmap

Two tracks. The **incremental track** (S/M/L below) fixes each finding in place with isolated, diff-reviewable changes. The **bold track** (next section) redesigns whole surfaces — several incremental items become obsolete inside it, so pick per-surface: either patch it or rebuild it, not both. Effort tags: S (≤1 h), M (half day), L (multi-day), XL (multi-week surface rebuild).

### Quick wins (S)

1. **Filename in the window title** — `root.title(f"{name} — ClipToolbox")` on load, reset on `show_landing`; optionally render the orphaned `file_label_var` as a middle status-strip column. Pairs directly with the flash feature (identifiable taskbar button). *(Findings 4)*
2. **One accurate error for unreadable files, then back to the menu** — in `after_probe`, distinguish "file could not be read" (return to landing, clear state) from "no audio tracks" (stay, see item 6); never show both dialogs. *(Finding 3)*
3. **Settings: Esc cancels, DONE saves** — split `close()` into save-and-close vs teardown-only; bind Escape to the latter. *(Finding 9)*
4. **Session-restore toast with RESET action** — alongside the existing log line: `toast("Restored saved setup", …, action_label="RESET")`; don't count crop keyframes in the message when they're inert. Optionally a small dot on recent-clip rows that have sessions. *(Findings 6, 14)*
5. **UNDO-toast instead of instant clears** — trim CLEAR captures old values and offers UNDO in a toast (toasts already support action buttons). Note: while the Settings overlay holds its grab, toast buttons are unclickable — for CLEAR RECENT CLIPS flip the button to "UNDO CLEAR" in place instead. *(Finding 8)*
6. **Reset leaked workspace state on load** — trim checkbox/in-out cleared with the rest when a new clip loads. *(Finding 10)*
7. **Supersede stale success toasts** — dismiss surviving export toasts when a new export starts. *(Finding 11)*

### Medium (M)

8. **Real export progress** — add `on_progress(percent, attempt, attempts_max)` to `ExportCallbacks` (parsed data already exists); render a thin determinate strip in the status area; treat compression attempts honestly (per-attempt fill + "attempt 2/8" label, or indeterminate). Skip ETA — the multi-attempt tuner would make it a lie. *(Finding 5)*
9. **F1 shortcut cheat-sheet** — a dim+card overlay (reuse the Settings pattern) listing all bindings incl. hidden gestures; `F1`/`?` from both screens; add "F1 HELP" to the legend. *(Finding 7)*
10. **Landing keyboard navigation** — Up/Down/Enter over the menu items, selection state drives the existing hover detail panel. *(Finding 12)*
11. **Animated "starting preview" cue** — three-dot pulse on the placeholder label; trivial visual, disproportionate perceived-speed payoff. *(Finding 13)*

### Larger (L)

12. **Silent-video support** — make audio optional through the pipeline: probe result of 0 tracks yields an empty mix (skip `amix`), preview without audio branch, export with `-an` when no tracks selected. This converts finding 2 from a dead end into a supported workflow (screen recordings, muted game clips). Touches `filters.py`, preview engines, `export.py` — needs its own careful pass.
13. **Taskbar progress bar (ITaskbarList3)** — green progress fill on the taskbar icon during export; assessed this pass and deliberately deferred: ~100 lines of hand-rolled COM vtable ctypes with real pitfalls (STA/thread affinity on the Tk thread, vtable ordinals `SetProgressValue`=9/`SetProgressState`=10, Explorer-restart pointer invalidation, and the multi-attempt tuner mapping poorly to a determinate bar — use `TBPF_INDETERMINATE` during compression). Worth doing only as its own isolated diff after item 8 exists.
14. **Single-level undo for edit state** (trim/crop/mix snapshots) — supersedes item 5's per-action approach if appetite exists.

---

## Bold track: redesign directions

Drastic changes, deliberately. Each is grounded in tested findings, keeps the PIL-canvas + skin-token architecture (no new dependencies; both skins keep working because all rendering already funnels through `skin.py`/`theme`), and names what it absorbs from the incremental track.

### B1 — A real timeline (the highest-leverage rebuild) · XL

Replace the thin seekbar with a full timeline panel:

- **Filmstrip lane:** ~40 thumbnails extracted once per clip with the bundled ffmpeg (`fps=` filter → stills; the codebase already does single-frame extraction) and cached per session. Scrubbing gets spatial memory; trim placement stops being blind.
- **Waveform lane per audio track:** one `showwavespic` render per track at load, tinted by the track's mix state (mute/solo dims its lane). The mixer roster and the timeline stop being separate worlds.
- **Trim as a first-class region:** shaded exclusion zones with fat grab handles drawn over the filmstrip, instead of 6-px brackets under a 4-px bar.
- **Crop keyframes as a lane:** diamonds with drag + right-click delete, visible *whenever keyframes exist* — which also fixes the invisible-restored-crop problem structurally.
- **Export progress painted across the timeline** (fill sweeping left→right over the strip, attempt counter at the playhead), replacing the status-text-only feedback.

Absorbs findings 5, 6, 7 (partially), 13 and incremental items 8 and 11. Everything here is PIL-composited images on a canvas — the same technique `HaloSeekbar` and `CropBoxCanvas` already use, just bigger.

### B2 — One adaptive screen (kill the landing/workspace split) · L–XL

The landing menu becomes an **empty state of the workspace**: a drop-zone hero with a recent-clips thumbnail grid where the preview will live; loading a clip morphs the same screen into the editor. LOAD/SETTINGS/QUIT collapse into a slim persistent command strip. Removes the two-screen mode model (Esc-to-menu ambiguity, `show_landing`/`show_workspace` routing, duplicated legend states) and makes drag-drop the primary path instead of a hidden one. Finding 12 disappears (nothing left to arrow through); finding 4's filename display gets a natural home in the command strip.

### B3 — Command palette (Ctrl+K) · M

One Halo-styled console listing **every** action with its key hint, fuzzy-filterable, Enter to run. This is the drastic answer to discoverability (finding 7): instead of teaching 22 bindings via a static F1 sheet, every hidden gesture becomes a searchable, executable command ("solo track 2", "copy timestamp", "zoom timeline"). The F1 sheet (incremental item 9) becomes just a view inside it. Fits the fiction: it reads as a HUD console, and each skin can voice it differently.

### B4 — Export drawer with job history · L

Replace the save-dialog-then-status flow with a right-side **export drawer**: destination + name pattern (`{clip}_{trim}` tokens), size target with the live estimate that already exists, one GO button — and beneath it a **job list**: each export as a row with its own progress bar, attempt counter, final size, and OPEN/REVEAL/RE-RUN actions that persist for the session. Toasts (and the new taskbar flash) become pointers into this list rather than the only record. Absorbs findings 5 and 11 and incremental item 7; the compression tuner's excellent log narrative finally gets a UI surface worthy of it.

### B5 — Focus/HUD mode · M–L

Tab (or F) collapses both side panels and overlays translucent scanline controls on the video — transport, trim handles, timestamp — fading out when idle. Pure presentation-layer work on existing canvas widgets; the skins make it worth doing (Reach silver HUD vs H2 cyan brackets). Pairs with B1: HUD mode shows a mini-timeline strip.

### B6 — First-run coach marks · S–M

One-time dim overlay pointing at the four load-bearing controls (seekbar gestures, trim keys, crop key, export) with their key hints; re-invocable. The drastic-but-cheap fix for the cold-start half of finding 7.

**Suggested sequencing if the bold track wins:** B3 (cheap, immediate, independent) → B1 (the centerpiece) → B4 → B2 → B5/B6. B1 and B4 both want a small shared "background render queue" utility (thumbnail/waveform extraction off the Tk thread through the existing `ui()` marshaling pattern) — build that first as its own diff.

---

## Test-run appendix

- Runs: `flows` (15 steps, 28 s), `exports` (55 s incl. two NVENC compression exports + cancel), `flash` (5 assertions). Driver: in-process Tk with chained `after()` steps; save-dialog monkeypatched; keyboard scenarios via real `event_generate` so the actual binding layer is exercised.
- App state (`config.json`, `sessions.json`) snapshotted before testing and restored after; test exports written to the scratchpad only.
- Known environmental artifact: the NVIDIA overlay badge appears over the app when mpv spawns; unrelated to ClipToolbox.
