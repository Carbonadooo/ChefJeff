"""Reward, variable-duration TD targets and public-port Q policy regressions."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from experiments.native_rl.env import CookingEnv
from experiments.native_rl.q_policy import KINDS, QPolicy, potential, state_key
from experiments.native_rl.train import update, batch_update


class NativeRLTests(unittest.TestCase):
    def test_terminal_q_target_does_not_bootstrap_and_masks_unavailable_actions(self):
        policy = QPolicy()
        policy.values('next')[1] = 100
        policy.values('next')[2] = 4
        transition = {'state': 'current', 'action': 3, 'reward': 2,
                      'discount': 0.5, 'next_state': 'next', 'next_actions': (2,), 'ended': False}
        update(policy, transition, alpha=1)
        self.assertEqual(policy.values('current')[3], 4)
        transition['ended'] = True
        update(policy, transition, alpha=1)
        self.assertEqual(policy.values('current')[3], 2)

    def test_empirical_bellman_sweeps_remove_an_overvalued_wait_loop(self):
        policy = QPolicy()
        state = json.dumps(['state', [0, 1]])
        terminal = json.dumps(['terminal', []])
        policy.values(state)[0] = 10
        policy.values(terminal)
        memory = [
            {'state': state, 'action': 0, 'reward': 0, 'discount': 0.9,
             'next_state': state, 'next_actions': (0, 1), 'ended': False},
            {'state': state, 'action': 1, 'reward': 1, 'discount': 0.9,
             'next_state': terminal, 'next_actions': (), 'ended': True},
        ]
        batch_update(policy, memory, 1000)
        self.assertAlmostEqual(policy.values(state)[0], 0.9, places=6)
        self.assertAlmostEqual(policy.values(state)[1], 1, places=6)

    def test_wait_duration_discount_and_potential_are_separate_from_money(self):
        env = CookingEnv(seed=12, gamma_per_second=0.9)
        initial_score = env.k.money
        phi = potential(env.seen)
        step = env.step(0)
        self.assertAlmostEqual(step['duration'], 0.5)
        self.assertEqual(env.tick, 10)
        self.assertAlmostEqual(step['discount'], 0.9 ** 0.5)
        self.assertEqual(env.k.money, initial_score)
        self.assertAlmostEqual(step['reward'], step['base_reward'] + step['discount'] * potential(env.seen) - phi)
        self.assertEqual(potential({**env.seen, 'ended': True}), 0)
        self.assertTrue(all(row['seconds'] <= 0.05 for row in env.k.inputs if row['call'] == 'advance'))

    def test_checkpoint_roundtrip_and_legal_masking_do_not_use_bc(self):
        env = CookingEnv(seed=13)
        policy = QPolicy()
        key = state_key(env.seen)
        policy.values(key)[KINDS.index('fetch')] = 3
        policy.values(key)[KINDS.index('extinguish')] = 100
        self.assertEqual(policy.choose(env.seen), 'fetch beef')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'q.json'
            policy.save(path, initialization='zero Q values; no expert labels')
            loaded = QPolicy(path)
            self.assertEqual(loaded.choose(env.seen), 'fetch beef')
            np.testing.assert_array_equal(loaded.values(key), policy.values(key))
            self.assertNotIn('tree', json.loads(path.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
