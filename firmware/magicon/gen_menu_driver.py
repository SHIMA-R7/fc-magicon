"""
ゲーム選択メニューの 6502 プログラムと画面の土台を作り、menu_driver.h に書き出す。
    python gen_menu_driver.py
  フォントとロゴは NSF プレイヤーの CHR(nsf_driver.h の nsfd_chr)をそのまま使う(ファームが CHR に写す)。

メニューは NROM(PRG 32KB + CHR 8KB)として動く。PRG はファーム(cart.c の cart_load_menu)が起動時に組み立てる:
  $8000       項目の数(1〜127)
  $8100-$817F 題名の番地の下位、$8180-$81FF 上位
  $8200-      題名(28 文字ずつ、空白で埋める)
  $9800-$9BFF 画面の土台(ネームテーブル 960 + 属性 64)
  $C000-      このプログラム、$FFFA- ベクター
操作: 上下 = 選ぶ(押し続けると続けて動く)、左右 = 20 項目ずつ、A / START = 始める。
始める時は、本体 RAM($0300)に写した小さなプログラムに移ってから $5FF0 に番号を書く。ファームはそれを見て
番号を覚えて再起動し、その ROM を読み込む。本体側は 1.5 秒待ってから JMP ($FFFC) でゲームを最初から始める
(待つ間 PRG は読まないので、カセットが入れ替わっても平気)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from asm6502 import Asm   # noqa: E402

COUNT, PTR_LO, PTR_HI, TITLES, NT_TPL, CODE = 0x8000, 0x8100, 0x8180, 0x8200, 0x9800, 0xC000
TITLE_LEN, ROWS, ROW0 = 28, 20, 7                   # 題名の長さ、1 ページの行数、最初の行
SELECT_REG = 0x5FF0
STUB = 0x0300
LOGO_TILE0, LOGO_W, LOGO_H, ROW_LOGO, COL_LOGO = 0x80, 17, 2, 2, 7   # nsf_driver.h の CHR のロゴ(gen_nsf_driver.py と同じ)
# ゼロページ
CUR, TOP, PAD, PREV, NEW, NMIF, HOLD, OLDCUR, PTR, TMP, AHI, ALO, CNT, ROWN = (0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14)
UP, DOWN, LEFT, RIGHT, A_START = 0x08, 0x04, 0x02, 0x01, 0x90

# ---------------- 始める時に本体 RAM で動く部分($0300) ----------------
s = Asm(STUB)
s.sei()
s.lda_imm(0); s.sta(0x2000); s.sta(0x2001); s.sta(0x4015)
s.lda_zp(CUR); s.sta(SELECT_REG)                     # ファームへ番号を渡す(ここで RP2350 が再起動する)
s.ldx_imm(90)                                        # 1.5 秒待つ(VBlank を 90 回)
s.label("w"); s.bit(0x2002); s.bpl("w"); s.dex(); s.bne("w")
s.lda_imm(0); s.tax()
s.label("c")
for page in (0, 1, 2, 4, 5, 6, 7):                   # 本体 RAM を 0 に(このページ $0300 は残す)
    s.sta_absx(page * 0x100)
s.inx(); s.bne("c")
s.jmp_ind(0xFFFC)                                    # 選んだゲームのリセットベクターへ
stub, stub_listing = s.build(0x40)
stub = bytes(stub[:max(i for i, x in enumerate(stub) if x != 0xEA) + 1])

# ---------------- メニュー本体($C000) ----------------
a = Asm(CODE)
a.label("reset")
a.sei(); a.cld(); a.ldx_imm(0xFF); a.txs()
a.lda_imm(0); a.sta(0x2000); a.sta(0x2001); a.sta(0x4015); a.sta(0x4010)
a.lda_imm(0x40); a.sta(0x4017)
a.label("vbl1"); a.bit(0x2002); a.bpl("vbl1")
a.label("vbl2"); a.bit(0x2002); a.bpl("vbl2")
a.lda_imm(0x3F); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
a.ldx_imm(0)
a.label("pal"); a.lda_absx("paltab"); a.sta(0x2007); a.inx(); a.cpx_imm(32); a.bne("pal")
a.lda_imm(0x20); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
for page in range(4):
    a.ldx_imm(0)
    a.label(f"nt{page}"); a.lda_absx(NT_TPL + page * 0x100); a.sta(0x2007); a.inx(); a.bne(f"nt{page}")
a.lda_abs(COUNT); a.sta_zp(CNT)
a.lda_imm(0); a.sta_zp(CUR); a.sta_zp(TOP); a.sta_zp(PREV); a.sta_zp(HOLD)
a.jsr("draw_page"); a.jsr("show")

a.label("main")
a.lda_imm(0); a.sta_zp(NMIF)
a.label("wait"); a.lda_zp(NMIF); a.beq("wait")      # VBlank の始め(NMI)まで待つ
# パッド(1コンと、拡張端子のコントローラーの両方): bit7 = A … bit0 = →
a.lda_imm(1); a.sta(0x4016); a.lda_imm(0); a.sta(0x4016)
a.ldx_imm(8)
a.label("pad"); a.lda_abs(0x4016); a.and_imm(3); a.cmp_imm(1); a.rol_abs(PAD); a.dex(); a.bne("pad")
a.lda_zp(PREV); a.eor_imm(0xFF); a.and_zp(PAD); a.sta_zp(NEW)
a.lda_zp(PAD); a.sta_zp(PREV)
# 上下を押し続けたら、24 フレーム後から 4 フレームごとに動く
a.lda_zp(PAD); a.and_imm(UP | DOWN); a.bne("held")
a.lda_imm(0); a.sta_zp(HOLD); a.jmp("dirs")
a.label("held"); a.inc_zp(HOLD); a.lda_zp(HOLD); a.cmp_imm(24); a.bcc("dirs")
a.lda_imm(20); a.sta_zp(HOLD); a.lda_zp(PAD); a.and_imm(UP | DOWN); a.ora_zp(NEW); a.sta_zp(NEW)
a.label("dirs")
a.lda_zp(CUR); a.sta_zp(OLDCUR)
a.lda_zp(NEW); a.and_imm(DOWN); a.beq("not_down")
a.ldx_abs(CUR); a.inx(); a.txa(); a.cmp_abs(CNT); a.bcs("not_down"); a.sta_zp(CUR)   # 最後なら動かない
a.label("not_down")
a.lda_zp(NEW); a.and_imm(UP); a.beq("not_up")
a.lda_zp(CUR); a.beq("not_up"); a.dec_zp(CUR)
a.label("not_up")
a.lda_zp(NEW); a.and_imm(RIGHT); a.beq("not_right")              # 次のページ
a.lda_zp(CUR); a.clc(); a.adc_imm(ROWS); a.bcs("clamp"); a.cmp_abs(CNT); a.bcc("set_r")
a.label("clamp"); a.ldx_abs(CNT); a.dex(); a.txa()
a.label("set_r"); a.sta_zp(CUR)
a.label("not_right")
a.lda_zp(NEW); a.and_imm(LEFT); a.beq("not_left")                # 前のページ
a.lda_zp(CUR); a.sec(); a.sbc_imm(ROWS); a.bcs("set_l"); a.lda_imm(0)
a.label("set_l"); a.sta_zp(CUR)
a.label("not_left")
a.lda_zp(NEW); a.and_imm(A_START); a.beq("no_go"); a.jmp("launch")
a.label("no_go")
# 見えている範囲を合わせる(外れたら描き直す)
a.lda_zp(CUR); a.cmp_abs(TOP); a.bcs("ge_top"); a.sta_zp(TOP); a.jmp("redraw")
a.label("ge_top"); a.sec(); a.sbc_abs(TOP); a.cmp_imm(ROWS); a.bcc("same_page")
a.lda_zp(CUR); a.sec(); a.sbc_imm(ROWS - 1); a.sta_zp(TOP); a.jmp("redraw")
a.label("same_page")
a.lda_zp(CUR); a.cmp_abs(OLDCUR); a.bne("move"); a.jmp("main")
a.label("move")                                                  # カーソルだけ動かす(VBlank の中なので間に合う)
a.lda_zp(OLDCUR); a.sec(); a.sbc_abs(TOP); a.jsr("rowaddr"); a.lda_imm(0x20); a.sta(0x2007)
a.lda_zp(CUR); a.sec(); a.sbc_abs(TOP); a.jsr("rowaddr"); a.lda_imm(0x3E); a.sta(0x2007)   # '>'
a.lda_imm(0); a.sta(0x2005); a.sta(0x2005); a.lda_imm(0x80); a.sta(0x2000)
a.jmp("main")
a.label("redraw")                                                # ページごと描き直す(1 フレームだけ表示を止める)
a.lda_imm(0); a.sta(0x2001)
a.jsr("draw_page"); a.jsr("show"); a.jmp("main")

# A = ページの中の行(0〜19)→ その行の 1 列目を PPU の書き込み先にする
a.label("rowaddr")
a.sta_zp(TMP); a.lsr_a(); a.lsr_a(); a.lsr_a(); a.sta_zp(AHI)
a.lda_zp(TMP); a.asl_a(); a.asl_a(); a.asl_a(); a.asl_a(); a.asl_a()
a.clc(); a.adc_imm((0x2000 + ROW0 * 32 + 1) & 0xFF); a.sta_zp(ALO)
a.lda_zp(AHI); a.adc_imm((0x2000 + ROW0 * 32 + 1) >> 8); a.sta(0x2006)
a.lda_zp(ALO); a.sta(0x2006)
a.rts()

# 20 行ぶん描く(表示を止めてから呼ぶ)
a.label("draw_page")
a.lda_imm(0); a.sta_zp(ROWN)
a.label("dp_row")
a.lda_zp(ROWN); a.jsr("rowaddr")
a.lda_zp(ROWN); a.clc(); a.adc_abs(TOP); a.tax()                 # X = 項目の番号
a.txa(); a.cmp_abs(CUR); a.bne("dp_nocur"); a.lda_imm(0x3E); a.bne("dp_cur")      # 選んでいる行は '>'
a.label("dp_nocur"); a.lda_imm(0x20)
a.label("dp_cur"); a.sta(0x2007); a.lda_imm(0x20); a.sta(0x2007)
a.txa(); a.cmp_abs(CNT); a.bcs("dp_blank")
a.lda_absx(PTR_LO); a.sta_zp(PTR); a.lda_absx(PTR_HI); a.sta_zp(PTR + 1)
a.ldy_imm(0)
a.label("dp_ch"); a.lda_indy(PTR); a.sta(0x2007); a.iny(); a.cpy_imm(TITLE_LEN); a.bne("dp_ch")
a.jmp("dp_next")
a.label("dp_blank"); a.ldy_imm(TITLE_LEN); a.lda_imm(0x20)
a.label("dp_b"); a.sta(0x2007); a.dey(); a.bne("dp_b")
a.label("dp_next"); a.inc_zp(ROWN); a.lda_zp(ROWN); a.cmp_imm(ROWS); a.bne("dp_row")
a.rts()

# 次の VBlank で表示を戻す
a.label("show")
a.label("sh_w"); a.bit(0x2002); a.bpl("sh_w")
a.lda_imm(0); a.sta(0x2005); a.sta(0x2005)
a.lda_imm(0x80); a.sta(0x2000)                                   # NMI を有効に
a.lda_imm(0x0A); a.sta(0x2001)                                   # 背景を表示(左端 8 ドットも)
a.rts()

a.label("launch")                                                # 本体 RAM へ写して移る
a.ldx_imm(0)
a.label("cp"); a.lda_absx("stub"); a.sta_absx(STUB); a.inx(); a.cpx_imm(len(stub)); a.bne("cp")
a.jmp(STUB)

a.label("nmi"); a.inc_zp(NMIF); a.rti()
a.label("irq"); a.rti()
a.label("paltab")
a.bytes_([0x0F, 0x30, 0x11, 0x21,  0x0F, 0x21, 0x11, 0x30,  0x0F, 0x30, 0x11, 0x21,  0x0F, 0x30, 0x11, 0x21] * 2,
         "パレット(背景 0 = 白・青・水色、背景 1 = 水色の文字)。NSF プレイヤーと同じ")
a.label("stub"); a.bytes_(stub, f"本体 RAM ${STUB:04X} へ写す部分({len(stub)} バイト)")

code, listing = a.build(0x10000 - CODE, vectors={"nmi": "nmi", "reset": "reset", "irq": "irq"})
L = a.labels

# ---------------- 画面の土台 ----------------
nt = bytearray([0x20] * 960 + [0] * 64)
def put(row, text, col=None):
    col = (32 - len(text)) // 2 if col is None else col
    nt[row * 32 + col:row * 32 + col + len(text)] = text.encode("ascii")
for ty in range(LOGO_H):
    for tx in range(LOGO_W):
        nt[(ROW_LOGO + ty) * 32 + COL_LOGO + tx] = LOGO_TILE0 + ty * LOGO_W + tx
put(5, "SELECT A GAME")
put(28, "A:PLAY   LEFT/RIGHT:PAGE")                  # テレビで端が切れないよう短く
def attr_row(tile_row, pal):
    r, half = tile_row // 4, (tile_row % 4) // 2
    for i in range(8):
        nt[960 + r * 8 + i] |= (pal | (pal << 2)) << (4 * half)
for r in (5, 28):
    attr_row(r, 1)

# ---------------- 書き出し ----------------
def arr(name, data):
    lines = [f"static const uint8_t {name}[{len(data)}] = {{"]
    for i in range(0, len(data), 16):
        lines.append("    " + ", ".join(f"0x{x:02X}" for x in data[i:i + 16]) + ",")
    return "\n".join(lines + ["};"])

with open(os.path.join(HERE, "menu_driver.h"), "w", encoding="utf-8") as f:
    f.write("// gen_menu_driver.py が作ったゲーム選択メニュー($C000- のプログラム・画面の土台)。手で直さない\n"
            "#pragma once\n#include <stdint.h>\n\n")
    for k, v in (("MENUD_COUNT", COUNT - 0x8000), ("MENUD_PTR_LO", PTR_LO - 0x8000), ("MENUD_PTR_HI", PTR_HI - 0x8000),
                 ("MENUD_TITLES", TITLES - 0x8000), ("MENUD_TITLE_ADDR", TITLES), ("MENUD_TITLE_LEN", TITLE_LEN),
                 ("MENUD_NT", NT_TPL - 0x8000), ("MENUD_CODE", CODE - 0x8000), ("MENUD_SELECT", SELECT_REG),
                 ("MENUD_MAX_ITEMS", 127)):
        f.write(f"#define {k:18} 0x{v:04X}\n")
    f.write("\n// " + "\n// ".join(stub_listing + [""] + listing) + "\n")
    f.write(arr("menud_code", code) + "\n" + arr("menud_nt", nt) + "\n")
print(f"menu code {len(code)} bytes (${CODE:04X}-$FFFF, 使っているのは ${CODE:04X}-${L['stub'] + len(stub) - 1:04X})  "
      f"stub {len(stub)} bytes")
