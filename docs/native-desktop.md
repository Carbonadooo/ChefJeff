# ChefJeff native Windows desktop

> Native 1.2 adds uniform slow play with `--speed 0.5` or `--speed 0.25`. Default speed is 1. Tick and decision intervals remain in game seconds. See [game speed and recording semantics](native-speed.md).

> Update: native 1.1 adds `--decision-seconds`, schema-v2 recordings and original atlas art. See [decision timing and original art](native-decision-art.md) for current semantics and commands. The earlier implementation details below describe v1.0 where they differ. Graphics tests have resumed and original-art real-window acceptance is recorded in [native-verification-v1.1.1.md](native-verification-v1.1.1.md). The earlier report below covers v1.0 where noted.

This is an additive, offline Python port of the existing ChefJeff kitchen. Run one Python command to open a native Pygame window. It requires no browser, HTTP/WebSocket service, Cocos Creator, model account/key, online LLM, GPU, WSL or Docker. The original web implementation and game-rule files are unchanged.

## Start on this computer

The isolated environment has already been created using Python 3.12.11 at `C:\Users\Shaoyu\miniforge3\python.exe`. No environment activation or ExecutionPolicy change is needed.

```powershell
$chefRoot = 'D:\Desktop\IRL\ChefJeff'
& "$chefRoot\.venv\Scripts\python.exe" "$chefRoot\native_play.py"
```

Or double-click `start-native.bat`. To select another authored map:

```powershell
& "$chefRoot\.venv\Scripts\python.exe" "$chefRoot\native_play.py" --level level-3 --seed 0
& "$chefRoot\.venv\Scripts\python.exe" "$chefRoot\native_play.py" --level level-4 --seed 0
```

All resource paths are resolved from source locations. These commands also work from another directory and with spaces in the repository path. Custom `--record` paths are resolved relative to the invoking directory. Default recordings go into `native-recordings/` beside the entrypoint.

For a fresh environment on Windows with a compatible Python 3.10–3.12 installation:

```powershell
$chefRoot = 'D:\Desktop\IRL\ChefJeff'
& 'C:\Users\Shaoyu\miniforge3\python.exe' -m venv "$chefRoot\.venv"
& "$chefRoot\.venv\Scripts\python.exe" -m pip install -r "$chefRoot\requirements-native.txt"
```

The only additional gameplay dependency is `pygame==2.6.1`. The local test environment also has the repository's pinned NumPy/Pillow test dependencies. The entrypoint re-executes itself in UTF-8 mode when necessary because upstream `model_language.py` reads a UTF-8 catalog with a locale-default `read_text()`. This compatibility fix is process-local and changes no original file or system setting.

## Two players and controls

Canonical engine actor IDs remain `human` (P1) and `jeff` (P2). Both use the original collision, orientation, movement, item and action rules.

| Control | Player 1 | Player 2 |
|---|---|---|
| Move, including diagonals | WASD | Arrow keys |
| Hands: take, put, plate, serve | Space | Enter |
| Use: chop, wash, extinguish; otherwise throw | E | Right Ctrl |
| Throw in current aim direction | Q | Right Shift |
| Dash while moving | Left Shift | `/` |
| Stop current action | X | `.` |

`P` pauses/resumes. `Esc` or the window Close button saves and closes the episode. Focus loss clears held and queued keys, sends zero movement for both chefs, and pauses; press P after returning. Discrete actions fire once per press, while movement persists until release. Very short movement taps are retained until one simulation sample. Opposite directions cancel. Work is sticky until movement or Stop, matching the engine's existing behavior; releasing E does not cancel chopping.

The board highlights the station selected by the engine. The side panel lists the current Hands/Use actions, held objects, tasks, recipes and order deadlines. Food color/state labels distinguish raw, chopped, cooking, ready and burnt. Ready food is green. Heating has an orange progress bar. Fire changes the station color. All art is native geometric placeholder rendering; no third-party game art was copied.

First steak: face the beef source, take beef, put it on a board, press Use to chop, take it, load the pan, wait until ready, take a clean plate, plate from the pan and serve at the green serving window. Use the displayed action hints when holding pans/plates or sharing work. The authored burger requires its original additional components and assembly. Recipes and required stages are displayed from the engine catalog.

