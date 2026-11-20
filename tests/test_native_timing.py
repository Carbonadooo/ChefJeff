"""CPU-only timing/input/replay checks. Never imports pygame or opens a display."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from native.controls import Keyboard
from native.game import LocalGame, checked_state, digest, replay, ROOT
from native.timing import DecisionSession, RealtimeClock, decision_config


class TimingTests(unittest.TestCase):
    def test_exact_intervals_and_same_duration_physics(self):
        final = []
        for interval,count in [(0.1,20),(1,2)]:
            g=LocalGame(seed=11,decision_seconds=interval); s=DecisionSession(g)
            for index in range(count):
                t=s.step({'human':{'move':[1,-1]},'jeff':{'move':[0,1]}})
                self.assertEqual(t['end_tick']-t['start_tick'],round(interval*20))
                self.assertAlmostEqual(t['duration'],interval)
                self.assertEqual(t['decision_index'],index)
            self.assertEqual(g.tick,40); self.assertAlmostEqual(g.k.time,2)
            self.assertTrue(all(i['seconds'] <= .05 for i in g.k.inputs if i['call']=='advance'))
            final.append(digest(checked_state(g.k))); s.close()
        self.assertEqual(*final)

    def test_wall_clock_pause_and_frame_rates(self):
        states=[]
        for interval,fps in [(0.1,30),(1,120)]:
            g=LocalGame(seed=3,decision_seconds=interval); s=DecisionSession(g); clock=RealtimeClock()
            for _ in range(fps*2):
                clock.add(1/fps)
                while clock.pop_tick(): s.advance_tick({'human':{'move':[0,-1]}})
            before=g.k.time
            clock.add(5,paused=True)
            self.assertFalse(clock.pop_tick()); self.assertEqual(g.k.time,before)
            self.assertEqual(g.tick,40)
            states.append(digest(checked_state(g.k))); s.close()
        self.assertEqual(*states)
        clock=RealtimeClock(); clock.add(1.25)
        self.assertEqual(sum(clock.pop_tick() for _ in range(30)),25)

    def test_agent_boundary_and_scheduled_release(self):
        g=LocalGame(decision_seconds=1); s=DecisionSession(g)
        s.advance_tick()
        p=s.agent_port('jeff'); receipt=p.submit({'move':[1,0]})
        self.assertEqual(receipt['decision_index'],1)
        with self.assertRaisesRegex(RuntimeError,'already pending'): p.submit({'stop':True})
        for _ in range(19): s.advance_tick()
        self.assertEqual(g.k.manual['jeff'],(0,0))
        s.advance_tick(); self.assertEqual(g.k.manual['jeff'],(1,0))
        self.assertEqual(p.observe()['decision']['remaining_ticks'],19)
        for _ in range(19): s.advance_tick()
        t=s.step({'jeff':{'move':[0,-1]}},schedules={'jeff':[{'offset':.1,'command':{'move':[0,0]}}]})
        self.assertEqual(g.k.manual['jeff'],(0,0))
        self.assertEqual(len(t['input_frames']),20)
        self.assertEqual(t['input_frames'][2]['actions']['jeff'][0]['move'],[0,0])
        s.close()

    def test_keyboard_fifo_short_press_repeat_and_combinations(self):
        k=Keyboard()
        k.press('w'); k.press('d'); k.release('w'); k.release('d')
        for _ in range(3): k.press('space'); k.release('space')
        k.press('return'); k.press('return')
        first=k.sample()
        self.assertEqual(first['human']['move'],[1,-1]); self.assertTrue(first['human']['hands'])
        self.assertTrue(first['jeff']['hands'])
        self.assertEqual(k.last_evidence['queued_buttons']['human'],2)
        self.assertTrue(k.sample()['human']['hands']); self.assertTrue(k.sample()['human']['hands'])
        self.assertNotIn('hands',k.sample()['human'])
        self.assertEqual(k.sample()['human']['move'],[0,0])

    def test_no_input_hold_and_explicit_release(self):
        g=LocalGame(decision_seconds=.1); s=DecisionSession(g)
        s.step({'human':{'move':[1,0]}})
        s.step(); self.assertEqual(g.k.manual['human'],(1,0))
        s.step({'human':{'move':[0,0]}})
        pos=g.k.positions['human']; s.step(); self.assertEqual(pos,g.k.positions['human'])
        s.close()

    def test_clear_cancels_buffer_and_keeps_simulation_phase(self):
        g=LocalGame(decision_seconds=1); s=DecisionSession(g); k=Keyboard()
        s.submit('human',{'move':[1,0]},[{'offset':.5,'command':{'hands':True}}])
        s.advance_tick(); s.submit('jeff',{'move':[1,0]})
        k.press('space'); k.release('space'); canceled=k.clear()
        self.assertTrue(canceled['pending_buttons']['human'])
        tick=g.tick; s.clear_input()
        self.assertEqual(g.tick,tick); self.assertFalse(s.pending); self.assertFalse(s.scheduled)
        self.assertFalse(k.held); self.assertFalse(k.buttons['human'])
        self.assertTrue(all(v==(0,0) for v in g.k.manual.values()))
        self.assertEqual(s.observe_timing()['remaining_ticks'],19)
        for _ in range(19): s.advance_tick(k.sample())
        self.assertIsNotNone(s.last_transition); s.close()

    def test_record_replay_decisions_multiple_edges_and_tamper(self):
        for interval in (.1,1):
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'round.jsonl'; g=LocalGame(seed=17,decision_seconds=interval,record=path)
                s=DecisionSession(g); keyboard=Keyboard()
                for _ in range(3): keyboard.press('space'); keyboard.release('space')
                for _ in range(40): s.advance_tick(keyboard.sample(),evidence=keyboard.last_evidence)
                s.close('test_complete')
                result=replay(path)
                self.assertEqual(result['tick'],40)
                self.assertEqual(result['decisions_checked'],20 if interval==.1 else 2)
                self.assertEqual(result['state_sha256'],digest(checked_state(g.k)))
                rows=[json.loads(line) for line in path.read_text().splitlines()]
                attempts=[entry for r in rows if r['type']=='tick' for command in r['action_results']['human'] for entry in command if entry['control']=='hands']
                self.assertEqual(len(attempts),3)
                self.assertTrue(all('applied' in entry for entry in attempts))
                start=next(row for row in rows if row['type']=='decision_start')
                start['details']['target_tick']+=1
                bad=Path(folder)/'bad.jsonl'; bad.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
                with self.assertRaisesRegex(ValueError,'decision duration'): replay(bad)

    def test_seed_reset_and_custom_positive_quantization(self):
        self.assertEqual(decision_config(.075)['decision_seconds'],.1)
        self.assertEqual(decision_config(.001)['decision_seconds'],.05)
        self.assertEqual(decision_config(1.25)['decision_ticks'],25)
        for invalid in (0,-1,float('nan'),float('inf'),True,'bad'):
            with self.assertRaises(ValueError): decision_config(invalid)
        a=LocalGame(seed=12,decision_seconds=1); b=LocalGame(seed=12,decision_seconds=1)
        self.assertEqual(digest(checked_state(a.k)),digest(checked_state(b.k)))
        a.reset(); self.assertEqual(a.timing['decision_seconds'],1)
        a.close(); b.close()
        g=LocalGame(seed=12,decision_seconds=1); session=DecisionSession(g)
        session.step({'human':{'move':[1,0]}})
        first_id=g.episode_id
        result=session.reset()
        self.assertEqual(result['decision']['time'],0)
        self.assertEqual(result['decision']['decision_seconds'],1)
        self.assertEqual(session.index,0); self.assertNotEqual(g.episode_id,first_id)
        session.close()

    def test_legacy_record_without_rewriting(self):
        path=ROOT/'native-recordings/sample-final-steak.jsonl'
        if not path.exists(): self.skipTest('optional prior-version sample is absent')
        before=path.read_bytes()
        report=replay(path,strict_code=False)
        self.assertEqual(report['score'],500); self.assertEqual(report['engine_events_checked'],413)
        self.assertEqual(path.read_bytes(),before)


if __name__=='__main__': unittest.main()
