"""Tabular reward-trained cook; no imitation labels or scripted cook fallback."""
import json
from pathlib import Path
import numpy as np
from environment import Agent

# An explicit role-constrained macro-action space. Targets within a kind follow
# the original engine's legal-action order; navigation remains engine-provided.
KINDS = ('wait', 'fetch', 'put_board', 'chop', 'take_board', 'put_pot', 'lift_pot',
         'plate_counter', 'return_pot', 'wash', 'empty_pot', 'take_tool', 'extinguish', 'put_tool')


def food_code(food):
    if not food:
        return '-'
    if food.get('stage') == 'pot':
        return 'pot/' + food_code(food.get('contents'))
    return ('plate/' if food.get('plate_id') else '') + food.get('stage', '-')


def choices(seen, version=3):
    by_kind = {}
    for action in seen['actions']:
        by_kind.setdefault(action['kind'], action['key'])
    return {index: by_kind[kind] for index, kind in enumerate(KINDS) if kind in by_kind and (version < 3 or kind not in ('take_tool', 'extinguish', 'put_tool'))}


def state_key(seen, version=3):
    """Documented fixed-map abstraction of observable state, without item IDs/time."""
    state = seen['kitchen']
    stations = state['stations']
    who = seen['who']
    other = next(key for key in state['chefs'] if key != who)
    boards = [food_code(stations[key].get('food')) + ('/busy' if stations[key].get('used_by') else '')
              for key in ('b1', 'b2', 'b3')]
    pans = [[food_code(stations[key].get('food')), bool(stations[key].get('pot_id')),
             bool(stations[key].get('heating')), bool(stations[key].get('fire'))]
            for key in ('p1',)]
    counters = [food_code(stations[key].get('food')) for key in ('plates', 'counter2')]
    dirty = min(2, len(stations['sink'].get('stack') or []) + int(bool(stations['sink'].get('food'))))
    if version >= 2:
        # Pool interchangeable stations to reduce tabular sample complexity.
        # No action or recipe choice is inserted by this representation.
        board_foods = [stations[key].get('food') or {} for key in ('b1', 'b2', 'b3')]
        board_summary = [any(item.get('stage') == stage for item in board_foods)
                         for stage in ('raw', 'chopped')]
        surface_foods = [station.get('food') or {} for station in stations.values() if station.get('counter')]
        plate_summary = [any(item.get('stage') == 'clean_plate' for item in surface_foods),
                         any(item.get('plate_id') and item.get('stage') in ('ready', 'assembled') for item in surface_foods)]
        return json.dumps([food_code(state['chefs'][who].get('holding')), board_summary, pans,
                           plate_summary, dirty > 0, sorted(choices(seen, version))], separators=(',', ':'))
    return json.dumps([food_code(state['chefs'][who].get('holding')), boards, pans, counters,
                       dirty, food_code(stations['dryer'].get('food')),
                       food_code(stations['returns'].get('food')),
                       food_code(state['chefs'][other].get('holding')), sorted(choices(seen, version))],
                      separators=(',', ':'))


def potential(seen):
    """Bounded inventory progress for training only; terminal potential is zero."""
    if seen['ended']:
        return 0.0
    state = seen['kitchen']
    visited = set()

    def progress(food):
        if not food:
            return 0.0
        identity = food.get('id')
        if identity and identity in visited:
            return 0.0
        if identity:
            visited.add(identity)
        if food.get('stage') == 'pot':
            return progress(food.get('contents'))
        if food.get('plate_id') and food.get('stage') in ('ready', 'assembled'):
            return 1.0
        return {'raw': 0.05, 'chopped': 0.25, 'cooking': 0.4, 'ready': 0.75}.get(food.get('stage'), 0.0)

    total = sum(progress(station.get('food')) for station in state['stations'].values())
    total += sum(progress(chef.get('holding')) for chef in state['chefs'].values())
    total += sum(progress(item.get('food')) for item in state.get('ground', []))
    return min(4.0, total)


class QPolicy:
    def __init__(self, checkpoint=None):
        model = json.loads(Path(checkpoint).read_text(encoding='utf-8')) if checkpoint else {}
        if model and model.get('action_kinds') != list(KINDS):
            raise ValueError('Checkpoint action space differs')
        self.state_version = model.get('state_version', 1) if model else 3
        self.q = {key: np.array(values, dtype=np.float64) for key, values in model.get('q', {}).items()}
        self.metadata = model

    def values(self, state):
        return self.q.setdefault(state, np.zeros(len(KINDS), dtype=np.float64))

    def action(self, seen, rng=None, epsilon=0.0, random_ties=False):
        available = choices(seen, self.state_version)
        valid = list(available)
        if not valid:
            return 0, 'wait'
        if rng is not None and rng.random() < epsilon:
            index = int(rng.choice(valid))
        else:
            values = self.values(state_key(seen, self.state_version))
            best = max(values[index] for index in valid)
            tied = [index for index in valid if abs(values[index] - best) < 1e-10]
            index = int(rng.choice(tied)) if random_ties and rng is not None else tied[0]
        return index, available[index]

    def choose(self, seen):
        return self.action(seen)[1]

    def save(self, path, **metadata):
        model = {'schema': 'chefjeff-tabular-q-v1', 'algorithm': 'semi-Markov Q-learning with experience replay',
                 'state_version': self.state_version, 'action_kinds': list(KINDS), 'level': 'level-1', 'actor': 'jeff',
                 'wait_seconds': 0.5, 'decision_seconds': 0.1, **metadata,
                 'q': {key: values.tolist() for key, values in self.q.items()}}
        with Path(path).open('x', encoding='utf-8') as stream:
            json.dump(model, stream)


class RLAgent(Agent):
    name = 'chefjeff-level1-q-learning'

    def __init__(self, checkpoint):
        self.policy = QPolicy(checkpoint)
        self.next_poll = 0.0

    def start(self, port):
        self.next_poll = 0.0

    def poll(self, port, now):
        if now + 1e-9 < self.next_poll or port.job_id() is not None:
            return
        index, key = self.policy.action(port.observe())
        self.next_poll = now + (0.5 if index == 0 else 0.1)
        if index:
            port.act(key, expect_job=None)

    def close(self):
        pass
