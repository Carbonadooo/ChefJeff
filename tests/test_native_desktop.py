"""Focused native port regression tests; all gameplay uses the real engine."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from native.controls import Keyboard
from native.game import LocalGame, checked_state, digest, replay
from native.policy import drive_reference


class NativeTests(unittest.TestCase):
    def test_headless_import_no_gui_or_network(self):
        code = "from native.game import LocalGame; import sys; g=LocalGame(); g.step(); g.state(); g.reset(); g.close(); assert 'pygame' not in sys.modules; assert 'web_server' not in sys.modules; assert 'jev' not in sys.modules"
        subprocess.run([sys.executable, '-X', 'utf8', '-c', code], cwd=Path(__file__).resolve().parents[1], check=True)

    def test_two_keyboards_hold_release_and_clear(self):
        keys = Keyboard()
        keys.press('w'); keys.press('right'); keys.press('space')
        a = keys.sample()
        self.assertEqual(a['human']['move'], [0,-1])
        self.assertEqual(a['jeff']['move'], [1,0])
        self.assertTrue(a['human']['hands'])
        self.assertNotIn('hands', keys.sample()['human'])
        keys.release('w')
        self.assertEqual(keys.sample()['human']['move'], [0,0])
        keys.press('a'); keys.press('w')
        self.assertEqual(keys.sample()['human']['move'], [-1,-1])
        keys.clear()
        keys.press('d'); keys.release('d')
        self.assertEqual(keys.sample()['human']['move'], [1,0])
        self.assertEqual(keys.sample()['human']['move'], [0,0])
        keys.clear()
        self.assertEqual(keys.sample()['jeff']['move'], [0,0])

    def test_movement_release_focus_clear_collision_orientation(self):
        g = LocalGame()
        start = dict(g.k.positions)
        for _ in range(10):
            g.step({'human': {'move': [0,-1]}, 'jeff': {'move': [0,1]}})
        self.assertNotEqual(g.k.positions['human'], start['human'])
        self.assertNotEqual(g.k.positions['jeff'], start['jeff'])
        self.assertEqual(g.k.facing['human'], 'up')
        g.clear_input()
        stopped = dict(g.k.positions)
        g.step()
        self.assertEqual(g.k.positions, stopped)
        for _ in range(150):
            g.step({'human': {'move': [-1,0]}, 'jeff': {'move': [1,0]}})
        g.k.assert_invariants()
        g.close()

    def test_native_keyboard_fetch_process_take(self):
        # Route with the public AgentPort, then use the same hands/use adapter
        # as keyboard events. No teleportation or item injection.
        g = LocalGame()
        def action(key, actor='human'):
            self.assertTrue(g.agent_port(actor).act(key)['applied'], key)
            for _ in range(1000):
                g.step()
                if g.k.chefs[actor].job is None: return
            self.fail('job did not complete')
        action('go fridge')
        g.k.face('human',0,-1)
        g.step({'human': {'hands': True}})
        self.assertIsNotNone(g.k.chefs['human'].hand)
        action('go b1')
        # Engine routing faces the chosen station.
        g.step({'human': {'hands': True}})
        self.assertIsNotNone(g.k.stations['b1'].food)
        self.assertIsNone(g.k.chefs['human'].hand)
        g.step({'human': {'use': True}})
        for _ in range(250): g.step()
        self.assertEqual(g.k.stations['b1'].food.stage, 'chopped')
        g.step({'human': {'hands': True}})
        self.assertEqual(g.k.chefs['human'].hand.stage, 'chopped')
        g.close()

    def test_full_cooking_serving_two_players_and_exact_replay(self):
        with tempfile.TemporaryDirectory(prefix='chef jeff ') as folder:
            path = Path(folder) / 'sample round.jsonl'
            g = LocalGame(seed=7, record=path)
            for _ in range(5401):
                drive_reference(g); g.step()
                if g.k.ended: break
            self.assertGreater(g.k.served, 0)
            kinds = {e['kind'] for e in g.k.events}
            self.assertIn('served', kinds)
            self.assertTrue(g.k.provenance.history)
            actors = {a['actor'] for a in g.k.provenance.actions.values()}
            self.assertEqual(actors, {'human','jeff'})
            self.assertTrue(g.k.ended)
            g.close()
            expected = digest(checked_state(g.k))
            report = replay(path)
            self.assertEqual(report['score'], g.k.money)
            self.assertEqual(report['state_sha256'], expected)
            self.assertGreater(report['boundaries_checked'], 3500)
            event_lines = path.read_text().splitlines()
            event_row = json.loads(event_lines[1]); event_row['events'] = [{'kind':'invented'}]
            event_lines[1] = json.dumps(event_row)
            bad_events = Path(folder) / 'bad-events.jsonl'; bad_events.write_text('\n'.join(event_lines)+'\n')
            with self.assertRaisesRegex(ValueError, 'events diverged'): replay(bad_events)
            # A changed score must be detected, never silently trusted.
            lines = path.read_text().splitlines()
            row = json.loads(lines[3]); row['score'] += 1
            lines[3] = json.dumps(row)
            bad = Path(folder) / 'tampered.jsonl'; bad.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError, 'diverged'): replay(bad)
            unfinished = Path(folder) / 'unfinished.jsonl'
            unfinished.write_text('\n'.join(path.read_text().splitlines()[:-1])+'\n')
            with self.assertRaisesRegex(ValueError, 'incomplete'): replay(unfinished)

    def test_order_arrival_countdown_expiry_and_final_end(self):
        g = LocalGame(hz=10)
        remaining = g.state()['orders'][0]['remaining']
        for _ in range(610): g.step()
        self.assertLess(g.k.money, 0)
        kinds = {e['kind'] for e in g.k.events}
        self.assertIn('order', kinds)
        self.assertGreater(g.k.expired_count(), 0)
        self.assertGreater(g.k.orders[0]['deadline'], remaining)
        g.close()

    def test_multi_recipe_maps_unchanged_and_step_determinism(self):
        for level in ('level-1','level-2','level-3','level-4'):
            a,b = LocalGame(level,seed=4),LocalGame(level,seed=4)
            for tick in range(20):
                actions = {'human':{'move':[0,1 if tick<10 else 0]}}
                a.step(actions); b.step(actions)
            self.assertEqual(digest(checked_state(a.k)),digest(checked_state(b.k)))
            if level in ('level-3','level-4'):
                self.assertEqual({d['id'] for d in a.state()['dishes']},{'steak','burger'})
            a.close(); b.close()


if __name__ == '__main__':
    unittest.main()
