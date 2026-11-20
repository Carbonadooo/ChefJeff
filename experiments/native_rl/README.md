# Native ChefJeff Q-learning

This is an independent **reinforcement-learning** experiment: tabular Q-learning
starts with zero values and updates them from environment rewards and subsequent
states. It does not initialize from BC weights, collect expert action labels,
or invoke a scripted cook during inference. The human-side assembler remains a
fixed upstream script and is part of the training environment.

This first experiment is restricted to Level 1, full-state observations and a cook
role with high-level engine actions. It is not a pixel/keyboard policy, a PPO/DQN
implementation, IRL, HA2/FCP, or the official real-time benchmark.

## Install and train

Use the same Python 3.10-3.12 environment as the BC lab:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-learning.txt
& .\.venv\Scripts\python.exe -X utf8 experiments/native_rl/train.py --episodes 120 --out runs/native_rl/run-001
& .\.venv\Scripts\python.exe -X utf8 experiments/native_rl/play_agent.py --checkpoint runs/native_rl/run-001/policy.json --scripted-partner
```

An output directory must be new. `--seed` controls exploration/replay RNG, not a
learned checkpoint. Training environment seeds cycle over 0-31. Checkpoints are
selected only on validation seeds 80/81. Final evaluation uses seeds 200-203 after
selection, with BC and scripted baselines reported separately. Training uses virtual
game time without sleeping. GUI playback accepts `--speed 0.5` or `--speed 0.25`.
Different independent training seeds are needed for a research comparison.

## State and action abstraction

The observable tabular state describes the held item, pooled board stages, the stove/pan, assembly plate availability,
dirty plate availability and available action kinds. Older profile-1 checkpoints
retain per-station and partner-holding features; profile 2 pools stations, and
profile 3 additionally excludes tool actions from the cook role. Item IDs and absolute time are excluded. This is a lossy
fixed-map abstraction and may alias states that need different behavior.

The policy learns a choice among these available kinds:

```text
wait, fetch, put_board, chop, take_board, put_pot, lift_pot,
plate_counter, return_pot, wash, empty_pot
```

This is the explicit profile-3 role-constrained action space. Profile 1/2
also allowed take_tool/extinguish/put_tool; old checkpoints remain readable. The engine's first legal target
of the selected kind is used; target selection and primitive movement are not
learned. Navigation and persistent jobs are provided by the original engine.
There is no recipe-script fallback for the learned chef.

## Variable-duration transitions

The kitchen still advances in 50 ms simulation ticks. The partner is polled every
0.1 game seconds. An action option runs until the chef is idle at such a boundary;
`wait` lasts 0.5 game seconds. A transition contains its actual duration, reward,
next state, legal next actions and terminal flag. The TD bootstrap discount is
`gamma_per_second ** duration`, not a fixed discount for unequal-duration options.
Engine actions and 180-second episode rules are not changed.

## Reward and Q update

The base training reward is the game-money change divided by 50, discounted within
each action option. Evaluation reports original money and deliveries, not shaped
training returns. The default training discount is 0.97 per game second; lower-level environment
constructors retain their explicit parameter defaults for compatibility.

For exploration, a bounded inventory-progress potential adds:

```text
shaped_reward = base_reward + gamma^duration * Phi(next) - Phi(current)
target = shaped_reward + gamma^duration * max_legal Q(next)
Q(state, action) += alpha * (target - Q(state, action))
```

Terminal transitions have zero bootstrap and zero terminal potential. Phi uses
raw/chopped/cooking/ready/plated inventory progress, deduplicated by item identity
and capped at 4. This is handcrafted **training-side reward shaping**, not a new
engine scoring rule and not a learned reward model. Use `--no-shaping` for an
explicit sparse-reward ablation. It is not claimed that sparse rewards alone will
solve the task within the same small budget.

Exploration is epsilon-greedy; repeated off-policy updates use uniform experience
replay. An optional `--bellman-sweeps 2000` additionally fits empirical
Bellman expectations over collected reward transitions before validation; no
expert labels are involved. This model/replay planning remains subject to the
lossy state abstraction. `--epsilon-start` controls initial exploration.
The checkpoint contains actual learned Q values and the action-space and
training metadata. `policy.json` is the best validation checkpoint; training logs,
intermediate checkpoints, original-score validation curves and final baselines
are under the run folder and are ignored by Git.

## Deployment and verification

```powershell
# Once a checkpoint has been trained:
& .\.venv\Scripts\python.exe -X utf8 experiments/native_rl/play_agent.py --checkpoint runs/native_rl/run-001/policy.json --speed 0.25

# A complete rendered scripted-partner round and strict replay check:
& .\.venv\Scripts\python.exe -X utf8 experiments/native_rl/play_agent.py --checkpoint runs/native_rl/run-001/policy.json --scripted-partner --verify-render runs/native_rl/render-001

& .\.venv\Scripts\python.exe -X utf8 scripts/check_native.py
```

The render check requires real Windows SDL and uses unpaced presentation for its
long episode; it is not physical keyboard verification. Removing the scripted
partner enables P1 keyboard control, but human-partner performance is unvalidated.
The native JSONL replay validates the actual engine input/event/state trace.
Physical inputs and participant records are never synthesized as human data.


## Evaluated checkpoint (2026-11-20)

The included `checkpoints/level1-q.json` was selected after episode 60 of a
120-episode run (training RNG seed 0), by scores on validation seeds 80/81.
It starts from zero Q values and uses no BC weights or expert actor labels.
The default CLI settings reproduce this protocol: profile 3, alpha 0.15,
gamma 0.97 per game second, epsilon starting at 0.5 and 32 uniform replay updates
per transition. The optional Bellman sweeps are **not** used by this checkpoint.

```powershell
& .\.venv\Scripts\python.exe -X utf8 experiments/native_rl/play_agent.py --scripted-partner
```

It completed 10 dishes for score 500 on test seeds 200-203 and on a separate fresh
set 300-303. Original-score comparison on the fresh set, with the same partner:

| Chef policy | Mean original score | Mean deliveries |
| --- | ---: | ---: |
| Untrained zero-Q policy | -80 | 0 |
| Random within the same RL role action space | -80.5 | 0 |
| Upstream priority example | 450 | 9 |
| Scripted teacher | 500 | 10 |
| BC checkpoint | 500 | 10 |
| Reward-trained Q-learning checkpoint | 500 | 10 |

Five configurations totaling 700 training episodes were screened on validation
scores. Broad/overly detailed states and other replay settings often stalled or
cycled actions; these failures are included in `results/level1-smoke.json` rather
than omitted. Training returns with exploration can remain much worse than the
selected greedy checkpoint. Only one training RNG seed was used per configuration.
This small result does not establish convergence reliability or generalization.

The selected checkpoint was also reloaded for a complete original-art Windows SDL
round: score 500, 10 deliveries, and strict native engine replay passed. Local
records/screenshots stay under ignored run directories; no participant records or
video files are distributed with this experiment.
