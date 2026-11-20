"""Uniform slow-play clock, input retention, CLI metadata and replay regressions."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from native.controls import Keyboard
from native.game import LocalGame, checked_state, digest, replay
from native.timing import DecisionSession, RealtimeClock, game_speed
import native_play


class SpeedTests(unittest.TestCase):
    def test_speed_values_reject_zero_negative_nonfinite_and_fast(self):
        for value in (1, '0.5', 0.25):
            self.assertEqual(game_speed(value), float(value))
        for value in (0, -1, 1.01, True, False, None, 'bad', float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                game_speed(value)

    def test_quarter_speed_needs_200_wall_ms_for_50_game_ms(self):
        clock = RealtimeClock(speed=0.25)
        clock.add(0.199)
        self.assertFalse(clock.pop_tick())
        clock.add(0.001)
        self.assertTrue(clock.pop_tick())
        self.assertFalse(clock.pop_tick())
        self.assertAlmostEqual(clock.active_wall_seconds, 0.2)

    def test_pause_and_reset_keep_real_and_simulation_clocks_distinct(self):
        clock = RealtimeClock(speed=0.25)
        clock.add(1)
        clock.add(20, paused=True)
        self.assertAlmostEqual(clock.active_wall_seconds, 1)
        self.assertAlmostEqual(clock.reset_backlog(), 0.25)
        self.assertFalse(clock.pop_tick())
        clock.add(0.2)
        self.assertTrue(clock.pop_tick())
        self.assertAlmostEqual(clock.active_wall_seconds, 1.2)

    def test_speed_scales_all_engine_time_without_changing_same_time_state(self):
        expected = None
        for interval in (0.1, 1):
            for speed in (1, 0.5, 0.25):
                game = LocalGame(seed=11, decision_seconds=interval)
                session = DecisionSession(game)
                clock = RealtimeClock(speed=speed)
                try:
                    for _ in range(round(120 / speed)):
                        clock.add(1 / 60)
                        while clock.pop_tick():
                            session.advance_tick({'human': {'move': [1, -1]}, 'jeff': {'move': [0, 1]}})
                    self.assertEqual(game.tick, 40)
                    self.assertAlmostEqual(game.k.time, 2)
                    self.assertEqual(session.index, 20 if interval == 0.1 else 2)
                    state = digest(checked_state(game.k))
                    if expected is None:
                        expected = state
                    self.assertEqual(state, expected)
                    self.assertTrue(all(row['seconds'] <= 0.05 for row in game.k.inputs if row['call'] == 'advance'))
                finally:
                    session.close()

    def test_cli_records_speed_retains_button_bursts_and_replays(self):
        def fake_window(game, fps, demo, session, art_mode):
            clock = RealtimeClock(game.hz, speed=game.runtime['game_speed'])
            keys = Keyboard()
            for _ in range(3):
                keys.press('space')
                keys.release('space')
            for _ in range(round(60 / clock.speed)):
                clock.add(1 / 60)
                while clock.pop_tick():
                    session.advance_tick(keys.sample(), evidence={
                        'keyboard': keys.last_evidence,
                        'active_wall_seconds': clock.active_wall_seconds,
                        'game_speed': clock.speed,
                    })

        with tempfile.TemporaryDirectory() as folder:
            for speed in (1, 0.25):
                path = Path(folder) / f'speed-{speed}.jsonl'
                with patch.dict('sys.modules', {'native.window': SimpleNamespace(run=fake_window)}), redirect_stdout(io.StringIO()):
                    result = native_play.main(['--speed', str(speed), '--decision-seconds', '1', '--record', str(path)])
                self.assertEqual(result, 0)
                rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
                self.assertEqual(rows[0]['runtime']['game_speed'], speed)
                self.assertEqual(rows[0]['runtime']['speed_timebase'], 'simulation_seconds_per_wall_second')
                ticks = [row for row in rows if row['type'] == 'tick']
                self.assertEqual(len(ticks), 20)
                self.assertAlmostEqual(ticks[-1]['details']['active_wall_seconds'], 1 / speed)
                attempts = [entry for row in ticks for command in row['action_results']['human']
                            for entry in command if entry['control'] == 'hands']
                self.assertEqual(len(attempts), 3)
                self.assertEqual(replay(path)['decisions_checked'], 1)

    def test_headless_rejects_misleading_slow_play_option(self):
        error = io.StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            native_play.main(['--headless', '--speed', '0.25', '--no-record'])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('headless runs are unpaced', error.getvalue())


if __name__ == '__main__':
    unittest.main()
