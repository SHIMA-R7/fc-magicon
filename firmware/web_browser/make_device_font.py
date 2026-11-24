"""Generate a private CP932 bitmap font from a locally installed font.

The generated header contains font-derived glyphs. Do not redistribute it.
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

p = argparse.ArgumentParser()
p.add_argument('output', type=Path)
p.add_argument('--font', default='C:/Windows/Fonts/meiryo.ttc')
a = p.parse_args()
font = ImageFont.truetype(a.font, 12)
keys = list(range(32, 127)) + list(range(0xA1, 0xE0))
for lead in list(range(0x81, 0xA0)) + list(range(0xE0, 0xFD)):
    for trail in range(0x40, 0xFD):
        try:
            bytes((lead, trail)).decode('cp932')
            keys.append((lead << 8) | trail)
        except UnicodeDecodeError:
            pass
rows = []
for key in keys:
    raw = bytes((key,)) if key < 256 else bytes((key >> 8, key & 255))
    image = Image.new('L', (12, 14))
    ImageDraw.Draw(image).text((0, -2), raw.decode('cp932'), font=font, fill=255)
    data = list(image.tobytes())
    rows.append([sum((1 << (11-x)) for x in range(12) if data[y*12+x] >= 112) for y in range(14)])
a.output.parent.mkdir(parents=True, exist_ok=True)
with a.output.open('w', encoding='ascii') as f:
    f.write('// Generated from a local font; not for redistribution.\n#pragma once\n#include <stdint.h>\n')
    f.write('static const uint16_t web_font_keys[]={'+','.join(map(str, keys))+'};\n')
    f.write('static const uint16_t web_font_rows[][14]={\n')
    for row in rows:
        f.write('{'+','.join(map(str,row))+'},\n')
    f.write('};\n')
print('Generated', len(keys), 'glyphs, bitmap bytes', len(keys)*28)
