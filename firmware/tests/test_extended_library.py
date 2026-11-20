"""Compile actual cart.c and check large MMC3 storage plus menu selection.

Optional arguments are private, locally dumped .nes files; none are bundled.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    zig = shutil.which("zig") or next(Path("C:/Users/Yugo/pico/zig").rglob("zig.exe"))
    with tempfile.TemporaryDirectory(prefix="fc-extended-") as folder:
        exe = Path(folder) / "audit.exe"
        for profile in (["-DFC_GAME_BANKED_DMA=1"],
                        ["-DFC_GAME_PROVEN_MMC3=1", "-DFC_DIAG_CPU_ONLY=1",
                         "-DFC_DIAG_NROM_GAME=1", "-DFC_DIAG_MMC3_GAME=1"],
                        ["-DFC_GAME_PROVEN_MMC3=1", "-DFC_DIAG_CPU_ONLY=1",
                         "-DFC_DIAG_NROM_GAME=1", "-DFC_DIAG_MMC3_GAME=1", "-DFC_GAME_PRG_SRAM=1"]):
            subprocess.run([str(zig), "cc", "-O2", "-std=gnu11",
                        "-DFC_GAME_FAST_NROM=1", *profile,
                        "-I" + str(ROOT / "sim"), "-I" + str(ROOT / "chr_test"),
                        str(ROOT / "tests/audit_extended_library.c"), "-o", str(exe)],
                       check=True, timeout=120)
            subprocess.run([str(exe), *sys.argv[1:]], check=True, timeout=30)


if __name__ == "__main__":
    main()
