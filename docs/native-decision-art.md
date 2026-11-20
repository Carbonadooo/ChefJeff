# Native 1.1: decision steps and original art

> Native 1.2 adds uniform slow play with `--speed 0.5` or `--speed 0.25`. Default speed is 1. Tick and decision intervals remain in game seconds. See [game speed and recording semantics](native-speed.md).

This update adds a discrete decision interface while keeping the existing kitchen engine, its maximum 50 ms integration steps, keyboard controls and two-player semantics. It also ports the original atlas composition into the native renderer. Original engine/Cocos/assets files are read-only and unchanged.

**Verification update (1.1.1):** the user authorized normal graphics testing again. Real Windows/SDL rendering, 0.1/1-second wall-clock pacing, synthetic keyboard/pause/focus events, all-map captures, original-resource comparison and two complete rendered/replayed rounds have now passed. See [final visual verification](native-verification-v1.1.1.md). Physical hardware keyboard input remains a manual acceptance item; injected computer-use keys did not reach SDL.

## Four separate clocks

| Clock | Default | Meaning |
|---|---|---|
| Wall time | Monotonic elapsed seconds | GUI pacing only. Paused/focus-lost time does not advance the game. |
| Adapter / engine integration | 20 Hz / 50 ms | Existing `LocalGame.step()` duration. `Kitchen.advance()` still subdivides at no more than 50 ms. |
| Decision step | **0.1 s**, configurable | One training transition / one agent boundary. 0.1 s runs 2 default ticks; 1 s runs 20. |
| Rendering | 60 FPS | Visual refresh, independent of simulation and decisions. |

Changing `--decision-seconds` does **not** slow cooking, deadlines, walking or collisions, and it never calls `advance(1)` as a replacement for twenty normal ticks. For the same unpaused wall duration, the same low-level input trace produces the same game state under 0.1 s and 1 s decisions. An agent that changes its behavior only once per second can produce a different result from an agent that decides ten times per second; that is the intended policy difference.

`--hz`, `--ticks`, the legacy `LocalGame.step()` API and normal startup remain supported. The CLI prints the timing configuration explicitly. The default human keyboard cadence remains 50 ms. `--demo` now invokes the existing reference policy at decision boundaries, so its cadence follows this setting.

Custom finite positive decision values up to 86400 seconds are accepted. Decision boundaries align to adapter ticks by rounding **up**. At 20 Hz, 0.075 becomes 0.1 s and 0.001 becomes 0.05 s; 0.25, 1 and 1.25 are exact. Both requested and effective values are recorded, and the CLI announces rounding. This avoids variable physics integration or fractional tick drift. With a custom legacy `--hz`, that adapter tick determines decision quantization; the engine still uses substeps at most 50 ms.

GUI pacing now retains wall-time backlog rather than silently discarding a stall beyond 250 ms. At most ten catch-up ticks run between renders/event pumps, so a slow machine can visibly lag before catching up. Pause/focus changes explicitly clear and record the remaining backlog and input buffers. Simulation and decision phase freeze while paused; an interrupted decision resumes with its remaining ticks rather than silently starting over.

## Windows examples

The current isolated environment already contains the dependencies. No activation, ExecutionPolicy or driver changes are needed.

```powershell
$chefRoot = 'D:\Desktop\IRL\ChefJeff'
$chefPython = "$chefRoot\.venv\Scripts\python.exe"

# GUI examples (original-art rendering and timing verified).
& $chefPython "$chefRoot\native_play.py" --decision-seconds 0.1
& $chefPython "$chefRoot\native_play.py" --decision-seconds 1
& $chefPython "$chefRoot\native_play.py" --decision-seconds 0.25 --level level-3

# The Windows launcher accepts the same arguments.
& "$chefRoot\start-native.bat" --decision-seconds 1 --art original

# Previous geometric rendering remains available.
& $chefPython "$chefRoot\native_play.py" --art simple --decision-seconds 0.1
```

CPU-only training/headless examples:

