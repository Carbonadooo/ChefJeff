# Native 1.2: uniform game speed

`--speed` sets simulation seconds per unpaused wall second. The default is 1.
Values must be finite, greater than 0 and at most 1. Use 0.5 for half speed or
0.25 for quarter speed. This setting slows the whole kitchen uniformly: movement,
work, heating, fire, projectiles, orders, deadlines and the round clock. Game-rule
durations, recipes, physics, reward and the agent action contract are unchanged.

```powershell
$chefRoot = 'D:\Desktop\IRL\ChefJeff'
& "$chefRoot\start-native.bat" --hz 20 --speed 0.25 --decision-seconds 0.1
& "$chefRoot\start-native.bat" --hz 20 --speed 0.5 --decision-seconds 1
```

At the default 20 Hz, each adapter tick still advances 50 ms of game time.
At speed 0.25, this tick becomes due after 200 ms of unpaused wall time. A
180-game-second round therefore takes about 12 real minutes, excluding pauses
and resource loading. At speed 0.5 it takes about 6 minutes. Rendering and event
pumping retain the requested FPS; sprite positions still update at simulation
ticks, so slow play is not a claim of interpolated 60 FPS movement.

`--hz` changes the adapter step, not the game speed. Keep `--hz 20` for normal
50 ms game-time input/physics steps. All `--decision-seconds` values and scheduled
command offsets remain game seconds: at speed 0.25, a 0.1-second decision spans
0.4 real seconds, and a 1-second decision spans 4 real seconds. Changing speed
alone does not change the number of simulation ticks or decisions in a full round.

Keyboard events continue to be collected every render/event pump. Buttons retain
the per-player FIFO, including multiple presses between ticks and across decision
boundaries. A maximum of one button edge per actor is applied per simulation tick;
slow play also increases its wall-time queue delay. Movement is sampled at tick
boundaries and retains the existing short-tap rules. Several direction changes
between two ticks do not preserve their exact physical durations; raw observed
key events and their real-time timestamps remain available as evidence. Pause
and focus loss clear input/backlog as before. Paused time never advances the game.

New CLI recording headers include `runtime.game_speed`, `speed_timebase` and
`decision_timebase`; tick evidence keeps real `active_wall_seconds`, the speed,
and observed keyboard events. Clock-reset backlog amounts are simulation seconds,
explicitly labelled in new reset records. The JSONL schema stays
`chefjeff-native-v2`; the native adapter version is 1.2.0. A transition still
contains all input frames, not just the final button. Slow play does not remove
idle samples, and study data collected at different speeds must keep that condition.

Replay checks the recorded game-time trace without wall-clock delays. Older files
are never rewritten; after this source change they may require the existing
`--allow-code-change` option, which bypasses source identity only. Events, inputs,
state, score and decision boundaries remain checked. Old runtime headers without
`game_speed` continue to mean normal speed when used by the window loop.

`--speed` is a real-time GUI option. Combining a non-default speed with
`--headless` is rejected because offline execution is unpaced. The immediate
`LocalGame` and `DecisionSession` stepping APIs remain unpaced and game-time based.

Manual acceptance: run quarter speed, verify that one countdown second takes
about four real seconds, move both chefs, prepare a dish, pause/resume, switch
focus while holding a direction, and verify the new recording after closing.
No physical-keyboard success is implied by synthetic-event or CPU tests.
