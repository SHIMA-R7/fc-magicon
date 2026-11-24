"""Record the controller-2 microphone to PC WAV files; 2P A starts/stops.

Requires pyserial. C6 UART is opened at 115200 then explicitly switches to
460800 while armed. Raw 12-bit ADC data is also retained for analysis.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import struct
import time
import wave
import serial
from fc_mic_denoise import MicNoiseFilter
from fc_mic_playback import PlaybackSource, latest_recording

def fnv(data, h=2166136261):
    for b in data:
        h = ((h ^ b) * 16777619) & 0xffffffff
    return h

def upload(port, kind, payload=b''):
    header=struct.pack('<4scH',b'M2UP',kind,len(payload))
    port.write(header+payload+struct.pack('<I',fnv(payload,fnv(header))))

def decode(header, payload, tail):
    magic, kind, length, seq = struct.unpack('<4scHI', header)
    if magic != b'M2PK' or length != len(payload) or length > 2048:
        raise RuntimeError('Invalid recording packet dimensions')
    if struct.unpack('<I', tail)[0] != fnv(payload, fnv(header)):
        raise RuntimeError('Recording checksum mismatch')
    return kind, seq, payload

class Link:
    def __init__(self, port):
        self.port = port
        self.last_keepalive = 0
        self.seq = 0

    def keepalive(self):
        if time.monotonic() - self.last_keepalive > .4:
            self.port.write(b'K')
            self.last_keepalive = time.monotonic()

    def exact(self, n):
        result = bytearray()
        deadline = time.monotonic() + 2
        while len(result) < n:
            self.keepalive()
            chunk = self.port.read(n-len(result))
            result.extend(chunk)
            if time.monotonic() > deadline:
                raise RuntimeError('Recording packet timed out')
        return bytes(result)

    def packet(self):
        self.keepalive()
        first = self.port.read(1)
        if not first:
            return None
        header = first + self.exact(10)
        if header[:4] != b'M2PK':
            raise RuntimeError('Unexpected bytes in recording stream')
        n = struct.unpack_from('<H', header, 5)[0]
        if n > 2048:
            raise RuntimeError('Recording packet too large')
        kind, seq, data = decode(header, self.exact(n), self.exact(4))
        if seq != self.seq:
            raise RuntimeError(f'Recording sequence gap: {self.seq} -> {seq}')
        self.seq += 1
        return kind, data

class Recording:
    def __init__(self, folder, meta):
        if meta != dict(rate=16000, format='u12le', channels=1):
            raise RuntimeError('Unsupported ADC recording format')
        folder.mkdir(parents=True, exist_ok=True)
        self.stem = folder / ('mic-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        self.wav_path = self.stem.with_suffix('.partial.wav')
        self.raw = self.stem.with_suffix('.u16le').open('xb')
        self.wav = wave.open(str(self.wav_path), 'wb')
        self.wav.setnchannels(1); self.wav.setsampwidth(2); self.wav.setframerate(16000)
        self.clean_path = self.stem.with_suffix('.partial-clean.wav')
        self.clean = wave.open(str(self.clean_path), 'wb')
        self.clean.setnchannels(1); self.clean.setsampwidth(2); self.clean.setframerate(16000)
        self.noise_filter = MicNoiseFilter()
        self.meta = meta
        self.n = self.sum = self.clipped = 0
        self.lo, self.hi = 4095, 0
        self.previous = None
        self.filtered = 0.
        print('RECORDING:', self.wav_path, flush=True)

    def data(self, raw):
        if len(raw) % 2:
            raise RuntimeError('Odd ADC data size')
        values = struct.unpack('<' + 'H' * (len(raw)//2), raw)
        if any(v > 4095 for v in values):
            raise RuntimeError('ADC data outside 12-bit range')
        self.raw.write(raw)
        pcm = bytearray()
        centered = []
        for v in values:
            self.n += 1; self.sum += v
            self.lo = min(self.lo, v); self.hi = max(self.hi, v)
            self.clipped += v <= 4 or v >= 4091
            if self.previous is None:
                self.previous = v
            # Fixed gain, DC-removal high-pass (~13 Hz); no auto normalization.
            self.filtered = v - self.previous + .995 * self.filtered
            self.previous = v
            centered.append(self.filtered*16)
            pcm.extend(struct.pack('<h', max(-32768, min(32767, round(self.filtered*16)))))
        self.wav.writeframesraw(pcm)
        cleaned = self.noise_filter.process(centered)
        self.clean.writeframesraw(b''.join(struct.pack('<h', max(-32768, min(32767, round(v)))) for v in cleaned))

    def finish(self, end=None):
        self.wav.close(); self.raw.close(); self.clean.close()
        complete = bool(end and end.get('samples') == self.n and
                        end.get('overflow') == 0 and end.get('reason') == 'button')
        meta = dict(self.meta, samples=self.n, seconds=self.n/16000,
                    mean_raw=self.sum/self.n if self.n else None,
                    min_raw=self.lo, max_raw=self.hi, clipped=self.clipped,
                    wav_gain=16, highpass_hz=13, complete=complete, end=end,
                    noise_filter=self.noise_filter.profile)
        self.stem.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        if complete:
            target = self.stem.with_suffix('.wav')
            self.wav_path.rename(target); self.wav_path = target
            target_clean = self.stem.with_name(self.stem.name+'-clean').with_suffix('.wav')
            self.clean_path.rename(target_clean); self.clean_path = target_clean
        print('SAVED:', self.wav_path, 'seconds=', round(self.n/16000, 2),
              'complete=', complete, 'clipped=', self.clipped, flush=True)
        print('NOISE REDUCED:', self.clean_path, flush=True)
        if end and (end.get('samples') != self.n or end.get('overflow')):
            raise RuntimeError('ADC sample loss: kept as partial recording')

def run(port_name, folder, replay_source=None, playback_gain=4.0):
    p = serial.Serial(); p.port = port_name; p.baudrate = 115200; p.timeout = .05
    p.dtr = p.rts = False
    rec = None
    playback = None
    with p:
        p.reset_input_buffer(); p.write(b'\x03MIC2 ARM\n'); p.flush()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            line = p.readline()
            if line.startswith(b'MIC1 ERROR'):
                if b'bridge_busy' in line:
                    time.sleep(.15)
                    p.write(b'\x03MIC2 ARM\n'); p.flush()
                    continue
                raise RuntimeError(line.decode().strip())
            if line.strip() == b'MIC2 BAUD 460800':
                break
        else:
            raise RuntimeError('C6 did not arm the microphone recorder')
        p.baudrate = 460800
        link = Link(p)

        closed = False
        def consume(item):
            nonlocal rec, closed, playback
            if item is None: return False
            kind, data = item
            if kind == b'R': print('READY: 2P A records/stops; 2P B replays/stops the latest recording.', flush=True)
            elif kind == b'B':
                if rec is not None: raise RuntimeError('Duplicate recording start')
                rec = Recording(folder, json.loads(data))
            elif kind == b'D':
                if rec is None: raise RuntimeError('ADC data without recording start')
                rec.data(data)
            elif kind == b'E':
                if rec is None: raise RuntimeError('Recording end without start')
                closing, rec = rec, None
                closing.finish(json.loads(data))
                print('READY: press 2P A for another recording.', flush=True)
            elif kind == b'P':
                if playback: playback.close(); playback=None
                path=replay_source or latest_recording(folder)
                if path is None:
                    print('NO RECORDING YET',flush=True);upload(p,b'X')
                else:
                    playback=PlaybackSource(path,playback_gain)
                    upload(p,b'S',struct.pack('<I',playback.total))
                    print('DAC PLAYBACK:',path,'samples=',playback.total,'gain=',playback_gain,flush=True)
            elif kind == b'C':
                if len(data)!=7:raise RuntimeError('Invalid playback credit')
                consumed,free,state=struct.unpack('<IHB',data)
                if state==10:
                    print('DAC AUDIT: writes=',consumed,'min=',free&255,'max=',free>>8,flush=True)
                elif state==11:
                    print('DAC AUDIT: mismatches=',consumed,'last_actual=',free&255,'last_expected=',free>>8,flush=True)
                if playback:
                    if state==1: playback.ready=True
                    if playback.ready and state in (1,2):
                        if consumed>playback.sent:raise RuntimeError('Playback acknowledgement exceeds upload')
                        available=8192-(playback.sent-consumed)
                        count=min(512,available,playback.total-playback.sent)
                        if count:upload(p,b'D',playback.take(count))
                        if playback.sent==playback.total and not playback.ended:
                            upload(p,b'E');playback.ended=True
            elif kind == b'L':
                if playback:playback.close();playback=None
                print('DAC PLAYBACK END:',data.decode(errors='replace'),flush=True)
            elif kind == b'X': raise RuntimeError('C6 ADC error: ' + data.decode())
            elif kind == b'Q':
                closed = True
                return True
            else: raise RuntimeError('Unknown recording packet type')
            return False

        try:
            while not consume(link.packet()): pass
        except KeyboardInterrupt:
            p.write(b'Q'); p.flush()
            end = time.monotonic() + 2
            while time.monotonic() < end:
                if consume(link.packet()): break
        finally:
            try:
                if not closed: p.write(b'Q'); p.flush()
            finally:
                if rec is not None: rec.finish()
                if playback is not None: playback.close()

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', required=True)
    ap.add_argument('--outdir', type=Path, required=True)
    ap.add_argument('--replay-source', type=Path, help='Diagnostic override; leaves the latest recording unchanged')
    ap.add_argument('--playback-gain', type=float, default=4.0)
    args = ap.parse_args()
    run(args.port, args.outdir, args.replay_source, args.playback_gain)
