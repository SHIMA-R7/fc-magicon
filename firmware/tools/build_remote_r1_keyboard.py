"""Preserve confirmed RP firmware byte-for-byte, replace only its 6502 ROM.

No device access. The original UF2 and original generated ROM must match.
"""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'out-standalone-video/remote-desktop-usb-a9-gpio39-20261017-r1-confirmed.uf2'
OUT = ROOT / 'out-standalone-video/remote-desktop-usb-r1-keyboard-20261018.uf2'
EXPECTED = 'd1519162bc985604b754ef6880487e6870d1567da0e1b5374fb4f67c7b884899'

def main():
    original = BASE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == EXPECTED
    blocks = [bytearray(original[i:i+512]) for i in range(0, len(original), 512)]
    memory = {}
    for b in blocks:
        assert len(b) == 512
        assert struct.unpack_from('<II', b) == (0x0a324655, 0x9e5d5157)
        assert struct.unpack_from('<I', b, 508)[0] == 0x0ab16f30
        addr, n = struct.unpack_from('<II', b, 12)
        assert n == 256 and struct.unpack_from('<I', b, 8)[0] in (0x2000, 0xa000)
        for j, value in enumerate(b[32:32+n]):
            assert addr+j not in memory
            memory[addr+j] = value
    low, high = min(memory), max(memory)+1
    image = bytes(memory.get(a, 255) for a in range(low, high))
    with tempfile.TemporaryDirectory(prefix='remote-r1-keyboard-') as temp:
        plain = Path(temp)/'plain.h'
        keyboard = Path(temp)/'keyboard.h'
        generator = ROOT/'standalone_video/gen_video_driver.py'
        subprocess.run([sys.executable, str(generator), str(plain)], check=True)
        subprocess.run([sys.executable, str(generator), str(keyboard), '--desktop-keyboard'], check=True)
        old = plain.with_suffix('.bin').read_bytes()
        new = keyboard.with_suffix('.bin').read_bytes()
    assert len(old) == len(new) == 16384 and image.count(old) == 1
    start = low + image.index(old)
    changed = 0
    for b in blocks:
        addr, n = struct.unpack_from('<II', b, 12)
        for j in range(n):
            a = addr+j
            if start <= a < start+len(new):
                value = new[a-start]
                changed += b[32+j] != value
                b[32+j] = value
    result = b''.join(blocks)
    # Both ARM code and all UF2 metadata must remain exactly as in confirmed r1.
    rebuilt = dict(memory)
    for b in blocks:
        addr, n = struct.unpack_from('<II', b, 12)
        for j, value in enumerate(b[32:32+n]):
            if not start <= addr+j < start+len(new):
                assert value == memory[addr+j]
            rebuilt[addr+j] = value
    assert bytes(rebuilt[start+j] for j in range(len(new))) == new
    OUT.write_bytes(result)
    report = dict(base_sha256=EXPECTED, sha256=hashlib.sha256(result).hexdigest(),
                  rom_address=hex(start), rom_length=len(new), changed_payload_bytes=changed,
                  rp_firmware_outside_rom_identical=True, device_written=False,
                  hardware_playback_confirmed=False)
    OUT.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(OUT)
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
