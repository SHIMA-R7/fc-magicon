"""Measured narrow-band C6 microphone noise suppression; no auto loudness.

The streaming filter uses only Python's standard library. The measurement
profile is specific to this C6 / 16 kHz ADC / 460800-baud recording setup.
"""
import json
import math
from pathlib import Path

PROFILE = Path(__file__).with_name('mic_noise_profile.json')

class MicNoiseFilter:
    def __init__(self, rate=16000, profile=PROFILE):
        p = json.loads(Path(profile).read_text(encoding='utf-8'))
        if rate != p['rate']:
            raise ValueError('Noise filter profile sample rate mismatch')
        self.profile = p
        self.stages = []
        for tone in p['tones']:
            f, bw = tone['hz'], tone['bandwidth_hz']
            if not 0 < f < rate/2 or not 0 < bw < rate/2:
                raise ValueError('Invalid noise notch')
            g = 1/(1+math.tan(math.pi*bw/rate))
            b0, b1, b2 = g, -2*g*math.cos(2*math.pi*f/rate), g
            self.stages.append([b0, b1, b2, b1, 2*g-1, 0., 0.])

    def process(self, values):
        out = list(values)
        for s in self.stages:
            b0,b1,b2,a1,a2,z1,z2 = s
            for i,x in enumerate(out):
                y = b0*x+z1
                z1 = b1*x-a1*y+z2
                z2 = b2*x-a2*y
                out[i] = y
            s[5],s[6] = z1,z2
        return out
