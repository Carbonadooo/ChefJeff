"""Decision windows and wall-clock pacing, without GUI imports or larger physics steps."""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import math


def decision_config(seconds=0.1, hz=20):
    try:
        requested = Decimal(str(seconds))
    except InvalidOperation as error:
        raise ValueError('decision seconds must be a finite positive number') from error
    if isinstance(seconds, bool) or not requested.is_finite() or requested <= 0:
        raise ValueError('decision seconds must be a finite positive number')
    if requested > Decimal('86400'):
        raise ValueError('decision seconds must not exceed 86400')
    ticks = max(1, int((requested * hz).to_integral_value(rounding=ROUND_CEILING)))
    return {'requested_decision_seconds': float(requested), 'decision_ticks': ticks,
            'decision_seconds': ticks / hz, 'adapter_tick_seconds': 1 / hz,
            'engine_max_substep_seconds': 0.05, 'quantization': 'ceil_to_adapter_tick',
            'keyboard_sampling': 'adapter_tick_with_fifo_button_edges',
            'agent_actions': 'boundary_or_explicit_tick_schedule'}


def game_speed(value):
    """Simulation seconds per unpaused wall second; 1 is normal speed."""
    try:
        speed = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('speed must be finite, greater than 0 and at most 1') from error
    if isinstance(value, bool) or not math.isfinite(speed) or not 0 < speed <= 1:
        raise ValueError('speed must be finite, greater than 0 and at most 1')
    return speed


class RealtimeClock:
    """Scale unpaused wall time into game-time backlog; retain catch-up ticks."""
    def __init__(self, hz=20, speed=1.0):
        self.hz = hz
        self.speed = game_speed(speed)
        self.accumulator = 0.0
        self.active_wall_seconds = 0.0

    def add(self, seconds, paused=False):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('wall duration must be finite and nonnegative')
        if not paused:
            self.accumulator += seconds * self.speed
            self.active_wall_seconds += seconds

    def pop_tick(self):
        if self.accumulator + 1e-10 < 1 / self.hz:
            return False
        self.accumulator = max(0.0, self.accumulator - 1 / self.hz)
        return True

    def reset_backlog(self):
        # Return discarded simulation seconds; active_wall_seconds remains real time.
        dropped = self.accumulator
        self.accumulator = 0.0
        return dropped


class DecisionPort:
    """One chef's boundary-queued interface; underlying observations remain env-v1."""
    def __init__(self, session, actor):
        self.session, self.actor = session, actor
        self.engine_port = session.game.agent_port(actor)

    def observe(self):
        return {**self.engine_port.observe(), 'decision_api': 'native-decision-v1',
                'decision': self.session.observe_timing()}

    def submit(self, command, schedule=None):
        """Queue next boundary. An unconsumed submission is rejected, never overwritten."""
        return self.session.submit(self.actor, command, schedule)