```powershell
& $chefPython "$chefRoot\native_play.py" --headless --steps 10 --decision-seconds 1 --no-record
& $chefPython "$chefRoot\native_play.py" --headless --steps 100 --decision-seconds 0.1 --no-record
& $chefPython "$chefRoot\native_play.py" --headless --ticks 200 --decision-seconds 1 --no-record
```

All three advance ten simulation seconds. Headless execution is unpaced and runs as fast as the CPU allows; GUI execution paces the same ticks to wall time. `--steps` counts decision windows; `--ticks` counts legacy adapter ticks. They are mutually exclusive. The previous default headless limit remains 3601 ticks. Source/resource paths remain relative to module locations, not the working directory.

## Training and agent interface

Run Python with `-X utf8` when importing the repository directly on Windows. None of these imports initializes or imports Pygame.

```python
from native.game import LocalGame
from native.timing import DecisionSession

game = LocalGame(seed=7, decision_seconds=1, record='new-training-round.jsonl')
session = DecisionSession(game)
try:
    # Commands are applied at the decision start, then normal physics ticks run.
    transition = session.step({
        'human': {'move': [1, -1]},
        'jeff': {'move': [0, 1]},
    })
    # transition contains decision_index, start/end ticks and times, duration,
    # money-delta reward, score, ended/interrupted, input_frames, raw events,
    # and the English engine state.

    # Movement persists if omitted. Explicitly release it with [0, 0].
    transition = session.step({
        'human': {'move': [0, 0]},
        'jeff': {'move': [0, 0]},
    })
    state = session.state()

    # Several actions or a key release inside one decision need a schedule.
    # These offsets are quantized upward to the same adapter tick grid.
    transition = session.step(
        {'human': {'move': [1, 0]}},
        schedules={'human': [
            {'offset': 0.1, 'command': {'move': [0, 0]}},
            {'offset': 0.2, 'command': {'hands': True}},
            {'offset': 0.3, 'command': {'use': True}},
        ]},
    )
finally:
    session.close()

# reset closes any partial old decision, creates a new episode and retains the
# existing config/timing unless overridden. Supply a NEW record path to log it.
result = session.reset(seed=7, decision_seconds=0.1)
session.close()
```

`session.advance_tick(actions, evidence=...)` is the real-time side of the same interface. It advances one adapter tick and returns `transition=None` until the current decision ends, then returns the same transition shape as `session.step()`. This is how keyboard frames remain live inside a one-second decision. A full decision is a sequence of frames, not one lossy boolean action.

`session.agent_port('jeff')` returns a boundary-queued `DecisionPort`. Its `observe()` reuses the existing `AgentPort.observe()` data and adds `native-decision-v1` timing. `submit(command, schedule=None)` queues for the next decision start. Submitting while a decision is active targets the following decision; a second unconsumed submission for that actor raises an error rather than replacing it. Legal action keys are resolved through the original `AgentPort` when applied, so stale/unavailable actions are refused and recorded. Existing `game.agent_port()` remains the immediate engine interface for compatibility; use `session.agent_port()` for a boundary-enforced agent. The existing `env-v1` contract was not changed.

If scheduled commands share an offset, they are executed in supplied order at that tick, with an outcome for each attempt. An event must fall strictly before the effective decision end; out-of-window events are rejected before gameplay starts. Commands for the two actors use the existing canonical `human`, then `jeff` order. If an agent command and a live keyboard command target the same actor/tick, scheduled commands run first and keyboard commands follow; the last movement vector wins and all attempts remain in the log. Prefer assigning each actor one controller.

## Input semantics and information loss

