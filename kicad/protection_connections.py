"""Extract confirmed header/GPIO mapping; do not regenerate the ordered PCB."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT / 'gen_schematic.py').read_text(encoding='utf-8-sig')
namespace = {}
exec(source[source.index('def _gpio_header'):source.index('def hdr_pin')], namespace)
exec(source[source.index('GPIO = {}'):source.index('# J1 カセット端子')], namespace)
signals = namespace['GPIO']
signal_index = 0
rows = []
for header in ['P1', 'P2', 'P3', 'P4']:
    for pin, name in enumerate(namespace[f'{header}_NAMES'], 1):
        gpio = int(name[4:]) if name.startswith('GPIO') and name[4:].isdigit() else None
        if gpio in signals:
            chip, channel = divmod(signal_index, 8)
            rows.append([header, pin, gpio, signals[gpio], f'U{chip+1}', channel+1, 'base A -> switch -> module B'])
            signal_index += 1
        else:
            action = 'NC on base; preserve original' if name in ['GPIO39', 'GPIO47_PSRAM_CS', 'ADC_VREF', '3V3_EN'] else 'direct-through'
            rows.append([header, pin, gpio if gpio is not None else '', name, '', '', action])
assert signal_index == 46
assert {int(r[2]) for r in rows if r[4]} == set(range(47)) - {39}
target = ROOT.parent / 'docs' / 'protection_connections.csv'
with target.open('w', encoding='utf-8-sig', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['socket', 'socket_pin', 'GPIO', 'signal', 'switch', 'channel', 'connection'])
    writer.writerows(rows)
print(f'46 signals mapped: {target}')
