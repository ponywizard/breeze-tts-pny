"""Verify bounded streaming conversion against the audition's independent DSP."""
from array import array
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
from breeze_pny.playback import RationalPCM


class Playback(unittest.TestCase):
    def test_chunk_boundaries_do_not_change_pcm_and_memory_stays_bounded(self):
        rng = random.Random(42)
        values = array('h', [rng.randrange(-16000, 16001) for _ in range(12037)])
        if sys.byteorder != 'little': values.byteswap()
        source = values.tobytes()
        for up, down in [(4, 5), (5, 4)]:
            expected = RationalPCM(up, down).process(source, final=True)
            for size in [2, 14, 1024, 4096]:
                converter = RationalPCM(up, down)
                chunks = []
                for at in range(0, len(source), size):
                    chunks.append(converter.process(source[at:at + size]))
                    self.assertLess(len(converter.buffer), 40)
                chunks.append(converter.process(b'', final=True))
                self.assertEqual(b''.join(chunks), expected)
                self.assertEqual(len(expected) // 2, (len(values) * up + down - 1) // down)

    def test_matches_scipy_lab_filter(self):
        try:
            import numpy as np
            from scipy.signal import resample_poly
        except ImportError:
            self.skipTest('SciPy is a development oracle, not a runtime requirement')
        rng = np.random.default_rng(24)
        for n in [1, 2, 12, 13, 37, 509, 24000]:
            values = rng.integers(-16000, 16001, n, dtype=np.int16)
            for up, down in [(4, 5), (5, 4)]:
                expected = np.rint(resample_poly(values.astype(float), up, down, window=('kaiser', 10))).astype('<i2').tobytes()
                actual = RationalPCM(up, down).process(values.astype('<i2').tobytes(), final=True)
                self.assertEqual(actual, expected)

    def test_bad_alignment_and_reuse_are_rejected(self):
        converter = RationalPCM(4, 5)
        with self.assertRaises(ValueError): converter.process(b'x')
        converter.process(b'\0\0' * 30, final=True)
        with self.assertRaises(ValueError): converter.process(b'\0\0')


if __name__ == '__main__': unittest.main()
