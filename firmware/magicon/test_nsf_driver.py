"""
NSF ドライバー(nsf_driver.h)を 6502 エミュレーター(py65)で動かして確かめる。
    python test_nsf_driver.py        (pip install py65)
  カセット側の割り当ては cart.c の nsf_bus_loop / nsf_write / nsf_load と同じにする:
    $5000-$5FFF ドライバー(書き込み可)、$5FF8-$5FFF バンク、$6000-$7FFF WRAM、$8000- 曲、$FFFA-$FFFF はドライバーの番地
  テスト用の NSF(小さな 6502 コード)で、INIT に渡る曲番号、PLAY の呼び出し、←→・A・START、RAM の初期化、バンクを見る。
"""
import os
import re
import sys

from py65.devices.mpu6502 import MPU
from py65.memory import ObservableMemory

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from asm6502 import Asm   # noqa: E402

H = open(os.path.join(HERE, "nsf_driver.h"), encoding="utf-8").read()
D = {k: int(v, 16) for k, v in re.findall(r"#define (\w+)\s+0x([0-9A-F]+)", H)}
def carr(name):
    body = re.search(rf"{name}\[\d+\] = \{{(.*?)\}};", H, re.S).group(1)
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9A-F]{2})", body))
CODE, NTIMG = carr("nsfd_code"), carr("nsfd_nt")

A, B, SEL, START, UP, DOWN, LEFT, RIGHT = (0x80 >> i for i in range(8))


class Cart:
    """cart.c の NSF モードと同じ振る舞い + 本体側(RAM・PPU・パッド)の最低限"""

    def __init__(self, nsf):
        self.load_nsf(nsf)
        self.ram = bytearray(0x800)
        self.ppu_ctrl = 0
        self.vbl = False
        self.pad = 0
        self.pad_shift = 0
        self.apu = {}
        self.bank_log = []
        self.mem = ObservableMemory()
        m = self.mem
        m.subscribe_to_read(range(0x0000, 0x10000), self.read)
        m.subscribe_to_write(range(0x0000, 0x10000), self.write)
        self.cpu = MPU(memory=m)
        self.cpu.pc = self.read(0xFFFC) | self.read(0xFFFD) << 8

    def load_nsf(self, p):
        self.songs, self.start = p[6], p[7]
        load, init, play = (p[i] | p[i + 1] << 8 for i in (8, 10, 12))
        banks = p[0x70:0x78]
        self.banked = any(banks)
        data = p[0x80:]
        if self.banked:
            pad = load & 0xFFF
            self.nb = (pad + len(data) + 0xFFF) // 0x1000
            self.rom = bytearray(self.nb * 0x1000)
            self.rom[pad:pad + len(data)] = data
            self.prg = [(b % self.nb) * 0x1000 for b in banks]
        else:
            self.rom = bytearray(0x8000)
            n = 0x10000 - load
            self.rom[load - 0x8000:load - 0x8000 + min(n, len(data))] = data[:n]
            self.nb = 8
            self.prg = [i * 0x1000 for i in range(8)]
        self.vec = bytes([D["NSFD_NMI"] & 0xFF, D["NSFD_NMI"] >> 8, D["NSFD_RESET"] & 0xFF, D["NSFD_RESET"] >> 8,
                          D["NSFD_IRQ"] & 0xFF, D["NSFD_IRQ"] >> 8])
        self.drv = bytearray(0x1000)
        self.drv[:len(CODE)] = CODE
        self.drv[D["NSFD_NT"]:D["NSFD_NT"] + 1024] = NTIMG
        self.drv[D["NSFD_PARAM"]] = self.songs
        self.drv[D["NSFD_PARAM"] + 1] = self.start
        self.drv[D["NSFD_PARAM"] + 8:D["NSFD_PARAM"] + 16] = banks
        for off, v in ((D["NSFD_INIT_OPERAND"], init), (D["NSFD_PLAY_OPERAND"], play)):
            self.drv[off], self.drv[off + 1] = v & 0xFF, v >> 8
        self.wram = bytearray([0xA5] * 0x2000)             # 起動時はゴミ(ドライバーが 0 にするはず)

    def read(self, a):
        if a < 0x2000:
            return self.ram[a & 0x7FF]
        if a < 0x4000:
            if a & 7 == 2:
                v = 0x80 if self.vbl else 0
                self.vbl = not self.vbl                     # 読むたびに VBlank が立ったり消えたり(待ちループを抜けるため)
                return v
            return 0
        if a == 0x4016:
            v = (self.pad_shift >> 7) & 1
            self.pad_shift = (self.pad_shift << 1) & 0xFF
            return 0x40 | v
        if a < 0x5000:
            return 0
        if a < 0x6000:
            return self.drv[a & 0xFFF]
        if a < 0x8000:
            return self.wram[a & 0x1FFF]
        if a >= 0xFFFA:
            return self.vec[a - 0xFFFA]
        return self.rom[self.prg[(a - 0x8000) >> 12] + (a & 0xFFF)]

    def write(self, a, v):
        if a < 0x2000:
            self.ram[a & 0x7FF] = v
        elif a < 0x4000:
            if a & 7 == 0:
                self.ppu_ctrl = v
        elif a == 0x4016:
            if v & 1:
                self.pad_shift = self.pad
        elif a < 0x4018:
            self.apu[a] = v
        elif a < 0x5000:
            pass
        elif a < 0x6000:
            if a >= 0x5FF8:
                self.bank_log.append((a, v))
                if self.banked:
                    self.prg[a - 0x5FF8] = (v % self.nb) * 0x1000
            else:
                self.drv[a & 0xFFF] = v
        elif a < 0x8000:
            self.wram[a & 0x1FFF] = v

    def nmi(self):
        c = self.cpu
        c.stPushWord(c.pc)
        c.stPush((c.p | c.UNUSED) & ~c.BREAK)
        c.p |= c.INTERRUPT
        c.pc = self.read(0xFFFA) | self.read(0xFFFB) << 8

    def frames(self, n, pad=0):
        """n フレーム動かす(1 フレーム 29780 サイクル。$2000 の bit7 が立っていれば毎フレーム NMI)"""
        for _ in range(n):
            self.pad = pad
            start = self.cpu.processorCycles
            while self.cpu.processorCycles - start < 29780:
                self.cpu.step()
            if self.ppu_ctrl & 0x80:
                self.nmi()


