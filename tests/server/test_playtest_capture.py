import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import capture_playtest


class PlaytestCaptureChecks(unittest.TestCase):
    def fixture(self, folder, exit_code=0, break_counter=False):
        root = Path(folder)
        device = root / 'gpu'; device.mkdir()
        (device / 'mem_info_vram_total').write_text(str(12 * 2**30))
        used = device / 'mem_info_vram_used'; used.write_text(str(6 * 2**30))
        game = root / 'HomeEquestria.x86_64'
        # A real subprocess changes the counter while the recorder owns its lifetime.
        game.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nimport time\n'
                        'time.sleep(.15)\nPath(' + repr(str(used)) + ').write_text('
                        + repr('broken' if break_counter else str(9 * 2**30)) + ')\n'
                        'time.sleep(.5)\nraise SystemExit(' + str(exit_code) + ')\n')
        game.chmod(0o755)
        mod = root / 'candidate.pck'; mod.write_bytes(b'candidate')
        profile = root / 'user/home-equestria-public'; profile.mkdir(parents=True)
        (profile / 'ai_config.json').write_text(json.dumps({'tts': {'provider':'moss','url':'http://127.0.0.1:18882/tts'}}))
        return {'game_directory':str(root),'gpu_device':str(device),'mod_pack':str(mod),
                'mod_sha256':hashlib.sha256(mod.read_bytes()).hexdigest(),
                'user_data_home':str(root/'user'),'companion_url':'http://127.0.0.1:18882',
                'output_directory':str(root/'runs')}

    @patch('capture_playtest.health', return_value={'ready': True, 'native_backend': 'breeze'})
    def test_capture_spans_game_and_stops_on_exit(self, _health):
        with tempfile.TemporaryDirectory() as folder:
            config = self.fixture(folder)
            self.assertEqual(capture_playtest.run(config), 0)
            result = json.loads(next((Path(folder)/'runs').glob('*/playtest.json')).read_text())
            self.assertTrue(result['gpu_capture_covers_game'])
            self.assertEqual(result['whole_card_peak_vram_gib'], 9)
            self.assertEqual(result['whole_card_minimum_free_vram_gib'], 3)
            self.assertGreater(result['gpu_samples'], 3)

    @patch('capture_playtest.health', return_value={'ready': True, 'native_backend': 'breeze'})
    def test_game_failure_still_finishes_recording(self, _health):
        with tempfile.TemporaryDirectory() as folder:
            config = self.fixture(folder, exit_code=7)
            self.assertEqual(capture_playtest.run(config), 7)
            result = json.loads(next((Path(folder)/'runs').glob('*/playtest.json')).read_text())
            self.assertEqual(result['game_exit_code'], 7)
            self.assertTrue(result['gpu_capture_covers_game'])

    @patch('capture_playtest.health', return_value={'ready': True, 'native_backend': 'breeze'})
    def test_sampling_failure_stops_the_owned_game(self, _health):
        with tempfile.TemporaryDirectory() as folder:
            config = self.fixture(folder, break_counter=True)
            with self.assertRaises(ValueError):
                capture_playtest.run(config)
            result = json.loads(next((Path(folder)/'runs').glob('*/playtest.json')).read_text())
            self.assertEqual(result['game_exit_code'], -15)
            self.assertIn('ValueError', result['error'])

    @patch('capture_playtest.health', return_value={'ready': True, 'native_backend': 'breeze'})
    def test_wrong_candidate_is_rejected_before_launch(self, _health):
        with tempfile.TemporaryDirectory() as folder:
            config = self.fixture(folder)
            Path(config['mod_pack']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'validated candidate'):
                capture_playtest.run(config)
            self.assertFalse((Path(folder)/'runs').exists())


if __name__ == '__main__':
    unittest.main()
