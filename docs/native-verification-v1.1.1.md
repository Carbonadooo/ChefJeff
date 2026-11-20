# Native 1.1.1 final visual verification

The user explicitly authorized normal graphics tests to resume. This report supersedes the graphics-pause status in the historical v1.0/v1.1 reports. Original engine, web implementation, maps, recipes and atlas resources remain unchanged. Native code/art integration is version 1.1.1; recording schema remains `chefjeff-native-v2`.

## Final results

- Portable core/native suite: **345 tests, OK, 2 skipped** (49.887 s). This includes decision timing, legacy replay, input queues, all-map art coverage and the added knife-grip/washing regressions.
- Real Windows SDL driver: **windows**, not dummy. `scripts/check_native_window.py` passed after graphics testing resumed.
- The original-art native window was directly inspected with computer-use capture; characters, map, devices, HUD/tickets and live countdown were visible. The window closed cleanly through its own Close control.
- The resumed acceptance script rendered all four authored maps and four directional chop fixtures, then complete recipe rounds. It saved real rendered client-frame PNGs, exact local recordings, a source-atlas reference sheet and JSON reports. Pose fixtures are explicitly labelled and are not represented as engine episodes.
- Final 0.1-second pacing: **2.0091 s wall time -> 2.0000 s simulation, 40 internal ticks, 20 decisions**, 121 rendered frames.
- Final 1-second pacing: **2.0085 s wall time -> 2.0000 s simulation, 40 internal ticks, 2 decisions**, 121 rendered frames.
- Real-event-queue synthetic SDL tests passed for both players, diagonal movement, release, pause/resume, queued-button clearing and focus loss. Engine/state/score/provenance replay checks passed for every completed visual round.
- Byte compilation, new-source marker/trailing-whitespace checks and `git diff --check` passed. The only modified original tracked file is `.gitignore`; native implementation/documentation/test files are additive and uncommitted. No commit/push/reset/clean or unrelated process termination was performed.

## Complete rendered rounds

Long rounds run unpaced for acceptance while a real window is rendered every ten ticks and at new key states. The separate wall-clock tests above verify normal 60 FPS pacing; the long rounds are not represented as three minutes of physical keyboard play. All completed rounds reached the original 180-second end.

| Level | Seed | Decision interval | Simulation | Ticks | Decisions checked | Score | Served | Raw events checked | Replay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| level-3 | 7 | 0.1 s | 180 s | 3600 | 1800 | 413 | 6 | 387 | verified |
| level-3 | 7 | 1 s | 180 s | 3600 | 180 | 330 | 5 | 296 | verified |
| level-4 | 0 | 0.1 s | 180 s | 3600 | 1800 | 150 | 3 | 353 | verified |
| level-4 | 7 | 0.1 s | 180 s | 3600 | 1800 | -60 | 0 | 91 | verified |

The mixed-recipe Level 3 trace served four burgers plus two steaks at 0.1 s, and three burgers plus two steaks at 1 s. The difference in score reflects policy decisions at different cadences, not a change in physics or wall-clock game speed. The identical-low-level-input parity tests remain part of the passing timing suite.

The split-map seed-7 reference-policy round exercised throws, catches, chopping, cooking and held pans but completed no deliveries; its negative score and exact trace are retained, not omitted or repaired by changing rules. The normal default seed-0 round separately completed three deliveries for 150, including actual throwing, preparation, cooking, plating, service and fire. This scripted trace driver is not promised to solve every seed, and no new AI policy was substituted.

## Visual inspection and fixes

Original atlas pixels and manifest anchors were compared against real native output. The source reference sheet and captures are in the evidence folders below. No source images/manifests were redrawn, regenerated or modified.

Inspected: human/robot proportions and directions; floor/counter/wall alignment; sink/rack halves; ingredient and plated-burger art; carried pans and plates; ready/steam, fire/smoke, throws/catches; order icons, count/score/deadline displays and paused presentation. The full recipe traces produced real gameplay-state captures; snapshot-only direction fixtures are labelled separately.

