"""Offline ChefJeff behavioral cloning smoke experiment, not Benchmark v3 or IRL."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
from collections import Counter
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
import config_contract as cc
from environment import AgentPort
from spatial_kitchen import SpatialKitchen
from native.game import LocalGame, code_identity, replay
from native.timing import DecisionSession
from experiments.native_bc.policy import TreePolicy, features

ACTOR = 'jeff'
PARTNER = 'human'
LEVEL = 'level-1'
TRAIN = [0, 1, 2, 3]
VALIDATION = [40, 41]
AGGREGATION = [[20, 21], [22, 23]]
TEST = [100, 101, 102, 103]


def teacher(kitchen, who, role):
    from reference_policy import choose
    return choose(kitchen, who, role)


def episode(seed, controller, policy=None, collect=False, journal=None):
    """The learned actor uses observation dictionaries; the fixed partner is scripted."""
    started = time.perf_counter()
    if journal:
        game = LocalGame(level=LEVEL, seed=seed, record=journal, decision_seconds=0.1,
                         runtime={'pacing': 'offline_unpaced', 'controller': controller,
                                  'experiment': 'level1-tree-bc', 'trained_actor': ACTOR,
                                  'partner': 'reference-assembler', 'game_speed': 1.0})
        kitchen = game.k
    else:
        game = None
        kitchen = SpatialKitchen(cc.load_level(LEVEL, seeds={'spawn': seed, 'orders': seed}))
    port = AgentPort(kitchen, ACTOR)
    partner_port = AgentPort(kitchen, PARTNER)
    rng = random.Random(10000 + seed)
    samples = []
    decisions = Counter()
    applied = refused = 0

    def decide(_=None):
        nonlocal applied, refused
        partner_action = teacher(kitchen, PARTNER, 'assembler')
        if partner_action:
            partner_port.start(partner_action)
        if kitchen.chefs[ACTOR].job is not None:
            return
        seen = port.observe()
        oracle = teacher(kitchen, ACTOR, 'cook') if collect or controller == 'teacher' else None
        target = oracle.key if oracle else 'wait'
        if controller == 'teacher':
            key = target
        elif controller == 'learned':
            key = policy.choose(seen)
        elif controller == 'priority':
            from example_agent import PriorityAgent
            key = PriorityAgent().choose(seen, ACTOR)
        elif controller == 'random':
            key = rng.choice(seen['actions'])['key']
        else:
            key = 'wait'
        decisions[key] += 1
        if collect:
            samples.append({'seed': seed, 'time': kitchen.time, 'observation': seen,
                            'expert_action': target, 'executed_action': key})
        if key != 'wait':
            result = port.act(key, expect_job=None)
            applied += int(result['applied'])
            refused += int(not result['applied'])

    if game:
        session = DecisionSession(game, on_decision=decide)
        try:
            while not kitchen.ended:
                session.advance_tick()
        finally:
            session.close('round_complete' if kitchen.ended else 'experiment_interrupted')
    else:
        tick = 0
        while not kitchen.ended:
            if tick % 2 == 0:
                decide()
            kitchen.advance(0.05)
            tick += 1
        kitchen.assert_invariants()
    result = {'seed': seed, 'controller': controller, 'simulation_seconds': kitchen.time,
              'score': kitchen.money, 'served': kitchen.served, 'decisions': sum(decisions.values()),
              'action_counts': dict(decisions), 'applied': applied, 'refused': refused,
              'elapsed_seconds': time.perf_counter() - started}
    if journal:
        result['journal'] = str(journal)
        result['replay'] = replay(journal)
    print(json.dumps({'episode': result}), flush=True)
    return result, samples


def fit(samples, depth=12):
    rows = [features(sample['observation']) for sample in samples]
    columns = sorted(set().union(*(row.keys() for row in rows)))
    classes = ['wait'] + sorted({sample['expert_action'] for sample in samples} - {'wait'})
    col_ids = {key: index for index, key in enumerate(columns)}
    class_ids = {key: index for index, key in enumerate(classes)}
    matrix = np.zeros((len(rows), len(columns)), dtype=np.float32)
    for index, row in enumerate(rows):
        for key, value in row.items():
            matrix[index, col_ids[key]] = value
    labels = np.array([class_ids[sample['expert_action']] for sample in samples])
    # Keep every raw decision, but reduce repeated waiting dominance in this training loss.
    weights = np.where(labels == 0, 0.2, 1.0)
    eye = np.eye(len(classes), dtype=np.float64)

    def grow(indices, remaining):
        ys = labels[indices]
        ws = weights[indices]
        counts = np.bincount(ys, weights=ws, minlength=len(classes))
        leaf = {'counts': counts.tolist(), 'samples': int(len(indices))}
        if remaining == 0 or len(indices) < 4 or np.count_nonzero(counts) == 1:
            return leaf
        total = counts.sum()
        best_score = float(np.dot(counts, counts) / total)
        best = None
        sub = matrix[indices]
        variable = np.flatnonzero(np.min(sub, axis=0) != np.max(sub, axis=0))
        for feature in variable:
            order = np.argsort(sub[:, feature], kind='stable')
            values = sub[order, feature]
            cuts = np.flatnonzero(values[:-1] < values[1:])
            cuts = cuts[(cuts >= 1) & (cuts < len(indices) - 2)]
            if len(cuts) > 32:
                cuts = cuts[np.linspace(0, len(cuts) - 1, 32).astype(int)]
            if not len(cuts):
                continue
            prefix = np.cumsum(eye[ys[order]] * ws[order, None], axis=0)[cuts]
            left_mass = prefix.sum(axis=1)
            right = counts - prefix
            right_mass = right.sum(axis=1)
            scores = np.sum(prefix * prefix, axis=1) / left_mass + np.sum(right * right, axis=1) / right_mass
            chosen = int(np.argmax(scores))
            if scores[chosen] > best_score + 1e-10:
                cut = int(cuts[chosen])
                best_score = float(scores[chosen])
                best = (int(feature), float((float(values[cut]) + float(values[cut + 1])) / 2),
                        indices[order[:cut + 1]], indices[order[cut + 1:]])
        if best is None:
            return leaf
        feature, threshold, left, right = best
        return {'feature': feature, 'threshold': threshold, 'left': grow(left, remaining - 1),
                'right': grow(right, remaining - 1)}

    model = {'schema': 'chefjeff-tree-bc-v1', 'algorithm': 'weighted CART behavioral cloning',
             'level': LEVEL, 'actor': ACTOR, 'decision_seconds': 0.1, 'classes': classes,
             'columns': columns, 'wait_loss_weight': 0.2, 'tree': grow(np.arange(len(samples)), depth)}
    return model, matrix, labels


def accuracy(policy, samples):
    predicted = [policy.choose(sample['observation']) for sample in samples]
    targets = [sample['expert_action'] for sample in samples]
    nonwait = [index for index, target in enumerate(targets) if target != 'wait']
    return {'samples': len(samples), 'accuracy': float(np.mean(np.array(predicted) == targets)),
            'nonwait_accuracy': float(np.mean([predicted[i] == targets[i] for i in nonwait])) if nonwait else None}


def write_samples(path, samples):
    with gzip.open(path, 'xt', encoding='utf-8') as stream:
        for sample in samples:
            stream.write(json.dumps(sample, ensure_ascii=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    if args.pilot:
        episode(0, 'teacher')
        return
    start = time.perf_counter()
    training = []
    teacher_train = []
    for seed in TRAIN:
        result, samples = episode(seed, 'teacher', collect=True)
        training.extend(samples)
        teacher_train.append(result)
    write_samples(args.out / 'teacher-train.jsonl.gz', training)
    validation = []
    for seed in VALIDATION:
        _, samples = episode(seed, 'teacher', collect=True)
        validation.extend(samples)
    write_samples(args.out / 'teacher-validation.jsonl.gz', validation)
    stages = []
    best_model = None
    best_score = -float('inf')
    for stage in range(3):
        model, matrix, labels = fit(training)
        checkpoint = args.out / f'checkpoint-{stage}.json'
        checkpoint.write_text(json.dumps(model), encoding='utf-8')
        policy = TreePolicy(checkpoint)
        validation_rollouts = [episode(seed, 'learned', policy=policy)[0] for seed in VALIDATION]
        score = float(np.mean([row['score'] for row in validation_rollouts]))
        stats = {'stage': stage, 'training_samples': len(training), 'training': accuracy(policy, training),
                 'validation': accuracy(policy, validation), 'validation_rollouts': validation_rollouts,
                 'validation_mean_score': score}
        stages.append(stats)
        print(json.dumps({'training_stage': stats}), flush=True)
        if score > best_score:
            best_model, best_score = model, score
        if stage < 2:
            added = []
            for seed in AGGREGATION[stage]:
                _, samples = episode(seed, 'learned', policy=policy, collect=True)
                added.extend(samples)
            write_samples(args.out / f'aggregation-{stage}.jsonl.gz', added)
            training.extend(added)
    best_path = args.out / 'policy.json'
    best_path.write_text(json.dumps(best_model, indent=2), encoding='utf-8')
    policy = TreePolicy(best_path)
    model, matrix, labels = fit(training)
    np.savez_compressed(args.out / 'training-data.npz', observations=matrix, expert_actions=labels,
                        columns=np.array(model['columns']), action_keys=np.array(model['classes']))
    test = []
    # Held-out test seeds are used only after checkpoint selection is complete.
    for controller in ('idle', 'random', 'priority', 'teacher', 'learned'):
        for seed in TEST:
            test.append(episode(seed, controller, policy=policy)[0])
    summaries = {}
    for controller in ('idle', 'random', 'priority', 'teacher', 'learned'):
        subset = [row for row in test if row['controller'] == controller]
        summaries[controller] = {'mean_score': float(np.mean([row['score'] for row in subset])),
                                 'mean_served': float(np.mean([row['served'] for row in subset])),
                                 'scores': [row['score'] for row in subset],
                                 'served': [row['served'] for row in subset]}
    recorded = episode(TEST[0], 'learned', policy=policy, journal=args.out / 'learned-evaluation.jsonl')[0]
    report = {'scope': 'Level 1, fixed scripted assembler partner, structured full-state observations and high-level legal actions. Offline virtual clock; not official Benchmark v3, pixel control, keyboard imitation, RL or IRL.',
              'train_seeds': TRAIN, 'aggregation_seeds': AGGREGATION, 'validation_seeds': VALIDATION,
              'test_seeds': TEST, 'teacher_train': teacher_train, 'stages': stages,
              'test': test, 'summary': summaries, 'recorded_evaluation': recorded,
              'engine_code_sha256': code_identity(), 'policy_sha256': hashlib.sha256(best_path.read_bytes()).hexdigest(),
              'python': sys.version, 'numpy': np.__version__, 'elapsed_seconds': time.perf_counter() - start}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'summary': summaries, 'report': str(args.out / 'report.json')}), flush=True)


if __name__ == '__main__':
    main()
