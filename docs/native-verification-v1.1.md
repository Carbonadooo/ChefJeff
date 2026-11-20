# Native 1.1 safe verification report

> Historical CPU-only checkpoint. The graphics pause was subsequently lifted and real-window acceptance completed; see [native 1.1.1 final verification](native-verification-v1.1.1.md).

Date: 2026-11-15 UTC. Environment: Windows, Python 3.12.11, existing isolated `.venv`. No original engine, Cocos source, map, atlas PNG or manifest was modified. No commit/push/reset/clean was performed. Previous native implementation files were backed up before this update at `%TEMP%\chefjeff-before-decision-steps-20261115-010146`.

The user's graphics-test pause is active. This update was implemented and checked without opening a window, importing Pygame in the headless checks, initializing SDL, rendering a screenshot, playing audio, using CUDA or running a model. The previous v1.0 real-window results apply only to that earlier geometric renderer.

## Completed safe checks

| Check | Actual result |
|---|---|
| Portable native/core engine runner | **343 tests, OK, 2 skipped**, final run 54.917 s |
| New timing suite | **9 tests passed** (included in 343) |
| New static art suite | **5 tests passed** (included in 343) |
| Existing ingredient-pack tests | **6 passed** |
| Existing visual-geometry tests | 3 run, **OK, 1 skipped** |
| Existing audio-asset checks | **7 passed**; no audio played |
| New source compilation | Passed; no GUI imports executed |
| `git diff --check` | Passed |
| Legacy v1 full-round replay | 413 events, score 500 verified; original file bytes unchanged |
| Custom CLI timing | `0.075` explicitly rounded to `0.1`, 2 steps = 4 ticks = 0.2 s |
| Invalid CLI timing | `nan` rejected with argument error; no episode/window started |

Tests demonstrate that equal-duration **identical low-level inputs** produce identical checked kitchen state at decision settings 0.1 and 1 seconds, including movement/collision and the same seed. At the default 20 Hz each call to the original engine remains at most 0.05 s. Different render pacing samples (30 vs 120 per wall second) produce the same two-second advance. Pause samples do not advance either clock; catch-up wall time is retained. Deferred agent submissions start at the correct following boundary, duplicate unconsumed submissions are rejected, scheduled releases occur at the correct tick, no-input movement holds, reset preserves timing and returns time to zero, and short/diagonal/repeated two-player input is retained as specified.

Three rapid interaction presses produce three recorded attempts with applied/refused outcomes. Queues and scheduled/submitted actions are explicitly canceled on clear. New replay checks reject changed decision boundaries, and existing tests reject changed raw events/scores and incomplete recordings.

## Complete headless decision rounds and replay

Both rounds used the existing reference trace driver, Level 1, seed 7. The policy was called once per decision; different decision cadences therefore intentionally produce different action traces/results. Both rounds advanced the same real-game duration. These are CPU/unpaced tests, not claims about actual wall-clock GUI speed.

| Field | 0.1 s decision | 1 s decision |
|---|---:|---:|
| Simulation time | 180.0 s | 180.0 s |
| Internal adapter ticks | 3600 | 3600 |
| Completed decisions checked | 1800 | 180 |
| Score | 500 | 350 |
| Served | 10 | 7 |
| Raw engine events checked | 412 | 302 |
| Recording boundaries checked | 7202 | 3962 |
| Replay | **verified** | **verified** |
| End reason | round_complete | round_complete |

Files retained locally (ignored generated evidence):

- `native-recordings/decision-0.1-final.jsonl` — 3,205,451 bytes; episode `28bd610aaaa442cfa4a60f3f16581606`; state SHA-256 `f4d463efc6c7d6bace3c3cfefdf105662982e4c915133551055448d1278a425a`.
- `native-recordings/decision-1-final.jsonl` — 1,694,169 bytes; episode `892569f7937a454da50acc518822da56`; state SHA-256 `33a12d0c22b447a723e845eecd7bf37675603dcf98bdb91f27e95ff618113b31`.

These use `chefjeff-native-v2`, with requested/effective decision timing, unchanged 0.05 s adapter/engine settings, render FPS, presentation choice and offline pacing declared in the header. Applied engine inputs and events are still replayed through the original `kitchen.apply_input`. Neither old samples nor their schemas were rewritten. Legacy source-identity differences require the already available `--allow-code-change` switch while all event/state/score checks remain active.

## Static original-art coverage

The catalog mirrors `LevelOneArt.ts`'s 13-atlas load/prefix/override sequence and resolves **627 frame keys**. Manifest fingerprint: `7e00a35658e974ac500cef6234720c13affe4e435fbf20d3d75da40d5cb72cc8`.

CPU checks verified atlas rectangle bounds and anchor conversion, original frame precedence, all four authored map scene plans with no missing selected frames, character identity/direction/walk/chop/diagonal-release keys, back-facing held-item depth, filled pans, partial/full burger layers, fire/steam selection and source immutability. All of this runs without image decoding or Pygame import. Asset data validity and scene commands do not establish rendered visual correctness.

Implemented presentation code reuses original floor/walls/cabinets, directions/animation frames, sources/devices, sink/rack/plates, foods/vessels/dishes, fire/steam/dash effects and order icons. Original source/assets are read in place. The palette follows the original Cocos HUD tokens; typography/panel layout and several advanced layered effects remain different. Consult `native-decision-art.md` for the exact port scope, resource provenance/terms and visual limitations.

## Deferred acceptance — graphics pause remains active

The following were deliberately **not run** after the user reported a game-launch problem:

1. Starting either new presentation mode in a real Windows window.
2. Running `scripts/check_native_window.py` or any dummy/real SDL render test.
3. Capturing/comparing the restored renderer against an original browser/resource screenshot.
4. Inspecting pixel proportions, sink halves/wires, directional hand/knife occlusion, effects and all GUI states.
5. Physical keyboard/diagonal/dual-player/focus-loss acceptance and actual GUI real-time pacing under load.

There is no claim of complete visual parity, pixel equality or physical-keyboard success. The next graphics step, once explicitly resumed, is to run the window check at both decision settings, inspect original-art snapshots and the listed key states, then address any visual issues. No unrelated process was terminated and no system/GPU configuration was changed.

## Files changed in this update

- Added `native/timing.py`: decision windows, queued `DecisionPort`, reset/state/training transitions and independent wall pacing.
- Updated `native/game.py`: schema-v2 timing/runtime metadata, ordered command lists/outcomes and decision-aware replay; legacy step/replay retained.
- Updated `native/controls.py`: raw observed key evidence and per-player button FIFOs.
- Added `native/art.py`: GUI-free original atlas catalog and inspectable scene composition.
- Added `native/sprite_renderer.py`: lazy original texture loading/caching and software Pygame execution (not executed under this pause).
- Updated `native/window.py`, `native_play.py`, `native/__init__.py`: original-art mode, timing options/status, real-time tick integration and version 1.1.0.
- Added `tests/test_native_timing.py`, `tests/test_native_art.py`; extended `scripts/check_native.py`.
- Added `docs/native-decision-art.md` and this report; retained earlier documentation with a version/update note; extended `.gitignore` for generated evidence.

Exact commands and API examples are in `native-decision-art.md`. Runtime installation still uses `requirements-native.txt`; no new gameplay dependency is required.
