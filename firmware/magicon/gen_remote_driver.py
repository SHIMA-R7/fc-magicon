"""
画面転送(リモートデスクトップ)モードの 6502 プログラムと、マウスカーソルの CHR を作り、remote_driver.h に書き出す。
    python gen_remote_driver.py

しくみ(cart.c の「画面転送」):
  ・ネームテーブルに「(行 % 8) * 32 + 列」のタイル番号を並べる(2 画面分。ミラーリングがどれでも同じに見えるように)。
    PPU がパターンを読みに来たアドレス(タイル番号・行の中の y)から、カセットは画面のどこを描いているかが分かり、
    PC から来た 256 x 240 の絵のその場所の 8 ドットを返す。行の 8 の位(0〜3)は、タイル番号の行が 7 → 0 になる回数で数える。
  ・背景のパレット 16 + スプライトのパレット 16 = 32 バイトと、属性テーブル 64 バイトは、VBlank ごとに 6502 が
    カセットの $5D00-$5D5F から PPU へ写す(16 x 16 ドットごとに 4 色を選べる)。
  ・マウスカーソルはスプライト(パターンテーブル $1000 の 4 タイル = 16 x 16)。OAM は $5E00 から DMA。
  ・NMI の最後に v を $2000 に戻す(次のフレームの最初の読み出しが行 0 になるように。カセットの位置合わせのため)。
  ・パッド(1コン)とファミリーベーシックのキーボード(nesdev: $4016 に $05 → 各行 $04 / $06 を書いて $4017 の bit1-4)を読み、
    $5F00(パッド、bit7 = A … bit0 = →)、$5F01-$5F09(キーボードの 9 行、下位 4 ビット = 列 0、上位 4 ビット = 列 1、押すと 0)、
    $5F0F(フレームの数)に書く。カセットがそれを USB で PC に送る。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from asm6502 import Asm   # noqa: E402

PAL, ATTR, OAM, IO = 0x5D00, 0x5D20, 0x5E00, 0x5F00
PAD, KB, FRAME = IO, IO + 1, IO + 0x0F
ROW, TMP, NTC = 0x00, 0x01, 0x02                   # ゼロページ(このプログラムだけが使う)
# キーボードの列を選んでから読むまでの待ち。nesdev は約 50 サイクルだが、前に作った拡張端子 ⇔ USB 変換器
# (github.com/SHIMA-R7/Famicom-Expand-USB-Adapter)では 300us で不安定、500us で安定した(寄生容量)ので 500us にする。
# 18 回で約 9ms。VBlank の PPU の仕事が終わってから読むので、画面には響かない(NMI の中で次の NMI までに終わる)
KB_WAIT_US = 500
KB_WAIT_LOOPS = min(255, round((KB_WAIT_US * 1.789773 - 12) / 5))   # DEX + BNE = 5 サイクル、JSR/LDX/RTS で約 12
CTRL = 0x88                                        # NMI 有効、背景 = $0000、スプライト = $1000、8x8
MASK = 0x1E                                        # 背景とスプライトを表示(左端 8 ドットも)

a = Asm(0xC000)
a.label("reset")
a.sei(); a.cld(); a.ldx_imm(0xFF); a.txs()
a.lda_imm(0); a.sta(0x2000); a.sta(0x2001); a.sta(0x4010)
a.lda_imm(0x40); a.sta(0x4017)                     # APU のフレーム IRQ を止める
a.label("vbl1"); a.bit(0x2002); a.bpl("vbl1")
a.label("vbl2"); a.bit(0x2002); a.bpl("vbl2")
a.lda_imm(0x3F); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
a.ldx_imm(0)
a.label("pal"); a.lda_absx(PAL); a.sta(0x2007); a.inx(); a.cpx_imm(32); a.bne("pal")
# ネームテーブル 2 画面分($2000-$27FF): タイル = (行 % 8) * 32 + 列、属性 = 0
a.lda_imm(0x20); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
a.lda_imm(2); a.sta_zp(NTC)
a.label("nt")
a.lda_imm(0); a.sta_zp(ROW)
a.label("row")
a.lda_zp(ROW); a.and_imm(7); a.asl_a(); a.asl_a(); a.asl_a(); a.asl_a(); a.asl_a(); a.sta_zp(TMP)
a.ldx_imm(0)
a.label("col"); a.txa(); a.ora_zp(TMP); a.sta(0x2007); a.inx(); a.cpx_imm(32); a.bne("col")
a.inc_zp(ROW); a.lda_zp(ROW); a.cmp_imm(30); a.bne("row")
a.lda_imm(0); a.ldx_imm(64)
a.label("attr0"); a.sta(0x2007); a.dex(); a.bne("attr0")
a.dec_zp(NTC); a.bne("nt")
a.label("vbl3"); a.bit(0x2002); a.bpl("vbl3")
a.lda_imm(0x20); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006); a.sta(0x2005); a.sta(0x2005)
a.lda_imm(CTRL); a.sta(0x2000)
a.lda_imm(MASK); a.sta(0x2001)
a.label("main"); a.jmp("main")

a.label("nmi")
a.pha(); a.txa(); a.pha(); a.tya(); a.pha()
a.lda_imm(0); a.sta(0x2003); a.lda_imm(OAM >> 8); a.sta(0x4014)       # カーソル(OAM DMA、513 サイクル)
a.bit(0x2002)
a.lda_imm(0x3F); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
for i in range(32):                                                  # パレット 32(展開して 1 バイト 8 サイクル)
    a.lda_abs(PAL + i); a.sta(0x2007)
a.lda_imm(0x23); a.sta(0x2006); a.lda_imm(0xC0); a.sta(0x2006)
for i in range(64):                                                  # 属性テーブル 64
    a.lda_abs(ATTR + i); a.sta(0x2007)
a.lda_imm(0x20); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)      # v = $2000(次のフレームの最初は行 0)
a.sta(0x2005); a.sta(0x2005)
a.lda_imm(CTRL); a.sta(0x2000)
# ここから下は PPU を触らないので、VBlank を過ぎてもよい
a.lda_imm(1); a.sta(0x4016); a.lda_imm(0); a.sta(0x4016)
a.ldx_imm(8)
a.label("pad"); a.lda_abs(0x4016); a.lsr_a(); a.rol_abs(PAD); a.dex(); a.bne("pad")
a.lda_imm(0x05); a.sta(0x4016)                                      # キーボード: 行 0 へ戻して有効に
a.jsr("kbwait")
a.ldy_imm(0)
a.label("kb")
a.lda_imm(0x04); a.sta(0x4016); a.jsr("kbwait")                     # 列 0
a.lda_abs(0x4017); a.and_imm(0x1E); a.lsr_a(); a.sta_zp(TMP)
a.lda_imm(0x06); a.sta(0x4016); a.jsr("kbwait")                     # 列 1(次に列 0 にすると行が進む)
a.lda_abs(0x4017); a.and_imm(0x1E); a.asl_a(); a.asl_a(); a.asl_a(); a.ora_zp(TMP)
a.sta_absy(KB)
a.iny(); a.cpy_imm(9); a.bne("kb")
a.lda_imm(0); a.sta(0x4016)
a.inc_abs(FRAME)
a.pla(); a.tay(); a.pla(); a.tax(); a.pla(); a.rti()
a.label("kbwait")                                                   # 列を選んでから読むまでの待ち(KB_WAIT_US)
a.ldx_imm(KB_WAIT_LOOPS)
a.label("w"); a.dex(); a.bne("w")
a.rts()
a.label("irq"); a.rti()

prg, listing = a.build(0x4000, {"nmi": "nmi", "reset": "reset", "irq": "irq"})

# マウスカーソル(矢印、16 x 16 = 4 タイル: 0 左上、1 右上、2 左下、3 右下)。色 1 = 白、色 3 = 黒のふち
ARROW = [
    "3...............",
    "33..............",
    "313.............",
    "3113............",
    "31113...........",
    "311113..........",
    "3111113.........",
    "31111113........",
    "311111113.......",
    "3111111113......",
    "31111133333.....",
    "3113113.........",
    "313.3113........",
    "33..3113........",
    "3....3113.......",
    ".....3333.......",
]
spr = bytearray(64)
for t, (ty, tx) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
    for y in range(8):
        row = ARROW[ty * 8 + y][tx * 8:tx * 8 + 8]
        for x, ch in enumerate(row):
            c = int(ch) if ch != "." else 0
            if c & 1: spr[t * 16 + y] |= 0x80 >> x
            if c & 2: spr[t * 16 + 8 + y] |= 0x80 >> x

def arr(name, data):
    lines = [f"static const uint8_t {name}[{len(data)}] = {{"]
    for i in range(0, len(data), 16):
        lines.append("    " + ", ".join(f"0x{x:02X}" for x in data[i:i + 16]) + ",")
    return "\n".join(lines + ["};"])

with open(os.path.join(HERE, "remote_driver.h"), "w", encoding="utf-8") as f:
    f.write("// gen_remote_driver.py が作った画面転送モードの 6502 プログラム($C000-、16KB)とカーソルの CHR。手で直さない\n")
    f.write("#pragma once\n#include <stdint.h>\n\n")
    for k, v in (("RD_PAL", PAL), ("RD_ATTR", ATTR), ("RD_OAM", OAM), ("RD_IO", IO)):
        f.write(f"#define {k:10} 0x{v:04X}\n")
    f.write("\n// " + "\n// ".join(listing[:40]) + "\n// ...\n")
    f.write(arr("remote_prg", prg) + "\n" + arr("remote_spr_chr", spr) + "\n")
used = max(i for i, x in enumerate(prg[:0x3FFA]) if x != 0xEA) + 1
print(f"code {used} bytes  reset ${a.labels['reset']:04X}  nmi ${a.labels['nmi']:04X}")
