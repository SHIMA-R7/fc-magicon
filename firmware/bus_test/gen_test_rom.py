"""bus_test 用の 16KB テスト ROM(6502)を作り、test_rom.h に書き出す。
    python gen_test_rom.py
  $C000(16KB を $8000 と $C000 に鏡映)から:
    ・PPU の表示を止める($2000/$2001 = 0)
    ・矩形波 1ch: 50% デューティ、長さカウンタ停止、固定音量 15、周期 $0FD(≈440Hz)
    ・ループ: $00 を増やして $8000 へ書く(RP2350B が数えて LED を点滅させる)
  アセンブラは使わず、命令ごとにバイト列を書く(番地は下の asm() が計算して確かめる)。
"""
import os

ORG = 0xC000
prog = []      # (ラベル or None, バイト列, 説明)


def op(b, note, label=None):
    prog.append((label, list(b), note))      # None はあとで番地を入れる所


op([0x78], "SEI", "reset")
op([0xD8], "CLD")
op([0xA2, 0xFF], "LDX #$FF")
op([0x9A], "TXS")
op([0xA9, 0x00], "LDA #$00")
op([0x8D, 0x00, 0x20], "STA $2000   ; NMI・PPU 設定を切る")
op([0x8D, 0x01, 0x20], "STA $2001   ; 表示を止める")
op([0xA9, 0x01], "LDA #$01")
op([0x8D, 0x15, 0x40], "STA $4015   ; 矩形波 1ch だけ有効")
op([0xA9, 0xBF], "LDA #$BF")
op([0x8D, 0x00, 0x40], "STA $4000   ; デューティ50%・長さ停止・固定音量15")
op([0xA9, 0x08], "LDA #$08")
op([0x8D, 0x01, 0x40], "STA $4001   ; スイープ無効")
op([0xA9, 0xFD], "LDA #$FD")
op([0x8D, 0x02, 0x40], "STA $4002   ; 周期 下位 ($0FD → 1789773/16/254 ≈ 440Hz)")
op([0xA9, 0x00], "LDA #$00")
op([0x8D, 0x03, 0x40], "STA $4003   ; 周期 上位・長さ")
op([0xE6, 0x00], "INC $00", "loop")
op([0xA5, 0x00], "LDA $00")
op([0x8D, 0x00, 0x80], "STA $8000   ; カセットへ書く(RP2350B が数える)")
op([0x4C, None, None], "JMP loop")
op([0x40], "RTI", "nmi")


def asm():
    addr, labels = ORG, {}
    for label, b, _ in prog:
        if label:
            labels[label] = addr
        addr += len(b)
    out = bytearray()
    listing = []
    addr = ORG
    for label, b, note in prog:
        b = bytearray(0 if x is None else x for x in b)
        if note.startswith("JMP loop"):
            b[1], b[2] = labels["loop"] & 0xFF, labels["loop"] >> 8
        listing.append(f"${addr:04X}: {' '.join(f'{x:02X}' for x in b):<9} {note}")
        out += b
        addr += len(b)
    return out, labels, listing


code, labels, listing = asm()
rom = bytearray([0xEA] * 0x4000)                     # 空きは NOP
rom[:len(code)] = code
vec = {0x3FFA: labels["nmi"], 0x3FFC: labels["reset"], 0x3FFE: labels["nmi"]}   # NMI / RESET / IRQ
for off, a in vec.items():
    rom[off], rom[off + 1] = a & 0xFF, a >> 8

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "test_rom.h"), "w", encoding="utf-8") as f:
    f.write("// gen_test_rom.py が作った 16KB のテスト ROM。$8000 と $C000 に鏡映して返す\n")
    for line in listing:
        f.write("// " + line + "\n")
    f.write("static const unsigned char test_rom[16384] = {\n")
    for i in range(0, len(rom), 16):
        f.write("    " + ", ".join(f"0x{x:02X}" for x in rom[i:i + 16]) + ",\n")
    f.write("};\n")
print("\n".join(listing))
print(f"reset=${labels['reset']:04X} loop=${labels['loop']:04X} nmi=${labels['nmi']:04X}, {len(code)} bytes")
