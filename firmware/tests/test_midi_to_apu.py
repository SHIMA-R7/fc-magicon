"""Musical timing and APU write regressions; uses synthetic MIDI only."""
import sys
import unittest
from pathlib import Path

import mido

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from midi_to_apu import compile_midi, timer


def midi(messages):
    song = mido.MidiFile(ticks_per_beat=480)
    song.tracks.append(mido.MidiTrack(messages))
    return song


class MidiToApuTests(unittest.TestCase):
    def test_sustain_and_final_silence(self):
        song = midi([
            mido.Message('note_on', note=69, velocity=127),
            mido.Message('control_change', control=64, value=127, time=240),
            mido.Message('note_off', note=69, time=240),
            mido.Message('control_change', control=64, value=0, time=480),
        ])
        records, _ = compile_midi(song)
        self.assertGreater(records[40][0] & 15, 0)
        self.assertEqual(records[61][0] & 15, 0)
        self.assertEqual(records[-1][6], 0x80)
        self.assertEqual(records[-1][0] & 15, 0)
        # Constant pitch must not reset the pulse sequencer every frame.
        self.assertEqual(int.from_bytes(records[10][12:], 'little') & 4, 0)

    def test_tempo_and_offset(self):
        song = midi([
            mido.MetaMessage('set_tempo', tempo=1000000),
            mido.Message('note_on', note=72, velocity=90),
            mido.Message('note_off', note=72, time=480),
        ])
        records, _ = compile_midi(song, offset=1)
        self.assertEqual(records[30][0] & 15, 0)
        self.assertGreater(records[100][0] & 15, 0)
        self.assertEqual(records[121][0] & 15, 0)

    def test_repeated_note_retriggers_and_timer(self):
        self.assertEqual(timer(69), 253)
        song = midi([
            mido.Message('note_on', note=69, velocity=100),
            mido.Message('note_off', note=69, time=480),
            mido.Message('note_on', note=69, velocity=100),
            mido.Message('note_off', note=69, time=480),
        ])
        records, _ = compile_midi(song)
        self.assertTrue(int.from_bytes(records[30][12:], 'little') & 4)


if __name__ == '__main__':
    unittest.main()
