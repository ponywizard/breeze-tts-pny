"""Bounded PCM varispeed matching SciPy resample_poly, without runtime packages.

The fixed 101-tap firwin(cutoff=1/5, window=(kaiser, 10)) coefficients are the
reviewed lab filter before its per-converter upsampling gain. Float literals
round-trip the original float64 values. Tests compare both 4/5 and 5/4 paths
with SciPy and the captured audition PCM. Pitch and timing change together.
"""
from array import array
import sys

_KERNEL = (
    -2.7688640806249105e-21,
    -3.069762853829796e-06,
    -9.311872128531522e-06,
    -1.567369393456718e-05,
    -1.5227244164928752e-05,
    4.276181596058217e-20,
    3.2919979159177094e-05,
    7.467861200986299e-05,
    0.00010221480157837373,
    8.473232054896153e-05,
    -1.8616293445928647e-19,
    -0.00014500094974784108,
    -0.0003005248659662894,
    -0.0003803529977217772,
    -0.0002943108338622406,
    5.321560592460991e-19,
    0.0004483308450487448,
    0.0008840265159154254,
    0.0010691922767204372,
    0.0007936345489050555,
    -1.1838669221862577e-18,
    -0.0011232818131570797,
    -0.0021437941929291302,
    -0.002515597068825813,
    -0.0018156249885075677,
    2.199031754729939e-18,
    0.002444181471118736,
    0.004561983154188162,
    0.005244470749778716,
    0.003714720793096119,
    -3.538407763652802e-18,
    -0.004841315361410918,
    -0.008914735882788813,
    -0.01012984364231325,
    -0.007106467091416712,
    5.039474817233556e-18,
    0.009148313580166009,
    0.016810063272491082,
    0.01912351414332366,
    0.013483803017593917,
    -6.4372893839315525e-18,
    -0.017806067551500337,
    -0.0334896870993756,
    -0.039390930652151705,
    -0.029117473521120346,
    7.434352422168557e-18,
    0.04537382168619657,
    0.09920030428995753,
    0.15022044581553445,
    0.1867430293991846,
    0.19999981962672334,
    0.1867430293991846,
    0.15022044581553445,
    0.09920030428995753,
    0.04537382168619657,
    7.434352422168557e-18,
    -0.029117473521120346,
    -0.039390930652151705,
    -0.0334896870993756,
    -0.017806067551500337,
    -6.4372893839315525e-18,
    0.013483803017593917,
    0.01912351414332366,
    0.016810063272491082,
    0.009148313580166009,
    5.039474817233556e-18,
    -0.007106467091416712,
    -0.01012984364231325,
    -0.008914735882788813,
    -0.004841315361410918,
    -3.538407763652802e-18,
    0.003714720793096119,
    0.005244470749778716,
    0.004561983154188162,
    0.002444181471118736,
    2.199031754729939e-18,
    -0.0018156249885075677,
    -0.002515597068825813,
    -0.0021437941929291302,
    -0.0011232818131570797,
    -1.1838669221862577e-18,
    0.0007936345489050555,
    0.0010691922767204372,
    0.0008840265159154254,
    0.0004483308450487448,
    5.321560592460991e-19,
    -0.0002943108338622406,
    -0.0003803529977217772,
    -0.0003005248659662894,
    -0.00014500094974784108,
    -1.8616293445928647e-19,
    8.473232054896153e-05,
    0.00010221480157837373,
    7.467861200986299e-05,
    3.2919979159177094e-05,
    4.276181596058217e-20,
    -1.5227244164928752e-05,
    -1.567369393456718e-05,
    -9.311872128531522e-06,
    -3.069762853829796e-06,
    -2.7688640806249105e-21,
)


class RationalPCM:
    def __init__(self, up, down):
        if (up, down) not in [(4, 5), (5, 4)]:
            raise ValueError('Unsupported playback ratio')
        self.up, self.down = up, down
        self.kernel = tuple(v * up for v in _KERNEL)
        self.buffer = []
        self.start = self.inputs = self.outputs = 0
        self.finished = False

    def process(self, pcm, final=False):
        if self.finished or len(pcm) % 2:
            raise ValueError('Invalid PCM or finished converter')
        values = array('h', pcm)
        if sys.byteorder != 'little':
            values.byteswap()
        self.buffer.extend(values)
        self.inputs += len(values)
        end = ((self.inputs * self.up + self.down - 1) // self.down if final else
               max(0, (self.inputs * self.up - 51) // self.down + 1))
        rendered = array('h')
        for index in range(self.outputs, end):
            center = self.down * index + 50
            low = max(0, (center - 100 + self.up - 1) // self.up)
            high = min(self.inputs - 1, center // self.up)
            total = 0.0
            for source in range(low, high + 1):
                total += self.buffer[source - self.start] * self.kernel[center - source * self.up]
            value = round(total)
            if not -32768 <= value <= 32767:
                raise RuntimeError('Playback conversion would clip')
            rendered.append(value)
        self.outputs = end
        keep = max(0, (self.down * end - 50 + self.up - 1) // self.up)
        self.buffer = self.buffer[keep - self.start:]
        self.start = keep
        self.finished = final
        if sys.byteorder != 'little':
            rendered.byteswap()
        return rendered.tobytes()


class Playback125(RationalPCM):
    def __init__(self):
        super().__init__(4, 5)
