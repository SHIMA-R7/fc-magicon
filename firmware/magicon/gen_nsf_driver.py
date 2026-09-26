"""
NSF プレイヤーのドライバー(6502)・画面の土台・フォントとロゴの CHR を作り、nsf_driver.h に書き出す。
    python gen_nsf_driver.py
  (Pillow を使う。フォントは Windows の Consolas Bold 9pt、ロゴは ../../images/logo.png)

メモリーの割り当て(カセットの $5000-$5FFF。本体側に何も無い所。RP2350 の SRAM で、書き込みもできる):
  $5000-      ドライバーのコード
  $5800-$5BFF ネームテーブルの土台(1024 バイト。ファームが曲名などを書き込み、ドライバーが PPU へ写す)
  $5F00-      ファームが書く値: +0 曲数、+1 最初の曲(1〜)、+8〜+15 バンクの初期値
  $5F80-      ドライバーの変数(NSF はゼロページを自由に使うので、変数はここに置く)
  $5FF8-$5FFF NSF のバンク切り替え(書き込むと $8000 + n*$1000 の 4KB が切り替わる)
ベクター($FFFA-$FFFF)は、ファームが読み出しを横取りしてこのドライバーの番地を返す。

動作:
  リセット → パレット・画面を出す → 曲を始める(APU を黙らせ、RAM と $6000-$7FFF を 0 にし、バンクを戻し、INIT を呼ぶ)
  → NMI(約 60Hz)ごとに PLAY を呼び、パッドを読む。
  ←→ = 前 / 次の曲、A = 最初から、START = 一時停止(APU を止める)。曲を変える時は NMI の外(メインループ)でやり直す。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from asm6502 import Asm   # noqa: E402

BASE, NT, PARAM, VAR = 0x5000, 0x5800, 0x5F00, 0x5F80
CUR, REQ, PAD, PREV, NEW, INNMI, PAUSED, DRAWPAUSE = (VAR + i for i in range(8))
COUNT, START, BANKS = PARAM, PARAM + 1, PARAM + 8

# 画面(32 x 30 タイル)
ROW_LOGO, COL_LOGO = 3, 7
ROW_TITLE, ROW_ARTIST, ROW_COPY = 9, 11, 13
ROW_SONG, COL_SONG = 17, 9                          # "SONG  00 / 00"
ROW_PAUSE, COL_PAUSE = 19, 13
LOGO_W, LOGO_H = 17, 2
LOGO_TILE0 = 0x80

def nt_addr(row, col):
    return 0x2000 + row * 32 + col


# ---------------- ドライバー ----------------
a = Asm(BASE)
a.label("reset")
a.sei(); a.cld(); a.ldx_imm(0xFF); a.txs()
a.lda_imm(0); a.sta(0x2000); a.sta(0x2001); a.sta(0x4015)
a.label("vbl1"); a.bit(0x2002); a.bpl("vbl1")        # PPU が起きるまで VBlank を2回待つ
a.label("vbl2"); a.bit(0x2002); a.bpl("vbl2")
a.lda_imm(0x3F); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)
a.ldx_imm(0)
a.label("pal"); a.lda_absx("paltab"); a.sta(0x2007); a.inx(); a.cpx_imm(32); a.bne("pal")
a.lda_imm(0x20); a.sta(0x2006); a.lda_imm(0x00); a.sta(0x2006)   # 画面の土台 1024 バイトを写す
for page in range(4):
    a.ldx_imm(0)
    a.label(f"nt{page}"); a.lda_absx(NT + page * 0x100); a.sta(0x2007); a.inx(); a.bne(f"nt{page}")
a.lda_abs(START); a.sta(CUR)

a.label("start_song")                                  # メインループから来る(スタックは使い捨てでよい)
a.lda_imm(0); a.sta(0x2000); a.sta(0x2001); a.sta(REQ); a.sta(PAUSED); a.sta(DRAWPAUSE); a.sta(INNMI)
a.ldx_imm(0)
a.label("apu"); a.sta_absx(0x4000); a.inx(); a.cpx_imm(0x14); a.bne("apu")    # $4000-$4013 = 0
a.sta(0x4015); a.lda_imm(0x0F); a.sta(0x4015); a.lda_imm(0x40); a.sta(0x4017)
a.lda_imm(0); a.tax()
a.label("ram")                                         # $0000-$07FF = 0(スタックも。この後 TXS し直す)
for page in range(8):
    a.sta_absx(page * 0x100)
a.inx(); a.bne("ram")
a.label("wram")                                        # $6000-$7FFF = 0
for page in range(32):
    a.sta_absx(0x6000 + page * 0x100)
a.inx(); a.bne("wram")
a.ldx_imm(0xFF); a.txs()
a.ldx_imm(0)
a.label("bank"); a.lda_absx(BANKS); a.sta_absx(0x5FF8); a.inx(); a.cpx_imm(8); a.bne("bank")
for addr, src in ((nt_addr(ROW_SONG, COL_SONG + 6), CUR), (nt_addr(ROW_SONG, COL_SONG + 11), COUNT)):
    a.lda_imm(addr >> 8); a.sta(0x2006); a.lda_imm(addr & 0xFF); a.sta(0x2006)
    a.lda_abs(src); a.jsr("put2")
p = nt_addr(ROW_PAUSE, COL_PAUSE)
a.lda_imm(p >> 8); a.sta(0x2006); a.lda_imm(p & 0xFF); a.sta(0x2006)
a.lda_imm(0x20); a.ldx_imm(5)
a.label("unpause"); a.sta(0x2007); a.dex(); a.bne("unpause")
a.ldx_abs(CUR); a.dex(); a.txa(); a.ldx_imm(0)       # A = 曲番号(0〜)、X = 0(NTSC)
a.jsr("init_tramp")
a.label("vbl3"); a.bit(0x2002); a.bpl("vbl3")        # 表示を戻すのは VBlank の中で
a.lda_imm(0); a.sta(0x2005); a.sta(0x2005)
a.lda_imm(0x80); a.sta(0x2000)                         # NMI を有効に
a.lda_imm(0x0A); a.sta(0x2001)                         # 背景を表示(左端 8 ドットも)
a.label("main"); a.lda_abs(REQ); a.beq("main"); a.jmp("start_song")

a.label("put2")                                        # A(0〜99)を 10 進 2 桁で $2007 へ
a.ldx_imm(0x30)
a.label("p2"); a.cmp_imm(10); a.bcc("p2d"); a.sbc_imm(10); a.inx(); a.bne("p2")
a.label("p2d"); a.stx(0x2007); a.ora_imm(0x30); a.sta(0x2007); a.rts()

a.label("nmi")
a.pha(); a.txa(); a.pha(); a.tya(); a.pha()
a.lda_abs(INNMI); a.beq("nmi_go"); a.jmp("nmi_out")     # PLAY が 1 フレームを超えた時は重ねて呼ばない
a.label("nmi_go")
a.inc_abs(INNMI)
a.lda_abs(DRAWPAUSE); a.beq("no_draw")                 # 一時停止の表示(VBlank の最初にだけ書く)
a.lda_imm(0); a.sta(DRAWPAUSE)
a.lda_abs(0x2002)
a.lda_imm(p >> 8); a.sta(0x2006); a.lda_imm(p & 0xFF); a.sta(0x2006)
a.ldx_imm(0); a.lda_abs(PAUSED); a.beq("dp_clr")
a.label("dp_txt"); a.lda_absx("pausetxt"); a.sta(0x2007); a.inx(); a.cpx_imm(5); a.bne("dp_txt"); a.jmp("dp_end")
a.label("dp_clr"); a.lda_imm(0x20)
a.label("dp_c"); a.sta(0x2007); a.inx(); a.cpx_imm(5); a.bne("dp_c")
a.label("dp_end"); a.lda_imm(0); a.sta(0x2005); a.sta(0x2005); a.lda_imm(0x80); a.sta(0x2000)
a.label("no_draw")
a.lda_abs(PAUSED); a.bne("no_play")
a.jsr("play_tramp")
a.label("no_play")
a.lda_imm(1); a.sta(0x4016); a.lda_imm(0); a.sta(0x4016)   # パッド: bit7 = A … bit0 = →
a.ldx_imm(8)
a.label("pad"); a.lda_abs(0x4016); a.lsr_a(); a.rol_abs(PAD); a.dex(); a.bne("pad")
a.lda_abs(PREV); a.eor_imm(0xFF); a.and_abs(PAD); a.sta(NEW)
a.lda_abs(PAD); a.sta(PREV)
a.lda_abs(NEW); a.lsr_a(); a.bcc("not_right")           # → 次の曲
a.inc_abs(CUR); a.lda_abs(CUR); a.cmp_abs(COUNT); a.beq("req"); a.bcc("req")
a.lda_imm(1); a.sta(CUR); a.jmp("req")
a.label("not_right")
a.lda_abs(NEW); a.and_imm(0x02); a.beq("not_left")     # ← 前の曲
a.dec_abs(CUR); a.bne("req")
a.lda_abs(COUNT); a.sta(CUR); a.jmp("req")
a.label("not_left")
a.lda_abs(NEW); a.bpl("not_a")                         # A = 最初から
a.label("req"); a.lda_imm(1); a.sta(REQ); a.jmp("nmi_done")
a.label("not_a")
a.lda_abs(NEW); a.and_imm(0x10); a.beq("nmi_done")     # START = 一時停止 / 再開
a.lda_abs(PAUSED); a.eor_imm(1); a.sta(PAUSED)
a.lda_imm(1); a.sta(DRAWPAUSE)
a.lda_abs(PAUSED); a.beq("resume")
a.lda_imm(0); a.sta(0x4015); a.jmp("nmi_done")
a.label("resume"); a.lda_imm(0x0F); a.sta(0x4015)
a.label("nmi_done"); a.dec_abs(INNMI)
a.label("nmi_out")
a.pla(); a.tay(); a.pla(); a.tax(); a.pla(); a.rti()

a.label("irq"); a.rti()
a.label("init_tramp"); a.jmp(0x0000)                   # ファームが NSF の INIT の番地を書く
a.label("play_tramp"); a.jmp(0x0000)                   # 同じく PLAY
a.label("paltab")
a.bytes_([0x0F, 0x30, 0x11, 0x21,  0x0F, 0x21, 0x11, 0x30,  0x0F, 0x30, 0x11, 0x21,  0x0F, 0x30, 0x11, 0x21] * 2,
         "パレット(背景 0 = 白・青・水色、背景 1 = 水色の文字)")
a.label("pausetxt"); a.bytes_(b"PAUSE", '"PAUSE"')

code, listing = a.build(NT - BASE)
code = bytes(code[:max(i for i, x in enumerate(code) if x != 0xEA) + 1])   # 後ろの詰め物(NOP)は要らない
L = a.labels

# ---------------- CHR(パターンテーブル 4KB): 0x20〜0x7E = ASCII、0x80〜 = ロゴ ----------------
chr_ = bytearray(0x1000)
font = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", 9)
for c in range(0x21, 0x7F):
    g = Image.new("L", (8, 8), 0)
    d = ImageDraw.Draw(g)
    bb = d.textbbox((0, 0), chr(c), font=font)
    d.text((4 - (bb[0] + bb[2]) / 2, -1), chr(c), font=font, fill=255)
    px = g.load()
    for y in range(8):
        chr_[c * 16 + y] = sum(0x80 >> x for x in range(8) if px[x, y] > 110)   # 色 1(プレーン 0 だけ)

logo = Image.open(os.path.join(HERE, "..", "..", "images", "logo.png")).convert("RGB")
lp = logo.load()
xs = [x for x in range(0, logo.width, 2) for y in range(0, logo.height, 4) if sum(lp[x, y]) > 120]
ys = [y for y in range(0, logo.height, 2) for x in range(0, logo.width, 4) if sum(lp[x, y]) > 120]
crop = logo.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
cp = crop.load()
PAL = [(0, 0, 0), (255, 255, 255), (26, 108, 255), (90, 170, 255)]      # 背景パレット 0 の色 0〜3
W, H = LOGO_W * 8, LOGO_H * 8
pix = [[0] * W for _ in range(H)]
for y in range(H):
    for x in range(W):
        x0, x1 = int(x * crop.width / W), int((x + 1) * crop.width / W)
        y0, y1 = int(y * crop.height / H), int((y + 1) * crop.height / H)
        votes = [0] * 4
        for yy in range(y0 + (y1 - y0) // 4, y1 - (y1 - y0) // 4 + 1):     # セルの中ほどの色の多数決
            for xx in range(x0 + (x1 - x0) // 4, x1 - (x1 - x0) // 4 + 1):
                c = cp[min(xx, crop.width - 1), min(yy, crop.height - 1)]
                votes[min(range(4), key=lambda i: sum((u - v) ** 2 for u, v in zip(c, PAL[i])))] += 1
        pix[y][x] = max(range(4), key=lambda i: votes[i])
for ty in range(LOGO_H):
    for tx in range(LOGO_W):
        t = LOGO_TILE0 + ty * LOGO_W + tx
        for y in range(8):
            row = pix[ty * 8 + y][tx * 8:tx * 8 + 8]
            chr_[t * 16 + y] = sum(0x80 >> x for x in range(8) if row[x] & 1)
            chr_[t * 16 + 8 + y] = sum(0x80 >> x for x in range(8) if row[x] & 2)

# ---------------- 画面の土台(ネームテーブル 960 + 属性 64) ----------------
nt = bytearray([0x20] * 960 + [0] * 64)
def put(row, s, col=None):
    s = s[:32]
    col = (32 - len(s)) // 2 if col is None else col
    nt[row * 32 + col:row * 32 + col + len(s)] = s.encode("ascii")
for ty in range(LOGO_H):
    for tx in range(LOGO_W):
        nt[(ROW_LOGO + ty) * 32 + COL_LOGO + tx] = LOGO_TILE0 + ty * LOGO_W + tx
put(6, "NSF PLAYER")
put(ROW_SONG, "SONG  00 / 00", COL_SONG)
put(23, "LEFT/RIGHT  SONG")
put(25, "A  RESTART    START  PAUSE")
def attr_row(tile_row, pal):                     # そのタイル行を含む 16x16 の半分を背景パレット pal に
    r, half = tile_row // 4, (tile_row % 4) // 2
    for i in range(8):
        nt[960 + r * 8 + i] |= (pal | (pal << 2)) << (4 * half)
for r in (ROW_TITLE, ROW_SONG, ROW_PAUSE):
    attr_row(r, 1)

# ---------------- 書き出し ----------------
def arr(name, data):
    lines = [f"static const uint8_t {name}[{len(data)}] = {{"]
    for i in range(0, len(data), 16):
        lines.append("    " + ", ".join(f"0x{x:02X}" for x in data[i:i + 16]) + ",")
    return "\n".join(lines + ["};"])

with open(os.path.join(HERE, "nsf_driver.h"), "w", encoding="utf-8") as f:
    f.write("// gen_nsf_driver.py が作った NSF プレイヤーのドライバー($5000-)・画面の土台・CHR。手で直さない\n#pragma once\n#include <stdint.h>\n\n")
    for k, v in (("NSFD_BASE", BASE), ("NSFD_NT", NT - BASE), ("NSFD_PARAM", PARAM - BASE),
                 ("NSFD_RESET", L["reset"]), ("NSFD_NMI", L["nmi"]), ("NSFD_IRQ", L["irq"]),
                 ("NSFD_INIT_OPERAND", L["init_tramp"] + 1 - BASE), ("NSFD_PLAY_OPERAND", L["play_tramp"] + 1 - BASE),
                 ("NSFD_ROW_TITLE", ROW_TITLE), ("NSFD_ROW_ARTIST", ROW_ARTIST), ("NSFD_ROW_COPY", ROW_COPY)):
        f.write(f"#define {k:20} 0x{v:04X}\n")
    f.write("\n// " + "\n// ".join(listing) + "\n")
    f.write(arr("nsfd_code", code) + "\n" + arr("nsfd_nt", nt) + "\n" + arr("nsfd_chr", chr_) + "\n")

print(f"code {len(code)} bytes (${BASE:04X}-${BASE + len(code) - 1:04X})  reset ${L['reset']:04X}  nmi ${L['nmi']:04X}")
# 確認用の画面イメージ(曲名などは例)
for row, s in ((ROW_TITLE, "Super Example Soundtrack"), (ROW_ARTIST, "Some Composer"), (ROW_COPY, "2026 SHIMA-R7"),
               (ROW_SONG, "SONG  03 / 12")):
    put(row, s, COL_SONG if row == ROW_SONG else None)
img = Image.new("RGB", (256, 240))
ip = img.load()
PALS = [[(0, 0, 0), (255, 255, 255), (26, 108, 255), (90, 170, 255)], [(0, 0, 0), (90, 170, 255), (26, 108, 255), (255, 255, 255)]]
for row in range(30):
    for col in range(32):
        t = nt[row * 32 + col]
        ab = nt[960 + (row // 4) * 8 + col // 4] >> (((row % 4) // 2) * 4 + ((col % 4) // 2) * 2) & 3
        for y in range(8):
            for x in range(8):
                ci = ((chr_[t * 16 + y] >> (7 - x)) & 1) | (((chr_[t * 16 + 8 + y] >> (7 - x)) & 1) << 1)
                ip[col * 8 + x, row * 8 + y] = PALS[min(ab, 1)][ci]
img.resize((512, 480), Image.NEAREST).save(os.path.join(HERE, "nsf_screen_preview.png"))

