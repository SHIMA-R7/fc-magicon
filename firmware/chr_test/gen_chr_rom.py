"""chr_test 用の 16KB テスト ROM(6502)を作り、chr_rom.h に書き出す。
    python gen_chr_rom.py
  ・PPU が起きるまで VBlank を2回待つ
  ・パレット 16色を書く
  ・ネームテーブル $2000 に 0,1,2,…255 を繰り返し 1024 バイト書く(属性テーブルも含む)
  ・スクロール 0、背景を表示
  ・矩形波で約 440Hz を鳴らし、ループのたびに $8000 へ書く(bus_test と同じ)
  CHR(タイル)は RP2350B 側(main.c)が作る。タイル t は下位2ビットの色で塗り、上辺と左辺に格子線を引く。
  画面に「色の縦縞 + 8ドットごとの格子」が出れば、アドレスの読み取りは正しい。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from asm6502 import Asm, write_header   # noqa: E402

PALETTE = [0x0F, 0x30, 0x16, 0x2A,  0x0F, 0x27, 0x12, 0x1A,  0x0F, 0x21, 0x14, 0x38,  0x0F, 0x10, 0x06, 0x19]

a = Asm(0xC000)
a.label("reset")
a.sei(); a.cld(); a.ldx_imm(0xFF); a.txs()
a.lda_imm(0); a.sta(0x2000); a.sta(0x2001)
a.label("vbl1"); a.bit(0x2002); a.bpl("vbl1")           # PPU が起きるまで VBlank を2回待つ
a.label("vbl2"); a.bit(0x2002); a.bpl("vbl2")
# パレット
a.lda_imm(0x3F); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
a.ldx_imm(0)
a.label("pal"); a.lda_absx("paltab"); a.sta(0x2007); a.inx(); a.cpx_imm(16); a.bne("pal")
# ネームテーブル $2000-$23FF に 0..255 を 4 回
a.lda_imm(0x20); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
a.ldy_imm(4); a.ldx_imm(0)
a.label("nt"); a.stx(0x2007); a.inx(); a.bne("nt"); a.dey(); a.bne("nt")
# スクロール 0、背景を表示(左端8ドットも)
a.lda_imm(0); a.sta(0x2005); a.sta(0x2005)
a.lda_imm(0x00); a.sta(0x2000)
a.lda_imm(0x0A); a.sta(0x2001)
# 音(bus_test と同じ)
a.lda_imm(0x01); a.sta(0x4015)
a.lda_imm(0xBF); a.sta(0x4000)
a.lda_imm(0x08); a.sta(0x4001)
a.lda_imm(0xFD); a.sta(0x4002)
a.lda_imm(0x00); a.sta(0x4003)
a.label("loop"); a.inc_zp(0x00); a.lda_zp(0x00); a.sta(0x8000); a.jmp("loop")
a.label("nmi"); a.rti()
a.label("paltab"); a.bytes_(PALETTE, "パレット 16色")

rom, listing = a.build(0x4000, {"nmi": "nmi", "reset": "reset", "irq": "nmi"})
here = os.path.dirname(os.path.abspath(__file__))
write_header(os.path.join(here, "chr_rom.h"), "chr_test_rom", rom, listing,
             "gen_chr_rom.py が作った 16KB のテスト ROM($8000 と $C000 に鏡映)")
print("\n".join(listing))
print(f"reset=${a.labels['reset']:04X} nmi=${a.labels['nmi']:04X} paltab=${a.labels['paltab']:04X}")
