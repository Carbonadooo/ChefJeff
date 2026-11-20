"""GUI-free fixed-step adapter around the unmodified SpatialKitchen engine."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import config_contract as cc
from environment import AgentPort
from kitchen import apply_input
from model_language import english_data
from research_record import state as engine_state
from spatial_kitchen import SpatialKitchen
from . import VERSION
from .timing import decision_config

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'chefjeff-native-v2'
LEGACY_SCHEMA = 'chefjeff-native-v1'
PLAYERS = ('human', 'jeff')


def digest(value):
    # JSON object keys are strings on disk; normalize before sorting so integer
    # provenance action IDs hash identically before and after serialization.
    normalized = json.loads(json.dumps(value, ensure_ascii=True))
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def code_identity():
    names = ['kitchen.py', 'spatial_kitchen.py', 'navigation.py', 'map_definition.py',
             'config_contract.py', 'rules.py', 'provenance.py', 'environment.py',
             'research_record.py', 'levels.py', 'schema_check.py', 'food_names.py', 'model_language.py',
             'reference_policy.py', 'native_play.py']
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'native').glob('*.py'))]
    return digest({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names})


def checked_state(k):
    # Reuse the repository's research replay projection, supplement fields that
    # affect future interactions, and preserve provenance without scoring it.
    return {'engine': engine_state(k), 'time': k.time,
            'facing': k.facing, 'aim': k.aim,
            'orders': k.orders, 'stacks': {key: [asdict(f) for f in s.stack] for key, s in k.stations.items()},
            'sprint_until': k.sprint_until, 'sprint_ready_at': k.sprint_ready_at,
            'provenance': asdict(k.provenance)}


class LocalGame:
    """reset/step/state API; step time is 1/hz, independent of renderer FPS.

    Actions: {actor: {move: [dx,dy], hands/use/throw/sprint/stop: bool,
                       action_key: engine-listed action key}}.
    Movement persists until a zero vector. Discrete buttons are edge actions;
    work remains sticky until movement/stop, matching the engine/web rules.
    """
    def __init__(self, level='level-1', seed=0, hz=20, config=None, record=None, decision_seconds=0.1, runtime=None):
        if not isinstance(hz, int) or not 1 <= hz <= 240:
            raise ValueError('hz must be an integer between 1 and 240')
        self.hz = hz
        self.timing = decision_config(decision_seconds, hz)
        self.runtime = deepcopy(runtime) if runtime is not None else {'render_fps':None,'pacing':'caller_controlled'}
        self.config = deepcopy(config) if config else cc.load_level(level, seeds={'spawn': seed, 'orders': seed})
        self.episode_id = uuid4().hex
        self.k = SpatialKitchen(deepcopy(self.config))
        self.tick = 0
        self.closed = False
        self._input_n = self._event_n = 0
        self._score = self.k.money
        self._log = None
        if record:
            path = Path(record).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._log = path.open('x', encoding='utf-8')
            self._write({'type': 'header', 'schema_version': SCHEMA, 'adapter_version': VERSION,
                         'code_sha256': code_identity(), 'episode_id': self.episode_id,
                         'started_at': datetime.now(timezone.utc).isoformat(),
                         'python': platform.python_version(), 'platform': platform.system(),
                         'engine': 'SpatialKitchen', 'hz': hz, 'timing': self.timing, 'runtime': self.runtime, 'resolved_config': self.config,
                         'initial_sha256': digest(checked_state(self.k))})

    def _write(self, row):
        if self._log:
            self._log.write(json.dumps(row, ensure_ascii=True) + '\n')
            self._log.flush()

    def reset(self, **kwargs):
        self.close('reset')
        if not any(key in kwargs for key in ('config', 'level', 'seed')):
            kwargs['config'] = self.config
        kwargs.setdefault('hz', self.hz)
        kwargs.setdefault('decision_seconds', self.timing['requested_decision_seconds'])
        kwargs.setdefault('runtime', self.runtime)
        self.__init__(**kwargs)
        return self.state()

    def state(self):
        return english_data(self.k.snapshot())

    def agent_port(self, actor='jeff'):
        return AgentPort(self.k, actor)

    @staticmethod
    def validate_command(command):
        allowed = {'move', 'hands', 'use', 'throw', 'sprint', 'stop', 'action_key'}
        if not isinstance(command, dict) or set(command) - allowed:
            raise ValueError('unknown local action')
        if 'move' in command:
            vector = command['move']
            if not isinstance(vector, (list, tuple)) or len(vector) != 2 or any(type(v) is not int or v not in (-1,0,1) for v in vector):
                raise ValueError('move must contain two integer components in -1,0,1')
        for key in allowed - {'move','action_key'}:
            if key in command and type(command[key]) is not bool:
                raise ValueError('discrete controls must be booleans')
        if 'action_key' in command and not isinstance(command['action_key'], str):
            raise ValueError('action_key must be a string')

    def _apply(self, actor, command):
        self.validate_command(command)
        outcomes = []
        if 'move' in command:
            x, y = command['move']
            length = max(1, (x*x+y*y)**0.5)
            if (x/length,y/length) != tuple(self.k.manual[actor]):
                self.k.set_manual(actor,x,y)
            outcomes.append({'control':'move','applied':True,'vector':[x,y]})
        if command.get('stop'):
            self.k.stop(actor)
            outcomes.append({'control':'stop','applied':True})
        if command.get('sprint'):
            outcomes.append({'control':'sprint','applied':bool(self.k.sprint(actor))})
        if command.get('action_key'):
            outcomes.append({'control':'action_key', **self.agent_port(actor).act(command['action_key'])})
        for button in ('hands','use','throw'):
            if not command.get(button): continue
            if button == 'throw':
                action,target = self.k.forward_throw(actor),None
            else:
                target,action = self.k.facing_interaction(actor,button)
                if button == 'use' and action is None:
                    action = self.k.forward_throw(actor)
            if action:
                if target in self.k.equipment: self.k.pick_station(actor,target)
                applied,message = self.k.start(actor,action)
                outcomes.append({'control':button,'action_key':action.key,'applied':bool(applied),'reason':english_data(message)})
            else:
                outcomes.append({'control':button,'applied':False,'reason':'no_legal_facing_action'})
        return outcomes

    def mark(self, kind, details):
        return self._capture(kind, details=details)

    def _capture(self, kind, requested=None, reason=None, details=None, action_results=None):
        score = self.k.money
        row = {'type': kind, 'tick': self.tick, 'simulation_time': self.k.time,
               'requested_actions': requested or {},
               'inputs': self.k.inputs[self._input_n:],
               'events': deepcopy(self.k.events[self._event_n:]),
               'score': score, 'reward': score - self._score,
               'state_sha256': digest(checked_state(self.k)), 'end_reason': reason}
        if details is not None: row['details'] = deepcopy(details)
        if action_results is not None: row['action_results'] = action_results
        if kind == 'final':
            row['state'] = checked_state(self.k)
        self._write(row)
        self._input_n, self._event_n = len(self.k.inputs), len(self.k.events)
        self._score = score
        return row

    def step(self, actions=None, evidence=None):
        if self.closed:
            raise RuntimeError('episode is closed; reset before stepping')
        actions = actions or {}
        if set(actions) - set(PLAYERS):
            raise ValueError('actors must be human or jeff')
        for commands in actions.values():
            for command in commands if isinstance(commands,list) else [commands]:
                self.validate_command(command)
        results = {}
        for actor in PLAYERS:
            commands = actions.get(actor,{})
            results[actor] = [self._apply(actor,command) for command in (commands if isinstance(commands,list) else [commands])]
        if not self.k.ended:
            self.k.advance(1 / self.hz)
            self.tick += 1
        self.k.assert_invariants()
        row = self._capture('tick', actions, details=evidence, action_results=results)
        return {'tick': self.tick, 'time': self.k.time, 'score': self.k.money,
                'reward': row['reward'], 'ended': self.k.ended,
                'events': row['events'], 'state_sha256': row['state_sha256'], 'action_results': results}

    def clear_input(self):
        for actor in PLAYERS:
            self.k.set_manual(actor, 0, 0)
        # Chopping/washing stay sticky, just as releasing E in the web game.

    def close(self, reason=None):
        if self.closed:
            return
        reason = reason or ('round_complete' if self.k.ended else 'quit')
        self.clear_input()
        if not self.k.ended:
            self.k.abort()
        self._capture('final', reason=reason)
        if self._log:
            self._log.close()
        self.closed = True


def replay(path, strict_code=True):
    """Verify every tick through kitchen.apply_input; never run an agent or GUI."""
    with Path(path).open(encoding='utf-8-sig') as stream:
        header = json.loads(next(stream))
        if header['schema_version'] not in (SCHEMA, LEGACY_SCHEMA):
            raise ValueError('unsupported recording schema')
        if strict_code and header['code_sha256'] != code_identity():
            raise ValueError('code identity differs; use --allow-code-change only for diagnosis')
        k = SpatialKitchen(deepcopy(header['resolved_config']))
        if digest(checked_state(k)) != header['initial_sha256']:
            raise ValueError('initial state diverged')
        checked = 0
        event_n = 0
        previous_score = k.money
        final = None
        decision = None
        decision_count = 0
        for line in stream:
            row = json.loads(line)
            if row['type'] not in ('tick', 'final', 'decision_start', 'decision_end', 'control'):
                raise ValueError('unknown record type')
            if final is not None:
                raise ValueError('data after final record')
            for item in row['inputs']:
                before = len(k.inputs)
                apply_input(k, item)
                if digest(k.inputs[before:]) != digest([item]):
                    raise ValueError(f"input outcome diverged at tick {row['tick']}")
            k.assert_invariants()
            if row['simulation_time'] != k.time:
                raise ValueError(f"clock diverged at tick {row['tick']}")
            if digest(k.events[event_n:]) != digest(row['events']):
                raise ValueError(f"events diverged at tick {row['tick']}")
            event_n = len(k.events)
            if row['reward'] != k.money - previous_score:
                raise ValueError(f"reward diverged at tick {row['tick']}")
            previous_score = k.money
            if digest(checked_state(k)) != row['state_sha256'] or k.money != row['score']:
                raise ValueError(f"state diverged at tick {row['tick']}")
            if row['type'] == 'decision_start':
                info = row['details']
                if decision is not None or info['index'] != decision_count or info['start_tick'] != row['tick'] or info['start_time'] != k.time or info['start_score'] != k.money:
                    raise ValueError('decision start diverged')
                if info['target_tick'] - info['start_tick'] != header['timing']['decision_ticks']:
                    raise ValueError('decision duration diverged')
                decision = info
            elif row['type'] == 'decision_end':
                info = row['details']
                if decision is None or info['decision_index'] != decision_count or info['end_tick'] != row['tick'] or info['time'] != k.time or info['reward'] != k.money - decision['start_score'] or info['score'] != k.money or info['start_tick'] != decision['start_tick'] or info['start_time'] != decision['start_time'] or info['duration'] != k.time-decision['start_time']:
                    raise ValueError('decision end diverged')
                if not info['interrupted'] and not k.ended and row['tick'] != decision['target_tick']:
                    raise ValueError('decision boundary diverged')
                decision = None
                decision_count += 1
            checked += 1
            if row['type'] == 'final':
                if digest(row['state']) != digest(checked_state(k)):
                    raise ValueError('final state differs from replay')
                final = row
        if decision is not None:
            raise ValueError('incomplete decision window')
        if final is None:
            raise ValueError(f'incomplete recording: {checked} boundaries verified, final row missing')
    return {'verified': True, 'episode_id': header['episode_id'], 'boundaries_checked': checked, 'engine_events_checked': event_n, 'decisions_checked': decision_count,
            'tick': final['tick'], 'time': k.time, 'score': k.money, 'served': k.served,
            'state_sha256': digest(checked_state(k)), 'end_reason': final['end_reason']}
