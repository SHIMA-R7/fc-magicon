"""Regression checks against actual firmware and synthetic inputs.

PIO timing and continuous A12 sampling need separate verification.
"""
from pathlib import Path
import contextlib
import io
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    zig = next(Path(r'C:\Users\Yugo\pico\zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='fc-cart-audit-') as folder:
        exe = Path(folder) / 'audit.exe'
        subprocess.run([str(zig), 'cc', '-O0', '-std=gnu11',
                        '-I' + str(ROOT / 'sim'), '-I' + str(ROOT / 'chr_test'),
                        str(ROOT / 'tests/audit_cart.c'), '-o', str(exe)],
                       check=True, timeout=120)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        expected = ['t coarse X=5', 'protected WRAM=19', 'four-screen rejected', 'bank=0']
        for token in expected:
            assert token in result.stdout, result.stdout
        print(result.stdout, end='')
        result = subprocess.run([str(exe), 'empty'], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and 'empty NSF rejected' in result.stdout, result.stderr
        print(result.stdout, end='')
    sys.path.insert(0, str(ROOT / 'tools'))
    import nes_pack
    with contextlib.redirect_stdout(io.StringIO()):
        assert nes_pack.check('short.nes', b'NES\x1a') is False
        assert nes_pack.check('short.nsf', b'NESM\x1a') is False
    print('PASS: short headers rejected without exception')

if __name__ == '__main__':
    main()
