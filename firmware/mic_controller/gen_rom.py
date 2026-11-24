"""Silent CPU-only cartridge: read 2P A, show blue idle / red recording."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from asm6502 import Asm

def build():
    a = Asm(0x8000)
    a.label('reset'); a.sei(); a.cld(); a.ldx_imm(255); a.txs()
    a.lda_imm(0); a.sta(0x2000); a.sta(0x2001); a.sta(0x4015); a.sta(0x4010)
    a.lda_imm(64); a.sta(0x4011); a.lda_imm(0)
    a.sta_zp(0)
    a.lda_imm(0x40); a.sta(0x4017)
    for name in ['v1', 'v2']:
        a.label(name); a.bit(0x2002); a.bpl(name)
    a.label('frame'); a.bit(0x2002); a.bpl('frame')
    a.jsr('pad')
    a.lda_imm(0x3f); a.sta(0x2006); a.lda_imm(0); a.sta(0x2006)
    a.lda_abs(0x5f02); a.beq('idle'); a.cmp_imm(2); a.beq('green')
    a.lda_imm(0x16); a.jmp('color')
    a.label('green'); a.lda_imm(0x2a); a.jmp('color')
    a.label('idle'); a.lda_imm(0x21)
    a.label('color'); a.sta(0x2007)
    # Restore address outside palette space while rendering is disabled.
    a.lda_imm(0); a.sta(0x2006); a.sta(0x2006)
    a.lda_abs(0x5f21); a.beq('frame'); a.jmp('pcm')
    a.label('pad')
    a.lda_imm(1); a.sta(0x4016); a.lda_imm(0); a.sta(0x4016)
    a.lda_abs(0x4017); a.and_imm(1); a.sta(0x5f00)
    a.lda_abs(0x4017); a.and_imm(1); a.sta(0x5f03)
    a.inc_zp(0); a.lda_zp(0); a.sta(0x5f01); a.rts()
    # Fixed page prevents a taken delay branch from gaining a page-cross cycle.
    end = 0x8000 + sum(a._size(it) for it in a.items)
    a.bytes_(bytes([0xea]) * (0x8200-end))
    a.label('pcm'); a.lda_abs(0x5f20); a.sta(0x4011)
    a.jsr('pad'); a.lda_abs(0x5f21); a.beq('finished')
    a.ldx_imm(30); a.label('delay'); a.dex(); a.bne('delay'); a.jmp('pcm')
    a.label('finished'); a.lda_imm(64); a.sta(0x4011); a.jmp('frame')
    return a.build(size=32768, vectors={'reset':'reset','nmi':'reset','irq':'reset'})[0]

if __name__ == '__main__':
    rom = build()
    Path(__file__).with_name('rom.h').write_text(
        'static const uint8_t mic_rom[32768] = {' + ','.join(map(str, rom)) + '};\n')
