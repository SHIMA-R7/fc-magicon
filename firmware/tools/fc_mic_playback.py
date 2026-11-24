"""Bounded-memory PC WAV -> cartridge's native 7-bit / ~8 kHz DAC stream."""
from collections import deque
import json
import math
from pathlib import Path
import struct
import wave

def latest_recording(folder):
    for meta in sorted(Path(folder).glob('mic-*.json'), reverse=True):
        try:
            if not json.loads(meta.read_text(encoding='utf-8')).get('complete'): continue
            base=meta.with_suffix('')
            clean=base.with_name(base.name+'-clean').with_suffix('.wav')
            original=base.with_suffix('.wav')
            if clean.exists(): return clean
            if original.exists(): return original
        except (OSError, ValueError): continue
    return None

class PlaybackSource:
    def __init__(self, path, gain=4.0):
        if not math.isfinite(gain) or not 0<gain<=16:
            raise ValueError('Playback gain must be finite and in (0, 16]')
        self.gain=gain
        self.path=Path(path); self.wav=wave.open(str(path),'rb')
        if (self.wav.getframerate(),self.wav.getnchannels(),self.wav.getsampwidth())!=(16000,1,2):
            self.wav.close(); raise ValueError('Replay requires a 16 kHz mono 16-bit WAV')
        self.total=(self.wav.getnframes()+1)//2
        if not 0<self.total<0x80000000:
            self.wav.close(); raise ValueError('Empty or excessively long replay')
        self.sent=0; self.ready=False; self.ended=False; self.iterator=self.convert()

    def convert(self):
        # 31-tap windowed-sinc anti-alias filter before decimation by two.
        taps=[]
        for i in range(31):
            x=i-15; fc=3400/16000
            v=2*fc if x==0 else math.sin(2*math.pi*fc*x)/(math.pi*x)
            taps.append(v*(.54-.46*math.cos(2*math.pi*i/30)))
        norm=sum(taps); taps=[v/norm for v in taps]
        history=deque([0.]*31,maxlen=31); index=out=0
        while True:
            raw=self.wav.readframes(2048)
            if not raw: break
            for (value,) in struct.iter_unpack('<h',raw):
                history.appendleft(value)
                if not index%2:
                    sample=sum(a*b for a,b in zip(taps,history))
                    envelope=max(0,min(1,out/40,(self.total-1-out)/40))
                    level=sample*self.gain/32768
                    # Linear up to 75% of DAC span; smoothly limit larger peaks.
                    if abs(level)>.75:
                        level=math.copysign(.75+.25*math.tanh((abs(level)-.75)/.25),level)
                    yield max(0,min(127,64+round(63*level*envelope)))
                    out+=1
                index+=1

    def take(self, count):
        count=min(count,self.total-self.sent)
        data=bytes(next(self.iterator) for _ in range(count))
        offset=self.sent;self.sent+=count
        return struct.pack('<I',offset)+data

    def close(self): self.wav.close()
