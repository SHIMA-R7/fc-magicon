"""Offline synthetic-audio tests; never uses personal recordings or hardware."""
from pathlib import Path
import json
import math
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from fc_mic_denoise import MicNoiseFilter
from fc_mic_playback import PlaybackSource, latest_recording
from record_fc_mic import decode, fnv, upload


class AudioTests(unittest.TestCase):
    def test_packet_integrity(self):
        payload = b'\x00\x08\xff\x0f'
        head = struct.pack('<4scHI', b'M2PK', b'D', len(payload), 12)
        tail = struct.pack('<I', fnv(payload, fnv(head)))
        self.assertEqual(decode(head, payload, tail), (b'D', 12, payload))
        with self.assertRaises(RuntimeError):
            decode(head, b'\x01' + payload[1:], tail)
        class Sink:
            def write(self, value): self.data = value
        sink = Sink()
        upload(sink, b'D', payload)
        self.assertEqual(sink.data[:7], struct.pack('<4scH', b'M2UP', b'D', 4))
        self.assertEqual(struct.unpack('<I', sink.data[-4:])[0], fnv(sink.data[:-4]))

    def test_filter_stream_continuity(self):
        samples = [math.sin(2*math.pi*200*i/16000) +
                   .3*math.sin(2*math.pi*5056*i/16000) for i in range(16000)]
        expected = MicNoiseFilter().process(samples)
        f = MicNoiseFilter()
        actual = []
        for i in range(0, len(samples), 137):
            actual.extend(f.process(samples[i:i+137]))
        self.assertEqual(actual, expected)

    def test_odd_wav_and_latest_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mic-001.wav'
            samples = [round(12000*math.sin(2*math.pi*440*i/16000)) for i in range(3201)]
            with wave.open(str(path), 'wb') as w:
                w.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                w.writeframes(struct.pack('<'+'h'*len(samples), *samples))
            source = PlaybackSource(path)
            result = bytearray()
            while source.sent < source.total:
                chunk = source.take(113)
                self.assertEqual(struct.unpack('<I', chunk[:4])[0], len(result))
                result.extend(chunk[4:])
            source.close()
            self.assertEqual(len(result), 1601)
            self.assertLessEqual(max(result), 127)
            self.assertEqual((result[0], result[-1]), (64, 64))
            path.with_suffix('.json').write_text(json.dumps({'complete': True}))
            (Path(folder)/'mic-002.json').write_text(json.dumps({'complete': False}))
            self.assertEqual(latest_recording(folder), path)
            clean = path.with_name('mic-001-clean.wav')
            clean.write_bytes(path.read_bytes())
            self.assertEqual(latest_recording(folder), clean)


if __name__ == '__main__':
    unittest.main()
