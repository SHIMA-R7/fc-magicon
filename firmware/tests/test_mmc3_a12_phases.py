"""Ideal input waveforms only; does not model electrical glitches or FIFO latency."""
from pathlib import Path
from test_pio_logic import run
pio=Path(__file__).resolve().parents[1]/'magicon/mmc3_a12.pio'
for phase in range(140):
    def short(t):
        return ((1<<25) if (t+phase)%140<84 else 0)|((1<<38) if t%372>=186 else 0)
    assert not run(pio,short,base=25,jmp_pin=38,steps=2000)[1],phase
    def long(t):
        return ((1<<25) if (t+phase)%140<84 else 0)|((1<<38) if 1000<=t<1200 else 0)
    assert len(run(pio,long,base=25,jmp_pin=38,steps=1400)[1])==1,phase
print('PASS M2 qualifier across 140 phases: short pulses rejected, long low clocks once')
