"""PIO control flow only: bank-pointer address, offset, A13 exclusion and late data.

This does not model the DMA sniffer pipeline's latency or electrical margins.
"""
from pathlib import Path
from test_pio_logic import run

pio = Path(__file__).resolve().parents[1] / 'magicon/ppu_banked.pio'
table = 0x20001000


def waveform(address):
    def levels(t):
        rd = (1 << 40) if t < 30 or t >= 170 else 0
        # Shared AD pins stop carrying the address after /RD goes low.
        a = address if t < 30 else (address & ~255) | 0xf0
        return rd | ((a & 0x1fff) << 26) | ((1 << 42) if address & 0x2000 else 0)
    return levels


for bank in range(8):
    for offset in [0, 1, 7, 8, 15, 31, 127, 255, 256, 511, 512, 1023]:
        a = bank * 1024 + offset
        out = []
        driven, _, _, values = run(pio, waveform(a), reply_at=[0, 100],
            reply=[table >> 5, 0x55], base=26, jmp_pin=40, steps=210, data_out=out)
        assert values == [offset, table + bank*4], (a, values)
        assert driven and all(mask == 255 for _, mask in driven)
        assert out[0][1] == 0x55

assert not run(pio, waveform(0x2345), reply_at=0, reply=table >> 5,
               base=26, jmp_pin=40, steps=210)[3]
assert not run(pio, waveform(0x345), reply_at=[0,190], reply=[table >> 5,0xaa],
               base=26, jmp_pin=40, steps=230)[0]
print('PASS banked PPU: 96 addresses, stale AD exclusion, nametable isolation, late reply stays input')