The final pass completed the source's knife-free body + original arc/pivot/grip layer + hand overlay where metadata supports it. Source `knife_hidden` strike phases remain hidden. It also added washing splashes and original-style overhead held-item bubbles, making carried items readable behind back-facing bodies. These are presentation-only changes; engine inputs and results replay exactly.

## Evidence and reproduction

- `native-recordings/visual-final/report.json`: final mixed-recipe timing/input/round report.
- `native-recordings/visual-final/original-atlas-reference.png`: original source frame crops; source files unchanged.
- `native-recordings/visual-final/level-3-0.1-plated.png`: actual carried assembled burger and held-item bubble.
- `native-recordings/visual-final/level-3-0.1-fire.png`: actual fire/ready/cooking scene.
- `native-recordings/visual-final/chop-fixture-{up,down,left,right}.png`: labelled pose fixtures.
- `native-recordings/visual-final/level-{1,2,3,4}-layout.png`: rendered authored layouts.
- `native-recordings/visual-split-seed0/report.json`: successful split-kitchen acceptance.
- `native-recordings/visual-split-seed0/level-4-0.1-served.png`: actual split-map service/score change.
- `native-recordings/visual-split-final/level-4-0.1-caught.png`: actual catch in the retained seed-7 trace.

All generated evidence stays local under the ignored `native-recordings/` directory. Existing logs were retained. Use a new output folder when reproducing; the script rejects a nonempty destination before initializing SDL.

```powershell
$chefRoot = 'D:\Desktop\IRL\ChefJeff'
$chefPython = "$chefRoot\.venv\Scripts\python.exe"

# Normal native play, original art. Change 0.1 to 1 for one-second decisions.
& $chefPython "$chefRoot\native_play.py" --decision-seconds 0.1
& "$chefRoot\start-native.bat" --decision-seconds 1

# Current-version exact replays (no GUI).
& $chefPython "$chefRoot\native_play.py" --replay "$chefRoot\native-recordings\visual-final\window-level-3-0.1.jsonl"
& $chefPython "$chefRoot\native_play.py" --replay "$chefRoot\native-recordings\visual-final\window-level-3-1.jsonl"
& $chefPython "$chefRoot\native_play.py" --replay "$chefRoot\native-recordings\visual-split-seed0\window-level-4-0.1.jsonl"

# CPU and real-window checks. Choose unused output folder names.
& $chefPython -X utf8 "$chefRoot\scripts\check_native.py"
& $chefPython -X utf8 "$chefRoot\scripts\verify_native_visual.py" --output "$chefRoot\native-recordings\new-visual-run"
& $chefPython -X utf8 "$chefRoot\scripts\verify_native_visual.py" --output "$chefRoot\native-recordings\new-split-run" --split-only --seed 0
```

`requirements-native.txt` remains unchanged (Pygame 2.6.1); the existing venv is ready. See `native-decision-art.md` for custom-step quantization, the training/agent API, full recording schema and asset attribution. Older source fingerprints still require `--allow-code-change`; that only bypasses source identity, not event/state/score checks.

## Remaining limits

Physical keyboard/hardware rollover and a complete human-played GUI meal are **not claimed verified**. The computer-use tool could inspect and close the real window, but its injected P key did not reach SDL: the corresponding normal-play journal contained zero raw keyboard events. The real SDL event-queue tests passed, and this delivery distinction is retained explicitly.

The original browser's precise HUD layout/typeface, exterior garden/lighting and some advanced masking/easing/feedback/audio/menu details are not pixel-identical. The native side panel remains English and exposes the preserved engine actions/recipes. No screenshot pixel-equality or full Cocos UI clone is claimed. Asset terms/rights review remain as described in the unchanged upstream notices; this update grants no additional asset rights.

The earlier broad upstream Linux/web suite failures are documented in the historical report. This iteration did not change those services or claim that the entire upstream suite passes on Windows. All owned test windows were closed at completion.
