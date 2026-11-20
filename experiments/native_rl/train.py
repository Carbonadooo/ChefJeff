"""Train reward-only Q-learning from zero values, then evaluate on held-out seeds."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from experiments.native_rl.env import CookingEnv, rollout
from experiments.native_rl.q_policy import QPolicy

VALIDATION = (80, 81)
TEST = (200, 201, 202, 203)


def update(policy, transition, alpha):
    current = policy.values(transition['state'])
    next_values = policy.values(transition['next_state'])
    bootstrap = 0.0 if transition['ended'] else max(next_values[index] for index in transition['next_actions'])
    target = transition['reward'] + transition['discount'] * bootstrap
    error = target - current[transition['action']]
    current[transition['action']] += alpha * error
    return float(error)


def batch_update(policy, memory, sweeps):
    """Fit Bellman expectations over reward transitions, without expert labels."""
    states = sorted({row[key] for row in memory for key in ('state', 'next_state')})
    ids = {key: index for index, key in enumerate(states)}
    width = len(next(iter(policy.q.values())))
    matrix = np.array([policy.values(key).copy() for key in states])
    mask = np.zeros_like(matrix, dtype=bool)
    for row in memory:
        mask[ids[row['state']], json.loads(row['state'])[-1]] = True
        mask[ids[row['next_state']], list(row['next_actions'])] = True
    indices = np.array([ids[row['state']] * width + row['action'] for row in memory])
    following = np.array([ids[row['next_state']] for row in memory])
    rewards = np.array([row['reward'] for row in memory])
    discounts = np.array([0 if row['ended'] else row['discount'] for row in memory])
    counts = np.bincount(indices, minlength=matrix.size)
    observed = counts > 0
    completed = 0
    for _ in range(sweeps):
        maximum = np.max(np.where(mask, matrix, -np.inf), axis=1)
        maximum[~np.any(mask, axis=1)] = 0
        targets = rewards + discounts * maximum[following]
        totals = np.bincount(indices, weights=targets, minlength=matrix.size)
        flat = matrix.ravel()
        replacement = totals[observed] / counts[observed]
        delta = float(np.max(np.abs(flat[observed] - replacement)))
        flat[observed] = replacement
        completed += 1
        if delta < 1e-7:
            break
    for index, key in enumerate(states):
        policy.q[key] = matrix[index].copy()
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--episodes', type=int, default=120)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--eval-every', type=int, default=20)
    parser.add_argument('--replay-updates', type=int, default=32)
    parser.add_argument('--bellman-sweeps', type=int, default=0)
    parser.add_argument('--alpha', type=float, default=0.15)
    parser.add_argument('--gamma-per-second', type=float, default=0.97)
    parser.add_argument('--epsilon-start', type=float, default=0.5)
    parser.add_argument('--no-shaping', action='store_true')
    args = parser.parse_args()
    if args.episodes < 1 or args.eval_every < 1 or args.replay_updates < 0 or args.bellman_sweeps < 0 or not 0 <= args.epsilon_start <= 1 or not 0 < args.alpha <= 1 or not 0 < args.gamma_per_second <= 1:
        parser.error('Episodes/evaluation interval must be positive; alpha/gamma must be in (0,1].')
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    rng = np.random.default_rng(args.seed)
    policy = QPolicy()
    initial = [rollout(policy, seed) for seed in VALIDATION]
    memory = deque(maxlen=50000)
    best = -float('inf')
    best_path = None
    evaluations = []
    with (args.out / 'training.jsonl').open('x', encoding='utf-8') as log:
        for episode in range(args.episodes):
            env = CookingEnv(episode % 32, args.gamma_per_second, shaping=not args.no_shaping, state_version=policy.state_version)
            epsilon = max(0.05, args.epsilon_start * (1 - episode / max(1, args.episodes * 0.8)))
            reward = error = 0.0
            while not env.k.ended:
                index, _ = policy.action(env.seen, rng, epsilon, random_ties=True)
                transition = env.step(index)
                memory.append(transition)
                error += abs(update(policy, transition, args.alpha))
                for _ in range(min(args.replay_updates, len(memory))):
                    update(policy, memory[int(rng.integers(len(memory)))], args.alpha)
                reward += transition['reward']
            row = {'episode': episode + 1, 'seed': episode % 32, 'score': env.k.money,
                   'served': env.k.served, 'epsilon': epsilon, 'decisions': env.decisions,
                   'shaped_return': reward, 'absolute_td_error': error,
                   'states': len(policy.q), 'elapsed_seconds': time.perf_counter() - started}
            log.write(json.dumps(row) + '\n')
            log.flush()
            if (episode + 1) % args.eval_every == 0 or episode + 1 == args.episodes:
                planned = batch_update(policy, list(memory), args.bellman_sweeps) if args.bellman_sweeps else 0
                checked = [rollout(policy, seed) for seed in VALIDATION]
                score = float(np.mean([item['score'] for item in checked]))
                evaluation = {'episode': episode + 1, 'bellman_sweeps': planned, 'mean_score': score, 'rounds': checked,
                              'training_last': row}
                evaluations.append(evaluation)
                print(json.dumps({'validation': evaluation}), flush=True)
                if score > best:
                    best = score
                    best_path = args.out / f'checkpoint-{episode + 1}.json'
                    policy.save(best_path, training_seed=args.seed, episodes=episode + 1,
                                planned_episodes=args.episodes, alpha=args.alpha,
                                epsilon_start=args.epsilon_start, replay_updates=args.replay_updates,
                                eval_every=args.eval_every, bellman_sweeps=args.bellman_sweeps,
                                gamma_per_second=args.gamma_per_second, shaping=not args.no_shaping,
                                initialization='zero Q values; no BC or expert labels',
                                training_seeds=list(range(32)), validation_seeds=list(VALIDATION))
    selected = QPolicy(best_path)
    test = [rollout(selected, seed) for seed in TEST]
    from experiments.native_bc.experiment import episode as bc_episode
    from experiments.native_bc.policy import TreePolicy
    bc = TreePolicy(ROOT / 'experiments/native_bc/checkpoints/level1-tree-bc.json')
    baselines = {name: [bc_episode(seed, name, policy=bc)[0] for seed in TEST]
                 for name in ('idle', 'random', 'priority', 'teacher', 'learned')}
    (args.out / 'policy.json').write_bytes(best_path.read_bytes())
    report = {'algorithm': 'semi-Markov tabular Q-learning with uniform experience replay',
              'initialization': 'zero Q values; no BC weights or expert action labels',
              'state_version': policy.state_version, 'epsilon_start': args.epsilon_start,
              'bellman_sweeps': args.bellman_sweeps,
              'alpha': args.alpha, 'replay_updates': args.replay_updates, 'eval_every': args.eval_every,
              'scope': 'Level 1, role-constrained high-level cook actions, fixed scripted assembler partner; offline game time; not IRL or official Benchmark v3.',
              'reward': {'base': 'discounted game-money deltas divided by 50', 'potential_shaping': not args.no_shaping,
                         'formula': 'base + gamma^duration * Phi(next) - Phi(current)',
                         'terminal_potential': 0, 'gamma_per_game_second': args.gamma_per_second},
              'training_seed': args.seed, 'episodes': args.episodes, 'training_seeds': list(range(32)),
              'validation_seeds': list(VALIDATION), 'test_seeds': list(TEST),
              'initial_validation': initial, 'evaluations': evaluations, 'test': test,
              'baselines': baselines, 'selected_checkpoint': best_path.name,
              'elapsed_seconds': time.perf_counter() - started}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'result': {'rl_scores': [item['score'] for item in test],
                                'rl_served': [item['served'] for item in test],
                                'baseline_means': {name: float(np.mean([item['score'] for item in rows])) for name, rows in baselines.items()},
                                'report': str(args.out / 'report.json')}}), flush=True)


if __name__ == '__main__':
    main()
