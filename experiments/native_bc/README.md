# Native ChefJeff learning lab

This optional experiment trains a small weighted CART policy by behavioral cloning
of the upstream recipe-following script. It is a functional learning/inference test,
not a PPO/DQN trainer, IRL, human behavior model, HA2/FCP reproduction, or official
Benchmark v3 result. No model API, API key, GPU or online service is used.

## Install

Use Python 3.10-3.12. From the repository root on Windows PowerShell:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-learning.txt
& .\.venv\Scripts\python.exe -X utf8 native_play.py --hz 20 --speed 0.25
```

On Linux/macOS, use `python3 -m venv .venv`, then the environment's `bin/python`.
GUI play needs a display; training is headless and uses the standard library plus
NumPy. Pygame is required only for the native display. Do not copy a Windows venv
to another computer; recreate it from the requirements.

## Run the included learned policy

```powershell
# Watch learned Jeff with the fixed scripted human partner.
& .\.venv\Scripts\python.exe -X utf8 experiments/native_bc/play_agent.py --scripted-partner

# Play P1 yourself, with more reaction time. Jeff uses the learned checkpoint.
& .\.venv\Scripts\python.exe -X utf8 experiments/native_bc/play_agent.py --speed 0.25
```

The checkpoint is `experiments/native_bc/checkpoints/level1-tree-bc.json`. Jeff is
trained as the **cook** (beef preparation, cooking and transfer to the assembly
plate); the training partner is the original scripted **assembler**. In human play,
P1 uses WASD/Space/E and helps with plates and service. This policy has not been
validated with human partners or outside Level 1. P2 keyboard commands are filtered
so they cannot override the learned actor.

`--speed 1`, `0.5` and `0.25` mean normal, half and quarter game speed. Keep `--hz 20`:
50 ms is still advanced per game-time tick. At quarter speed this tick takes 200 ms
of unpaused wall time. Decisions and scheduled offsets remain in game seconds.
Changing Hz alone does not slow the kitchen. See [speed semantics](../../docs/native-speed.md).

## Train from scratch

Choose a new output directory; existing directories are rejected:

```powershell
& .\.venv\Scripts\python.exe -X utf8 experiments/native_bc/experiment.py --out runs/native_bc/run-001
& .\.venv\Scripts\python.exe -X utf8 experiments/native_bc/play_agent.py --checkpoint runs/native_bc/run-001/policy.json --scripted-partner
```

The script collects four full teacher rounds, fits weighted CART, performs two
learner-state expert-label aggregation rounds, and selects the checkpoint on two
validation seeds. It evaluates idle, random, the upstream priority example, the
teacher and the selected model on four held-out test seeds only after selection.
The raw data keeps waiting decisions; the training loss gives wait labels weight
0.2. Waiting while cooking is meaningful and is not removed from the source data.

Outputs include compressed labeled observations, numerical training data,
intermediate checkpoints, the selected `policy.json`, a detailed `report.json`,
and one engine-replay-verified evaluation recording. `runs/` is ignored by Git.
No original recordings, participant data, credentials or video files are published.

## What is observed and executed?

- Actor: Jeff. Partner: the fixed upstream assembler script controlling Human.
- Observation: public `env-v1` structured full state and the current legal-action list.
- Actions: high-level legal engine actions such as fetching, chopping and loading a
  pan. The engine handles navigation and persistent work; this is not a primitive
  keyboard policy or vision policy.
- Integration: 50 ms game-time ticks; action decisions every 0.1 game seconds.
- Inference: `policy.py` uses checkpoint tree parameters and legal-action masking;
  it does not call the teacher or substitute a scripted cook when uncertain.
- Training/evaluation: unpaced virtual time. GUI playback uses wall-clock pacing.
  This is not comparable to the official real-time benchmark protocol.

## Recorded smoke-test result

The selected initial BC checkpoint used 3,945 decisions from seeds 0-3. Two further
aggregation stages did not improve validation return, so the first checkpoint was
retained. Validation seeds: 40 and 41. Test seeds: 100-103. Every episode lasts the
original 180 game seconds with the same fixed partner.

| Actor policy | Mean team score | Mean deliveries |
| --- | ---: | ---: |
| Idle | -80 | 0 |
| Random legal actions | -80.5 | 0 |
| Upstream priority example | 450 | 9 |
| Scripted teacher | 500 | 10 |
| Learned BC checkpoint | 500 | 10 |

See `results/level1-smoke.json`. This small fixed-map test does not establish
cross-map, cross-recipe or unfamiliar-human generalization. The script-generated
demonstrations are not human proxies. The learned policy is not an RL baseline.

## Files and extension points

| File | Role |
| --- | --- |
| `policy.py` | Observation encoding, checkpoint inference and `environment.Agent` wrapper |
| `experiment.py` | Teacher data, CART fitting, aggregation and held-out evaluation |
| `play_agent.py` | Native keyboard/agent assignment, GUI play and render verification |
| `checkpoints/` | Small reviewed synthetic-data checkpoint |
| `results/` | Sanitized smoke-test result; no local paths or participant data |

For a different policy, implement the agent interface and route its commands through
the engine ports; do not mutate the kitchen state. Boundary-queued command plans
also exist in `native/timing.py`. This example invokes the immediate engine port
at decision boundaries. A future low-level action policy needs an explicit action
encoding and evaluation protocol before comparing it to human keyboard traces.

## Checks and replay

```powershell
& .\.venv\Scripts\python.exe -m pip install -r tests/requirements.txt
& .\.venv\Scripts\python.exe -X utf8 scripts/check_native.py
& .\.venv\Scripts\python.exe -X utf8 native_play.py --replay runs/native_bc/run-001/learned-evaluation.jsonl
```

The portable runner covers native/core checks; it does not claim that all upstream
Linux/web deployment checks pass on Windows. Optional historic recording fixtures
are not distributed and their tests skip when absent. Native strict replay guards
the source fingerprint; recordings from older code may need `--allow-code-change`,
which bypasses identity only and still checks inputs, events, state and score.
Physical keyboard rollover and a human-played meal remain manual checks.

Original project code remains under the root AGPL-3.0-only license. Existing
third-party and asset notices remain applicable; see `LICENSE` and
`THIRD_PARTY_NOTICES.md`. This experiment does not add any new asset rights.
