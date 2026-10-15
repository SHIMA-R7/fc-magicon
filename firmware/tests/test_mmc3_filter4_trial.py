"""Diagnostic comparison, not MMC3 compliance: reject an eight-dot low pulse.

Three falling edges can fit an eight-PPU-dot low interval at some M2 phases.
This does not establish that the real console's extra clocks are such pulses.
"""
from pathlib import Path
from test_pio_logic import run
root=Path(__file__).resolve().parents[1]/'magicon'
normal=root/'mmc3_a12.pio'; trial=root/'mmc3_a12_filter4_experiment.pio'
accepted3=0
for phase in range(140):
    def border(t):
        return ((1<<25) if (t+phase)%140<84 else 0)|((1<<38) if t%744>=372 else 0)
    accepted3+=bool(run(normal,border,base=25,jmp_pin=38,steps=3000)[1])
    assert not run(trial,border,base=25,jmp_pin=38,steps=3000)[1],phase
    def long(t):
        return ((1<<25) if (t+phase)%140<84 else 0)|((1<<38) if 1000<=t<1200 else 0)
    assert len(run(trial,long,base=25,jmp_pin=38,steps=1400)[1])==1,phase
assert accepted3
print(f'PASS diagnostic filter4: eight-dot lows rejected at all phases; long low passes; filter3 accepts in {accepted3}/140 phase cases')
