"""Learned CART policy over env-v1 observations; no scripted policy fallback."""
import json
from pathlib import Path
import numpy as np
from environment import Agent


def features(seen):
    """Encode observable facts only; do not encode recipe rules or teacher decisions."""
    state = seen['kitchen']
    result = {}

    def category(name, value):
        result[f'{name}={value if value is not None else "none"}'] = 1.0

    def food(prefix, item):
        item = item or {}
        for key in ('stage', 'ingredient', 'dish', 'vessel'):
            category(prefix + '.' + key, item.get(key))
        result[prefix + '.plated'] = float(bool(item.get('plate_id')))
        for key in ('heated', 'chopped', 'washed', 'wash_remaining', 'chop_remaining'):
            result[prefix + '.' + key] = float(item.get(key) or 0)
        if item.get('contents'):
            food(prefix + '.contents', item['contents'])
        for component in item.get('components') or []:
            category(prefix + '.component', component)

    for who, chef in state['chefs'].items():
        prefix = 'self' if who == seen['who'] else 'partner'
        food(prefix + '.holding', chef.get('holding'))
        category(prefix + '.action', chef.get('action_kind'))
        category(prefix + '.target', chef.get('target'))
        result[prefix + '.busy'] = float(chef.get('job_id') is not None)
        result[prefix + '.working'] = float(chef.get('working', False))
        # Positions and identifiers are intentionally omitted for this first fixed-map test.
    for key, station in state['stations'].items():
        prefix = 'station.' + key
        food(prefix + '.food', station.get('food'))
        category(prefix + '.type', station.get('type'))
        category(prefix + '.used_by', station.get('used_by'))
        for name in ('fire', 'heating', 'pot_id'):
            result[prefix + '.' + name] = float(bool(station.get(name)))
        result[prefix + '.workers'] = float(len(station.get('workers') or []))
        result[prefix + '.stack'] = float(len(station.get('stack') or []))
    for action in seen['actions']:
        result['legal.' + action['key']] = 1.0
    for item in state.get('ground', []):
        stage = (item.get('food') or {}).get('stage', 'none')
        name = 'ground.' + stage
        result[name] = result.get(name, 0) + 1
    pending = [order for order in state['orders'] if order['status'] == 'pending']
    for order in pending:
        category('order.dish', order['dish'])
    return result


class TreePolicy:
    def __init__(self, checkpoint):
        self.model = json.loads(Path(checkpoint).read_text(encoding='utf-8')) if isinstance(checkpoint, (str, Path)) else checkpoint
        self.columns = self.model['columns']
        self.classes = self.model['classes']

    def choose(self, seen):
        if seen['kitchen']['chefs'][seen['who']].get('job_id') is not None:
            return 'wait'
        values = features(seen)
        node = self.model['tree']
        while 'feature' in node:
            value = values.get(self.columns[node['feature']], 0.0)
            node = node['left'] if value <= node['threshold'] else node['right']
        legal = {action['key'] for action in seen['actions']}
        scores = np.array(node['counts'], dtype=np.float64)
        for index, key in enumerate(self.classes):
            if key not in legal:
                scores[index] = -np.inf
        if not np.isfinite(scores).any() or np.max(scores) <= 0:
            return 'wait'
        return self.classes[int(np.argmax(scores))]


class LearnedAgent(Agent):
    name = 'chefjeff-level1-tree-bc'

    def __init__(self, checkpoint, decision_seconds=0.1):
        self.policy = TreePolicy(checkpoint)
        self.interval = decision_seconds
        self.next_poll = 0.0

    def start(self, port):
        self.next_poll = 0.0

    def poll(self, port, now):
        if now + 1e-9 < self.next_poll:
            return
        self.next_poll = now + self.interval
        if port.job_id() is None:
            key = self.policy.choose(port.observe())
            if key != 'wait':
                port.act(key, expect_job=None)

    def close(self):
        pass
