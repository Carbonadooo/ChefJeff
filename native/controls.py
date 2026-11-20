"""Keyboard state and loss-aware button FIFO. No pygame or display dependency."""
from collections import deque
import time
BINDINGS = {
    'human': {'left': 'a', 'right': 'd', 'up': 'w', 'down': 's',
              'hands': 'space', 'use': 'e', 'throw': 'q', 'sprint': 'left shift', 'stop': 'x'},
    'jeff': {'left': 'left', 'right': 'right', 'up': 'up', 'down': 'down',
             'hands': 'return', 'use': 'right ctrl', 'throw': 'right shift', 'sprint': '/', 'stop': '.'}}
BUTTONS = ('hands','use','throw','sprint','stop')


class Keyboard:
    def __init__(self):
        self.held = set()
        self.edges = set()
        self.buttons = {actor: deque() for actor in BINDINGS}
        self.raw = []
        self.sequence = 0
        self.started = time.perf_counter()
        self.last_evidence = None

    def _event(self, key, operation, **extra):
        self.sequence += 1
        event = {'sequence':self.sequence, 'key':key, 'operation':operation,
                 'observed_wall_seconds':time.perf_counter()-self.started, **extra}
        self.raw.append(event)
        return event

    def press(self, key):
        repeat = key in self.held
        event = self._event(key,'down',ignored_repeat=repeat)
        if not repeat:
            self.edges.add(key)
            for actor, keys in BINDINGS.items():
                for button in BUTTONS:
                    if key == keys[button]:
                        self.buttons[actor].append({'button':button,'event_sequence':event['sequence']})
        self.held.add(key)

    def release(self, key):
        self._event(key,'up')
        self.held.discard(key)

    def clear(self):
        canceled = {'held':sorted(self.held), 'pending_buttons':{actor:list(q) for actor,q in self.buttons.items()},
                    'raw_events':self.raw, 'operation':'keyboard_clear'}
        self.held.clear(); self.edges.clear(); self.raw = []
        for queue in self.buttons.values(): queue.clear()
        self.last_evidence = canceled
        return canceled

    def sample(self):
        out = {}
        movement = self.held | self.edges
        consumed = {}
        for actor, keys in BINDINGS.items():
            out[actor] = {'move':[int(keys['right'] in movement)-int(keys['left'] in movement),
                                  int(keys['down'] in movement)-int(keys['up'] in movement)]}
            # At most one button edge per actor per engine tick, preserving FIFO.
            # Multiple presses in a 1 s decision are never collapsed to a bool.
            if self.buttons[actor]:
                button = self.buttons[actor].popleft()
                out[actor][button['button']] = True
                consumed[actor] = button
        self.last_evidence = {'raw_events':self.raw, 'consumed_buttons':consumed,
                              'held':sorted(self.held),
                              'queued_buttons':{actor:len(q) for actor,q in self.buttons.items()}}
        self.raw = []; self.edges.clear()
        return out