def make_nsf(songs, start, code_fn, load=0x8000, banks=(0,) * 8, data=None):
    a = Asm(load)
    code_fn(a)
    body, _ = a.build(0x1000)
    body = bytes(body)
    if data is not None:
        body = data(body)
    hdr = bytearray(0x80)
    hdr[0:5] = b"NESM\x1a"
    hdr[5] = 1
    hdr[6], hdr[7] = songs, start
    for i, v in ((8, load), (10, a.labels["init"]), (12, a.labels["play"])):
        hdr[i], hdr[i + 1] = v & 0xFF, v >> 8
    hdr[0x0E:0x0E + 4] = b"TEST"
    hdr[0x70:0x78] = bytes(banks)
    return bytes(hdr) + body


def plain_code(a):
    a.label("init")
    a.sta(0x0300)                                   # 渡された曲番号
    a.lda_abs(0x6000); a.sta(0x0303)                # WRAM が 0 にされているか
    a.lda_imm(1); a.sta(0x0301)
    a.rts()
    a.label("play")
    a.inc_abs(0x0302); a.lda_abs(0x0302); a.sta(0x4002)
    a.rts()


ok = True
def check(name, cond, detail=""):
    global ok
    print(f"  {'OK ' if cond else 'NG '} {name} {detail}")
    ok &= bool(cond)