- Movement is held until changed or cleared. With no new input, existing movement/jobs continue; there is no implicit per-decision stop.
- Direction sampling still occurs every adapter tick, not once per decision. Held directions and very short taps are combined for one sample; opposite directions cancel. Diagonals are normalized by the original engine.
- A press/release completed between two samples produces at least one movement sample, matching the previous native behavior. Several directional changes within one 50 ms sample cannot retain their original physical durations; the raw observed key sequence/times are recorded rather than pretending they are exact physics. All such times are labelled observed, not hardware timestamps.
- Discrete button presses use a per-player FIFO. At most one button edge per player is applied per adapter tick; order and repeated presses are preserved across samples and decision boundaries. A quick three-tap Space sequence becomes three attempts, not one `hands=True`.
- A long button hold or OS repeat does not repeatedly activate it. A new release/press is required. Movement may be combined with a button in the same tick. Two different buttons queued together execute on successive ticks.
- Rapid interaction bursts can build a queue and delay later interactions. Each consumed edge has a sequence reference; queued counts and original down/up events are recorded. A button attempt that has no legal facing action is explicitly refused; no valid action is invented to satisfy it.
- Pause/focus loss clears held/short-tap state, queued keyboard edges, pending agent submissions, remaining scheduled actions and both engine movement vectors. Canceled buffers are recorded. Chopping/washing remain sticky under the original rules, but cannot progress while paused. Press P to resume. GUI pause-key OS repeats are ignored.

## Recording and old-file compatibility

New files use `chefjeff-native-v2`, adapter `1.1.1`. Header `timing` records requested/effective decision seconds, decision tick count, adapter seconds, engine maximum substep, rounding and sampling policy. Header `runtime` records render FPS, presentation choice and whether pacing is monotonic wall time or offline. Existing config/map/seeds, code identity, raw engine inputs/events, score/reward, checked state and provenance remain intact.

`decision_start` / `decision_end` rows record decision indices, exact tick/time bounds, target tick, duration, score/reward, end/interruption state. Tick rows include the actual command list, per-command `action_results` (including refusal reasons), and keyboard/wall evidence where provided. `control` rows retain submissions, pause/resume/focus changes, canceled buffers and clock resets. A partial last decision is explicitly ended with `interrupted=true` on close/reset.

Replay still uses the original `kitchen.apply_input`, checks exact applied input outcomes, raw engine events, simulation clock, state/provenance digests and money deltas, and now validates decision index/duration/boundary/reward metadata. It verifies engine-level results, not pixels. Keyboard timestamps and descriptive receipts are evidence, not a replacement for the engine input trace.

Schema-v1 files are never rewritten. They remain readable and reproducible with `--allow-code-change`, because the adapter fingerprint necessarily changed. This flag bypasses only the source identity guard: raw events, inputs, clock, scores and state/provenance are still checked. The original `sample-final-steak.jsonl` was replayed with all 413 events and score 500 matching; its bytes were checked unchanged.

```powershell
& $chefPython "$chefRoot\native_play.py" --replay "$chefRoot\native-recordings\visual-final\window-level-3-0.1.jsonl"
& $chefPython "$chefRoot\native_play.py" --replay "$chefRoot\native-recordings\visual-final\window-level-3-1.jsonl"
& $chefPython "$chefRoot\native_play.py" --replay "$chefRoot\native-recordings\sample-final-steak.jsonl" --allow-code-change
```

## Original art implementation

`native/art.py` reads the same 13 atlas manifests/PNGs, in the same prefix/override order, as `LevelOneArt.ts`. The resulting catalog contains 627 final frame keys. It validates PNG headers and all atlas rectangles without importing a GUI library. No original PNG, manifest, atlas, reference, animation metadata, Cocos source or map is altered, cropped on disk, regenerated or copied into a replacement resource pack.

The CPU-inspectable scene builder ports:

- Authored grid positions, 4x4 floor repeat, cutaway walls and map decorations.
- Cabinet run/device axes, cabinet north-edge depth and work-surface alignment, including the original 22-art-pixel cabinet lift.
- Boards, sources, directional serving windows, stove/pan contents, original prepared ingredient/dish frames and partial burger layer ordering.
- Sink/rack unit frame halves, rack plate slots/front wires and their per-cell layers.
- Human/robot identity, four directions, eight walking frames at the original 12 fps, idle and painted directional chop poses with the original 0.27 s beat. These animated sprites follow simulation time, so pause/decision settings do not change their clock.
- Directional carrying, back-facing item occlusion, throw-release/diagonal poses using metadata grips, original projectile images and ground/air depth.
- Original fire, steam, stove-flame, washing splash and dash-dust frames, plus plated order icons and the original ink/paper/denim/copper HUD palette. Held items retain the original-style overhead icon bubble for readability from the back.