## Optional scripted demonstration and agents

```powershell
& "$chefRoot\.venv\Scripts\python.exe" "$chefRoot\native_play.py" --demo
```

`--demo` drives both chefs with the existing `reference_policy.choose` / `choose_zoned` trace driver, including the original runner/maker roles on the split floor. It is a recipe regression demonstration, not an AI teammate or benchmark baseline. It never calls a model.

Future agents can use the existing `environment.Agent` lifecycle and `game.agent_port(actor)`, which returns the original `AgentPort` with English observations, legal actions, event history, guarded action requests and a read-only view. Run the agent on the simulation thread; avoid blocking work inside `poll`. Agent calls enter the same engine input recording as keyboard calls.

## Headless reset / step / state

Use `-X utf8` for direct library imports on Windows. No GUI module is imported by `native.game`, and headless use needs only the standard library and the existing repository source.

```python
from native.game import LocalGame

game = LocalGame(level='level-3', seed=7, record='my-new-round.jsonl')
try:
    game.step({'human': {'move': [1, -1]}, 'jeff': {'move': [0, 1]}})
    game.step({'human': {'move': [0, 0]}, 'jeff': {'move': [0, 0]}})
    state = game.state()                 # English engine snapshot
    port = game.agent_port('jeff')       # existing env-v1 contract
    actions = port.observe()['actions']
    if actions:
        port.act(actions[0]['key'])
    result = game.step()
    # result: tick/time/score/reward/ended/events/state_sha256
finally:
    game.close()

# reset() creates a new episode; supply a new record path to record it.
game.reset(level='level-1', seed=0)
game.close()
```

A movement vector remains active until changed to `[0,0]`. `hands`, `use`, `throw`, `sprint`, `stop` are discrete boolean requests; `action_key` uses the current engine legal-action list. Calls are applied in canonical human/jeff order and advanced on one thread. Do not mutate `game.k` to control an agent: direct state edits bypass the engine input log and replay should detect them.

The default simulation step is **50 ms / 20 Hz**, aligned with `docs/architecture/session-record.md` and `Kitchen.advance`'s maximum 50 ms substeps. Rendering defaults to 60 FPS and cannot change the step size. `--hz` and `--fps` are separate options. Long render stalls discard excess wall time beyond 250 ms rather than issuing a burst of stale input. Paused time never advances the simulation.

## Recording and replay

Local recording is enabled by default. Each JSONL file is created exclusively, flushed after every simulation boundary and retained locally; an existing file is never overwritten. Use `--no-record` to disable recording. No logs or data are uploaded.

```powershell
& "$chefRoot\.venv\Scripts\python.exe" "$chefRoot\native_play.py" --headless --demo --seed 0 --record "$chefRoot\native-recordings\new-sample.jsonl"
& "$chefRoot\.venv\Scripts\python.exe" "$chefRoot\native_play.py" --replay "$chefRoot\native-recordings\new-sample.jsonl"
```

Verified delivery samples are `native-recordings/sample-final-steak.jsonl` and `native-recordings/sample-final-split.jsonl`. Older development logs are preserved separately and may have older code fingerprints.

Header fields: `schema_version` (`chefjeff-native-v1`), `adapter_version`, `code_sha256`, `episode_id`, `started_at`, Python/platform, engine class, `hz`, full `resolved_config` (including map, recipes, rules, config hash and order/spawn seeds), and initial state digest.

Each tick/final row carries `tick`, `simulation_time`, `requested_actions`, the exact original `inputs` including accepted/refused outcomes and bound action objects, raw engine `events`, `score`, money-delta `reward`, `state_sha256` and `end_reason`. The final row also carries the checked engine state and raw `provenance`: action IDs, actors, item touches, merges, container histories, served dishes and penalties. Existing Chinese strings inside raw engine event evidence are preserved verbatim; UI/adapter/docs are English. No cooperation score is invented.

Replay uses **the original `kitchen.apply_input`**, not a second implementation of the rules. It rebuilds a new `SpatialKitchen` from the frozen config and checks each recorded input outcome, raw event sequence/content, simulation clock, score/reward and state digest. The state projection reuses `research_record.state` and adds orientation/aim, full orders, stacked plates, sprint state and raw provenance. The final serialized state must also agree. Truncated sessions without a final row are reported incomplete; changed events/state/scores fail. The code fingerprint is checked by default; `--allow-code-change` only permits diagnostic replay under different source, and still checks all state/events.

