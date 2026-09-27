"""テスト ROM 用のごく小さな 6502 アセンブラ(Python の関数呼び出しで書く)。
    a = Asm(0xC000)
    a.label("reset"); a.sei(); a.lda_imm(0); a.sta(0x2000); a.bne("reset") ...
    rom = a.build(size=0x4000, vectors={"nmi": "nmi", "reset": "reset", "irq": "nmi"})
命令は、テスト ROM と NSF ドライバーで使うものだけ用意している。分岐先が ±127 を超えるとエラーにする。
build(vectors=None) ならベクターを書かない(NSF ドライバーのように、ROM の途中に置くコード)。
"""

IMPLIED = {"sei": 0x78, "cld": 0xD8, "txs": 0x9A, "inx": 0xE8, "dey": 0x88, "dex": 0xCA, "iny": 0xC8,
           "rti": 0x40, "rts": 0x60, "nop": 0xEA, "tax": 0xAA, "txa": 0x8A, "tay": 0xA8, "tya": 0x98,
           "pha": 0x48, "pla": 0x68, "php": 0x08, "plp": 0x28, "clc": 0x18, "sec": 0x38, "cli": 0x58,
           "asl_a": 0x0A, "lsr_a": 0x4A, "rol_a": 0x2A, "ror_a": 0x6A}
IMM = {"lda": 0xA9, "ldx": 0xA2, "ldy": 0xA0, "cpx": 0xE0, "cpy": 0xC0, "cmp": 0xC9, "and": 0x29, "ora": 0x09,
       "eor": 0x49, "adc": 0x69, "sbc": 0xE9}
ABS = {"sta": 0x8D, "stx": 0x8E, "sty": 0x8C, "lda_abs": 0xAD, "bit": 0x2C, "jmp": 0x4C, "jsr": 0x20,
       "lda_absx": 0xBD, "inc_abs": 0xEE, "dec_abs": 0xCE, "rol_abs": 0x2E, "cmp_abs": 0xCD, "and_abs": 0x2D,
       "ora_abs": 0x0D, "eor_abs": 0x4D, "ldx_abs": 0xAE, "ldy_abs": 0xAC, "sta_absx": 0x9D, "sta_absy": 0x99,
       "lda_absy": 0xB9, "adc_abs": 0x6D, "sbc_abs": 0xED, "jmp_ind": 0x6C}
ZP = {"inc_zp": 0xE6, "lda_zp": 0xA5, "sta_zp": 0x85, "ora_zp": 0x05, "and_zp": 0x25, "dec_zp": 0xC6,
      "lda_indy": 0xB1}                   # lda_indy = LDA (zp),Y
REL = {"bpl": 0x10, "bmi": 0x30, "bne": 0xD0, "beq": 0xF0, "bcc": 0x90, "bcs": 0xB0}


class Asm:
    def __init__(self, org):
        self.org = org
        self.items = []          # (種類, 値, 表示)
        self.labels = {}
        self.data = []

    def _size(self, it):
        kind, v, _ = it
        return {"imp": 1, "imm": 2, "zp": 2, "rel": 2, "abs": 3, "bytes": len(v) if kind == "bytes" else 0,
                "label": 0}[kind]

    def label(self, name):
        self.items.append(("label", name, name + ":"))

    def bytes_(self, b, note=""):
        self.items.append(("bytes", bytes(b), note or ".byte " + ",".join(f"${x:02X}" for x in b)))

    def __getattr__(self, name):
        if name in IMPLIED:
            return lambda: self.items.append(("imp", (IMPLIED[name],), name.upper()))
        if name.endswith("_imm") and name[:-4] in IMM:
            return lambda v: self.items.append(("imm", (IMM[name[:-4]], v & 0xFF), f"{name[:-4].upper()} #${v & 0xFF:02X}"))
        if name in ABS:
            return lambda v: self.items.append(("abs", (ABS[name], v), f"{name.split('_')[0].upper()} {v if isinstance(v, str) else f'${v:04X}'}{',X' if name.endswith('_absx') else ''}"))
        if name in ZP:
            return lambda v: self.items.append(("zp", (ZP[name], v & 0xFF), f"{name.split('_')[0].upper()} ${v & 0xFF:02X}"))
        if name in REL:
            return lambda lab: self.items.append(("rel", (REL[name], lab), f"{name.upper()} {lab}"))
        raise AttributeError(name)

    def build(self, size, vectors=None):
        addr = self.org
        for it in self.items:
            if it[0] == "label":
                self.labels[it[1]] = addr
            addr += self._size(it)
        out, listing, addr = bytearray(), [], self.org
        for kind, v, note in self.items:
            if kind == "label":
                listing.append(note)
                continue
            if kind in ("imp", "imm", "zp"):
                b = bytes(v)
            elif kind == "abs":
                t = self.labels[v[1]] if isinstance(v[1], str) else v[1]
                b = bytes([v[0], t & 0xFF, t >> 8])
            elif kind == "rel":
                d = self.labels[v[1]] - (addr + 2)
                if not -128 <= d <= 127:
                    raise ValueError(f"分岐が遠すぎる: {note}")
                b = bytes([v[0], d & 0xFF])
            else:
                b = v
            listing.append(f"  ${addr:04X}: {' '.join(f'{x:02X}' for x in b[:8]):<24} {note}")
            out += b
            addr += len(b)
        rom = bytearray([0xEA] * size)
        rom[:len(out)] = out
        if len(out) > size:
            raise ValueError(f"コードが {size} バイトに入らない({len(out)} バイト)")
        for off, key in ((size - 6, "nmi"), (size - 4, "reset"), (size - 2, "irq")) if vectors else ():
            a = self.labels[vectors[key]]
            rom[off], rom[off + 1] = a & 0xFF, a >> 8
        return rom, listing


def write_header(path, name, rom, listing, comment):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"// {comment}\n")
        for line in listing:
            f.write("// " + line + "\n")
        f.write(f"static const unsigned char {name}[{len(rom)}] = {{\n")
        for i in range(0, len(rom), 16):
            f.write("    " + ", ".join(f"0x{x:02X}" for x in rom[i:i + 16]) + ",\n")
        f.write("};\n")