print("== 普通の NSF(バンク無し、5 曲、最初は 3 曲目)")
c = Cart(make_nsf(5, 3, plain_code))
c.frames(30)
check("INIT に 2(= 3 曲目)が渡る", c.ram[0x300] == 2, f"A={c.ram[0x300]}")
check("INIT の前に WRAM が 0 になっている", c.ram[0x303] == 0, f"$6000 was {c.ram[0x303]:#x}")
check("NMI が有効", c.ppu_ctrl & 0x80)
n1 = c.ram[0x302]
check("PLAY が毎フレーム呼ばれる", 25 <= n1 <= 30, f"{n1} 回 / 30 フレーム")
c.frames(1, RIGHT); c.frames(10)
check("→ で 4 曲目", c.ram[0x300] == 3, f"A={c.ram[0x300]}")
check("曲を変えると RAM が 0 からやり直し", c.ram[0x302] < 12, f"PLAY {c.ram[0x302]} 回")
c.frames(1, RIGHT); c.frames(5); c.frames(1, RIGHT); c.frames(5)
check("5 曲目の次は 1 曲目", c.ram[0x300] == 0, f"A={c.ram[0x300]}")
c.frames(1, LEFT); c.frames(5)
check("1 曲目の前は 5 曲目", c.ram[0x300] == 4, f"A={c.ram[0x300]}")
c.frames(1, START); c.frames(1)
p0 = c.ram[0x302]; c.frames(20)
check("START で一時停止(PLAY が止まる)", c.ram[0x302] == p0, f"{p0} -> {c.ram[0x302]}")
check("一時停止で $4015 = 0", c.apu.get(0x4015) == 0)
c.frames(1, START); c.frames(10)
check("もう一度 START で再開", c.ram[0x302] > p0 and c.apu.get(0x4015) == 0x0F, f"{p0} -> {c.ram[0x302]}")
c.ram[0x302] = 0; c.frames(1, A); c.frames(5)
check("A で最初から(曲は同じ)", c.ram[0x300] == 4 and c.ram[0x302] < 8, f"A={c.ram[0x300]} play={c.ram[0x302]}")


print("== バンク切り替えの NSF(4KB × 8、INIT が $5FF8 を切り替えて $8000 を読む)")
def banked_code(a):
    a.label("init")
    a.lda_imm(2); a.sta(0x5FF8)                     # $8000 にバンク 2
    a.lda_abs(0x8000); a.sta(0x0304)
    a.rts()
    a.label("play"); a.rts()
# コードはバンク 7 の +$10 に置き、$F010 から実行(初期値でバンク 7 が $F000 に来る)
a = Asm(0xF010); banked_code(a); body, _ = a.build(0x100)
img = bytearray(8 * 0x1000)
for k in range(8):
    img[k * 0x1000] = 0xB0 + k
img[7 * 0x1000 + 0x10:7 * 0x1000 + 0x10 + 0x100] = body
hdr = bytearray(0x80); hdr[0:5] = b"NESM\x1a"; hdr[5] = 1; hdr[6] = 1; hdr[7] = 1
for i, v in ((8, 0x8000), (10, a.labels["init"]), (12, a.labels["play"])):
    hdr[i], hdr[i + 1] = v & 0xFF, v >> 8
hdr[0x70:0x78] = bytes([0, 1, 2, 3, 4, 5, 6, 7])
c = Cart(bytes(hdr) + bytes(img))
c.frames(10)
check("バンク 2 に切り替わる", c.ram[0x304] == 0xB2, f"${c.ram[0x304]:02X}")
c.bank_log.clear(); c.frames(1, A); c.frames(5)
w8 = [v for a_, v in c.bank_log if a_ == 0x5FF8]
check("やり直すとバンクを初期値に戻してから INIT($5FF8 に 0 → 2)", w8 == [0, 2], f"$5FF8 への書き込み {w8}")
check("$5FF9-$5FFF にも初期値 1〜7", [v for a_, v in c.bank_log if a_ > 0x5FF8] == [1, 2, 3, 4, 5, 6, 7])

print("全部 OK" if ok else "NG あり")
sys.exit(0 if ok else 1)