`native/sprite_renderer.py` lazily loads/caches atlas crops and executes the plan on normal software Pygame surfaces, using nearest-neighbor proportional scaling, alpha bounds and Cocos-to-SDL anchor conversion. It is only imported by GUI startup. `--art original` is the new default; `--art simple` retains the previous geometric fallback. The presentation mode is printed and recorded. No GPU renderer flag, model or CUDA dependency is introduced.

The native screen retains its accessible English side panel/keyboard help rather than copying online model/account/research UI. The original web HUD is mostly procedural Cocos Graphics, so its palette and dish icons are reused in native UI. The original WOFF2 pixel font is not passed off as a supported Pygame font: native text currently uses the existing Pygame default font. Conversion or new font assets were not introduced.

Known art differences pending visual acceptance: exact browser HUD geometry/typeface; exterior garden/lighting composition; some mirrored tap details; advanced per-sprite knife/hand masks and chopping occlusion; wind-up/release easing and articulated throw timing; pick-up/landing feedback, smoke tinting, every plating-vessel orientation edge case, audio and menus. The renderer now selects knife-free bodies where supported, adds the original pre-drawn knife arc at its pose grip/pivot and paints the fist overlay above it. Source `knife_hidden` phases stay hidden. More complex masks/easing are not claimed pixel-identical to Cocos. Missing future item art is recorded in `SceneBuilder.missing`; custom-item fallback polish is deferred.

## Asset terms and attribution

The original asset notices remain at `THIRD_PARTY_NOTICES.md` and the integration/animation references at `docs/art/integration.md` and `docs/art/throw-diagonal-spec.md`. They describe project-generated art, user-supplied references and sprite assembly; asset/reference rights review remains part of the upstream release roadmap. This local reuse adds no new rights claim and does not describe the assets as public domain. Root original code remains under its existing AGPL license. The web engine's license is retained, though no Cocos runtime is used by the native renderer. Pygame and its default font retain their installed package notices. Audio files are unchanged and are not played by this port; their separate upstream terms remain applicable.

## Tests and remaining acceptance

```powershell
# CPU-only: these do not initialize SDL, decode/render images or open a window.
& $chefPython -X utf8 "$chefRoot\scripts\check_native.py"
Push-Location $chefRoot
& $chefPython -X utf8 -m unittest discover -s tests -p test_native_timing.py -v
& $chefPython -X utf8 -m unittest discover -s tests -p test_native_art.py -v
Pop-Location
```

Timing tests cover 0.1/1-second clock/state agreement, two actors, decision-boundary submission, scheduled release, no-input hold, short taps, repeated buttons, diagonals, queue clearing, pause pacing, reset/seeds, custom positive quantization, new replay and unchanged v1 replay. Art tests cover atlas precedence/rectangles, all four maps, anchors, direction/pose keys, held-item depth, vessel/dish/fire selection and read-only resources. These validate data/logic, not rendered pixels.

The resumed real-window acceptance command is:

```powershell
& $chefPython -X utf8 "$chefRoot\scripts\verify_native_visual.py" --output "$chefRoot\native-recordings\my-new-visual-check"
```

Use a new output folder to preserve existing recordings. This script rejects dummy SDL, checks real wall-clock pacing at both decision settings, sends explicitly synthetic SDL keyboard/pause/focus events, renders all maps and directional fixtures, runs complete cooking rounds and verifies their recordings. It saves a report, real-render PNG captures and an original-source atlas reference sheet. Snapshot-only pose fixtures are labelled and are not represented as gameplay episodes.

Completed visual evidence is in `native-recordings/visual-final/`, summarized in `native-verification-v1.1.1.md`. Still manual: physical keyboard/hardware rollover and a human-played complete GUI meal. The computer-use tool could inspect and close the real window, but its key injection produced no SDL key evidence, so hardware input is not claimed verified. Original browser HUD geometry/font, some exterior/decorative details and advanced animation easing/masks remain approximate.
