"""Portable checkpoint deployment and training-entry smoke checks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from experiments.native_bc.experiment import episode, fit
from experiments.native_bc.policy import TreePolicy

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / 'experiments/native_bc/checkpoints/level1-tree-bc.json'


class NativeLearningTests(unittest.TestCase):
    def test_packaged_checkpoint_finishes_a_heldout_round(self):
        result, _ = episode(100, 'learned', policy=TreePolicy(CHECKPOINT))
        self.assertEqual(result['simulation_seconds'], 180)
        self.assertEqual(result['score'], 500)
        self.assertEqual(result['served'], 10)
        self.assertEqual(result['refused'], 0)

    def test_portable_training_fits_and_reloads_without_local_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'pilot'
            command = [sys.executable, '-X', 'utf8', str(ROOT / 'experiments/native_bc/experiment.py'),
                       '--out', str(out), '--pilot']
            completed = subprocess.run(command, cwd=temporary, capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn('"simulation_seconds": 180.0', completed.stdout)
            _, samples = episode(0, 'teacher', collect=True)
            model, _, _ = fit(samples)
            path = Path(temporary) / 'policy.json'
            path.write_text(json.dumps(model), encoding='utf-8')
            result, _ = episode(101, 'learned', policy=TreePolicy(path))
            self.assertGreaterEqual(result['score'], 200)
            self.assertGreater(result['served'], 0)


if __name__ == '__main__':
    unittest.main()