class DecisionSession:
    """step() returns a training transition; advance_tick() keeps humans responsive.

    The same decision window contains all real-time keyboard frames. An agent's
    initial command is applied once at its next boundary; movement then holds
    until explicitly changed. Scheduled commands can express releases and several
    interactions inside one decision. None of this changes engine integration.
    """
    def __init__(self, game, on_decision=None):
        self.game = game
        self.k = game.k
        self.timing = deepcopy(game.timing)
        self.period_ticks = self.timing['decision_ticks']
        self.pending = {}
        self.scheduled = defaultdict(lambda: defaultdict(list))
        self.index = 0
        self.active = None
        self.last_transition = None
        self.on_decision = on_decision
        self.closed = False

    def state(self):
        return self.game.state()

    def reset(self, **kwargs):
        callback = self.on_decision
        self.close('reset')
        self.game.reset(**kwargs)
        self.__init__(self.game,on_decision=callback)
        return {'state':self.state(),'decision':self.observe_timing()}

    def observe_timing(self):
        return {**self.timing, 'next_decision_index': self.index + int(self.active is not None),
                'tick': self.game.tick, 'time': self.k.time,
                'at_boundary': self.active is None,
                'remaining_ticks': 0 if self.active is None else self.active['target_tick'] - self.game.tick}

    def agent_port(self, actor='jeff'):
        return DecisionPort(self, actor)

    def _plan(self, command, schedule):
        self.game.validate_command(command)
        plan = [(0, deepcopy(command))]
        for event in schedule or []:
            try:
                offset = Decimal(str(event['offset']))
            except InvalidOperation as error:
                raise ValueError('schedule offsets must be finite and nonnegative') from error
            if not offset.is_finite() or offset < 0:
                raise ValueError('schedule offsets must be finite and nonnegative')
            tick = int((offset * self.game.hz).to_integral_value(rounding=ROUND_CEILING))
            if tick >= self.period_ticks:
                raise ValueError('scheduled command must fall before this decision ends')
            self.game.validate_command(event['command'])
            plan.append((tick, deepcopy(event['command'])))
        return plan

    def submit(self, actor, command, schedule=None):
        if self.closed or self.k.ended:
            raise RuntimeError('session is closed or ended')
        if actor not in self.k.chefs:
            raise ValueError('actor must be human or jeff')
        if actor in self.pending:
            raise RuntimeError('a submission is already pending for this actor')
        target_index = self.index + int(self.active is not None)
        self.pending[actor] = self._plan(command, schedule)
        self.game.mark('control', {'operation': 'agent_submit', 'actor': actor,
                                 'plan': self.pending[actor], 'for_decision': target_index})
        return {'queued': True, 'decision_index': target_index}

    def _begin(self):
        if self.closed:
            raise RuntimeError('session is closed')
        self.active = {'index': self.index, 'start_tick': self.game.tick,
                       'target_tick': self.game.tick + self.period_ticks,
                       'start_time': self.k.time, 'start_score': self.k.money,
                       'event_seq': self.k.event_seq, 'frames': []}
        for actor, plan in self.pending.items():
            for offset, command in plan:
                self.scheduled[self.game.tick + offset][actor].append(command)
        self.pending.clear()
        self.game.mark('decision_start', {key: value for key, value in self.active.items() if key != 'frames'})
        if self.on_decision:
            self.on_decision(self.game)

    def advance_tick(self, actions=None, evidence=None):
        if self.k.ended:
            raise RuntimeError('episode ended')
        if self.active is None:
            self._begin()
        merged = self.scheduled.pop(self.game.tick, {})
        for actor, command in (actions or {}).items():
            commands = command if isinstance(command, list) else [command]
            merged.setdefault(actor, []).extend(deepcopy(commands))
        frame = self.game.step(dict(merged), evidence=evidence)
        self.active['frames'].append({'tick': self.game.tick, 'time': self.k.time,
                                      'actions': deepcopy(dict(merged)),
                                      'results': frame['action_results'], 'evidence': evidence})
        transition = None
        if self.game.tick >= self.active['target_tick'] or self.k.ended:
            transition = self._finish()
        return {'tick': frame, 'transition': transition}

    def _finish(self, interrupted=False):
        a = self.active
        if a is None:
            return None
        events = deepcopy([e for e in self.k.events if e['seq'] > a['event_seq']])
        transition = {'decision_index': a['index'], 'start_tick': a['start_tick'],
                      'end_tick': self.game.tick, 'start_time': a['start_time'], 'time': self.k.time,
                      'duration': self.k.time - a['start_time'],
                      'reward': self.k.money - a['start_score'], 'score': self.k.money,
                      'ended': self.k.ended, 'interrupted': interrupted,
                      'input_frames': a['frames'], 'events': events, 'state': self.game.state()}
        self.game.mark('decision_end', {key: value for key, value in transition.items()
                                       if key not in ('input_frames', 'events', 'state')})
        self.last_transition = transition
        self.active = None
        self.index += 1
        return transition

    def step(self, actions=None, schedules=None):
        """Advance one complete decision, as fast as possible for offline training.

        Real-time presentation calls advance_tick at the wall-clock pace instead.
        A missing move keeps previous motion. Use move=[0,0] to release it.
        """
        if self.active is not None:
            raise RuntimeError('step must start at a decision boundary')
        if set(schedules or {}) - set(actions or {}):
            raise ValueError('every scheduled actor needs an initial command')
        plans = {actor: self._plan(command, (schedules or {}).get(actor))
                 for actor, command in (actions or {}).items()}
        if set(plans) - set(self.k.chefs):
            raise ValueError('actor must be human or jeff')
        if set(plans) & set(self.pending):
            raise RuntimeError('actor already has a pending submission')
        self.pending.update(plans)
        while True:
            result = self.advance_tick()
            if result['transition'] is not None:
                return result['transition']

    def clear_input(self):
        canceled = {'pending': deepcopy(self.pending),
                    'scheduled': {str(tick): dict(commands) for tick, commands in self.scheduled.items()}}
        self.pending.clear()
        self.scheduled.clear()
        self.game.clear_input()
        self.game.mark('control', {'operation': 'clear_input', 'canceled': canceled})

    def note_control(self, details):
        self.game.mark('control', details)

    def close(self, reason=None):
        if self.closed:
            return
        self.clear_input()
        self._finish(interrupted=True)
        self.game.close(reason)
        self.closed = True
