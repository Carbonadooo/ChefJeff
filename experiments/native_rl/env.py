"""Semi-Markov cooking options over the unchanged 50 ms kitchen simulation."""
import numpy as np
import config_contract as cc
from environment import AgentPort
from spatial_kitchen import SpatialKitchen
from experiments.native_rl.q_policy import choices, potential, state_key


class CookingEnv:
    def __init__(self, seed=0, gamma_per_second=0.995, shaping=True, state_version=3):
        self.k = SpatialKitchen(cc.load_level('level-1', seeds={'spawn': seed, 'orders': seed}))
        self.actor = AgentPort(self.k, 'jeff')
        self.partner = AgentPort(self.k, 'human')
        self.gamma = gamma_per_second
        self.shaping = shaping
        self.state_version = state_version
        self.tick = 0
        self.refused = 0
        self.decisions = 0
        self._partner_tick()
        self.seen = self.actor.observe()

    def _partner_tick(self):
        # This script is the fixed environment partner, never the learned actor.
        from reference_policy import choose
        action = choose(self.k, 'human', 'assembler')
        if action:
            self.partner.start(action)

    def step(self, index):
        available = choices(self.seen, self.state_version)
        if index not in available:
            raise ValueError('Action is not available in the role-constrained public action list')
        if self.k.ended:
            raise RuntimeError('Episode already ended')
        before = self.seen
        key = available[index]
        if index:
            outcome = self.actor.act(key, expect_job=None)
            self.refused += int(not outcome['applied'])
        start = self.k.time
        previous_score = self.k.money
        reward = 0.0
        minimum = 0.5 if index == 0 else 0.1
        while not self.k.ended:
            self.k.advance(0.05)
            self.tick += 1
            elapsed = self.k.time - start
            reward += self.gamma ** elapsed * (self.k.money - previous_score) / 50.0
            previous_score = self.k.money
            if self.tick % 2 == 0:
                self._partner_tick()
                if elapsed + 1e-8 >= minimum and self.k.chefs['jeff'].job is None:
                    break
        self.seen = self.actor.observe()
        duration = self.k.time - start
        discount = self.gamma ** duration
        shaped = reward + (discount * potential(self.seen) - potential(before) if self.shaping else 0.0)
        self.decisions += 1
        return {'state': state_key(before, self.state_version), 'action': index, 'reward': shaped, 'base_reward': reward,
                'discount': discount, 'duration': duration, 'next_state': state_key(self.seen, self.state_version),
                'next_actions': tuple(choices(self.seen, self.state_version)), 'ended': self.k.ended}


def rollout(policy, seed, epsilon=0.0, rng=None, shaping=False):
    env = CookingEnv(seed, shaping=shaping, state_version=policy.state_version)
    rng = rng if rng is not None else np.random.default_rng(seed)
    actions = {}
    while not env.k.ended:
        index, key = policy.action(env.seen, rng, epsilon)
        actions[key] = actions.get(key, 0) + 1
        env.step(index)
    env.k.assert_invariants()
    return {'seed': seed, 'score': env.k.money, 'served': env.k.served, 'simulation_seconds': env.k.time,
            'decisions': env.decisions, 'refused': env.refused, 'actions': actions}