This small native envelope is deliberately separate from `SessionLog`/hosted research bundles, whose session construction imports web/server/model infrastructure. It reuses their engine input protocol, research state projection and provenance rather than duplicating those mechanisms. It does not claim compatibility with the hosted contribution upload schema. Replay verifies game results and raw evidence, **not pixel-identical rendering** or an agent's internal reasoning.

## Verification commands

```powershell
& "$chefRoot\.venv\Scripts\python.exe" -m pip install -r "$chefRoot\tests\requirements.txt"
& "$chefRoot\.venv\Scripts\python.exe" -X utf8 "$chefRoot\scripts\check_native.py"
& "$chefRoot\.venv\Scripts\python.exe" -X utf8 "$chefRoot\scripts\check_native_window.py"
```

The first runner covers the focused native suite and portable original engine tests. The second requires a real Windows display/SDL driver, renders a real window and checks synthetic keydown/keyup, two-player diagonal input and focus-loss handling. It rejects SDL's dummy driver. Synthetic event checks do not claim physical keyboard validation.

The repository-required broader checks remain:

```powershell
Push-Location $chefRoot
$env:PYTHONUTF8 = '1'
$env:CHEFJEFF_LOG_DIR = Join-Path $env:TEMP 'chefjeff-native-tests'
& "$chefRoot\.venv\Scripts\python.exe" -X utf8 -m unittest discover -s tests
node tests\hosted_browser_test.cjs
$env:PATH = 'C:\Program Files\Git\cmd;' + $env:PATH
& "$chefRoot\.venv\Scripts\python.exe" -X utf8 scripts\audit_release.py
& 'C:\Program Files\Git\cmd\git.exe' diff --check
Pop-Location
```

These environment variables affect only that PowerShell process. The original full suite includes Linux deployment/web tests and does not currently pass on this Windows checkout. See `native-verification.md` for actual results and limits; no system configuration was changed to make unrelated tests pass.

## Manual keyboard check still needed

1. Launch normal play, click the canvas, hold/release WASD, then hold W+D and verify diagonal motion and collision.
2. Repeat with P2 arrow keys while P1 moves; verify independent facing and release.
3. Fetch/chop/cook/plate/serve using the listed keys and watch the score/order change.
4. Hold a movement key, switch away, release it, return and press P; the chef should remain stopped.
5. Press P twice to verify pause/resume, then close and run `--replay` on the printed log path.

A real window was inspected using computer-use screenshots, including live countdown and expiry penalties. The UI automation tool's key injections did not appear in the SDL input journal, so physical keyboard and simultaneous hardware-key rollover remain unverified. The adapter and real-SDL synthetic input tests passed.

## Scope and file layout

- `native/game.py`: headless adapter, fixed steps, checked state, local recorder, engine replay.
- `native/controls.py`: held/released/edge key state, independent of GUI imports.
- `native/window.py`: Pygame renderer, event handling, pause/focus loop.
- `native/policy.py`: explicitly labelled existing reference demo; `native/__init__.py`: adapter version.
- `native_play.py`, `start-native.bat`, `requirements-native.txt`: launch/install surface.
- `tests/test_native_desktop.py`, `scripts/check_native.py`, `scripts/check_native_window.py`: regression and real-display checks.
- `.gitignore`: native venv and generated local evidence exclusions.

Preserved: all four authored maps; navigation and collision; shared counters/items/work; pots/plates and their reuse; throws/catches; processing/cooking/burning/fire/extinguishing; ingredient assembly and multiple recipes; order arrivals, countdown, expiry, scoring and end rules; original action binding, agent port and raw provenance.

Deferred presentation/product work: Cocos sprites/animations/audio, gamepad/mobile UI, a level picker/restart menu, polished asset import, packaged executable/installer, graphical replay transport, online sessions, model integration and hosted research/contribution workflows. Replay is a headless verifier. The original repository license remains applicable; original shapes are drawn by this adapter, while Pygame and its bundled font/runtime retain their package notices. Nothing was committed or pushed, and unrelated IRL projects were untouched.
