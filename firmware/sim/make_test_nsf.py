"""
試験用の NSF を作る(著作物を使わずに NSF プレイヤーを試すため)。
    python make_test_nsf.py out.nsf
  3 曲。曲 n はパルス 1 で音階(ドレミファソラシド)を 8 フレームごとに鳴らし、曲ごとに 1 オクターブずつ高い。
  バンク切り替えあり(INIT が曲番号のバンクを $8000 に出し、そこから音の表を読む)で、$5FF8 の処理も試す。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from asm6502 import Asm   # noqa: E402

# ドレミファソラシド(NTSC、パルスの周期レジスタ)。オクターブ 4 から
BASE = [428, 381, 339, 320, 285, 254, 226, 214]
NOTE, CNT, IDX = 0x00, 0x01, 0x02            # ゼロページ(NSF が自由に使う)

code = Asm(0xF000)                           # バンク 7(固定、$F000)
code.label("init")
code.sta(0x5FF8)                             # A = 曲番号 → バンク A を $8000 に(バンク 0〜2 が音の表)
code.lda_imm(0x0F); code.sta(0x4015)
code.lda_imm(0xBF); code.sta(0x4000)         # デューティ 50%、音量 15 固定
code.lda_imm(0x08); code.sta(0x4001)
code.lda_imm(0); code.sta_zp(CNT); code.sta_zp(IDX)
code.rts()
code.label("play")
code.inc_zp(CNT); code.lda_zp(CNT); code.and_imm(7); code.bne("done")
code.lda_zp(IDX); code.and_imm(7); code.tax()
code.lda_absx(0x8000); code.sta(0x4002)       # 表(今のバンク)から周期の下位
code.lda_absx(0x8008); code.sta(0x4003)       # 上位 + 長さ
code.inc_zp(IDX)
code.label("done")
code.rts()
body, _ = code.build(0x1000)

img = bytearray(8 * 0x1000)
for song in range(3):
    for i, per in enumerate(BASE):
        p = per >> song
        img[song * 0x1000 + i] = p & 0xFF
        img[song * 0x1000 + 8 + i] = (p >> 8) | 0xF8   # 長さ = 最大
img[7 * 0x1000:8 * 0x1000] = body
hdr = bytearray(0x80)
hdr[0:5] = b"NESM\x1a"; hdr[5] = 1; hdr[6] = 3; hdr[7] = 1
for off, v in ((8, 0x8000), (10, code.labels["init"]), (12, code.labels["play"])):
    hdr[off], hdr[off + 1] = v & 0xFF, v >> 8
hdr[0x0E:0x0E + 17] = b"MAGICON TEST SCALE"[:17]
hdr[0x2E:0x2E + 8] = b"SHIMA-R7"
hdr[0x4E:0x4E + 4] = b"2026"
hdr[0x6E], hdr[0x6F] = 0x1B, 0x41              # 16667us(60Hz)
hdr[0x70:0x78] = bytes([0, 1, 2, 3, 4, 5, 6, 7])
open(sys.argv[1], "wb").write(bytes(hdr) + bytes(img))
print("->", sys.argv[1])
