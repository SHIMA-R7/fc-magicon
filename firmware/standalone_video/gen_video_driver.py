"""Video-only remote driver: stage hidden NT, flip CHR/NT/palette in VBlank."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from asm6502 import Asm
capability='--palette-capability' in sys.argv
chr_readback='--chr-readback' in sys.argv
palette_log='--palette-log' in sys.argv
palette_readback='--palette-readback' in sys.argv or palette_log
frame_readback='--frame-readback' in sys.argv or palette_readback
readback='--readback' in sys.argv or chr_readback or frame_readback or capability
desktop_keyboard='--desktop-keyboard' in sys.argv
a=Asm(0xC000)
a.label('reset');a.sei();a.cld();a.ldx_imm(255);a.txs()
a.lda_imm(0);a.sta(0x2000);a.sta(0x2001);a.sta(0x4010)
for zp in (3,4,5,6,7,8,9,10):a.sta_zp(zp)
if readback:a.sta(0x5F20)
a.lda_imm(0x40);a.sta(0x4017)
for name in ('vbl1','vbl2'):
    a.label(name);a.bit(0x2002);a.bpl(name)
a.lda_imm(0x3F);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
for i in range(32):a.lda_abs(0x5D00+i);a.sta(0x2007)
a.lda_imm(0x20);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
for page in range(8):
    label=f'init_nt_{page}';a.ldx_imm(0);a.label(label)
    a.lda_absx(0x6000+(page%4)*256);a.sta(0x2007);a.inx();a.bne(label)
a.label('vbl3');a.bit(0x2002);a.bpl('vbl3')
a.lda_imm(0x20);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006);a.sta(0x2005);a.sta(0x2005)
a.lda_imm(0x80);a.sta(0x2000);a.lda_imm(0x0A);a.sta(0x2001)
a.label('main');a.jmp('main')
a.label('nmi');a.pha();a.txa();a.pha();a.tya();a.pha();a.bit(0x2002)
a.lda_imm(0);a.sta_zp(6)
a.lda_abs(0x5F10);a.and_imm(1);a.bne('pending');a.jmp('verify' if readback else 'restore')
a.label('pending');a.lda_abs(0x5F10);a.lsr_a();a.and_imm(1);a.sta_zp(5)
chunks=[(start,min(147,1024-start)) for start in range(0,1024,147)]
for chunk in range(len(chunks)-1):
    a.lda_zp(3);a.cmp_imm(chunk);a.bne(f'next_{chunk}');a.jmp(f'chunk_{chunk}');a.label(f'next_{chunk}')
a.jmp(f'chunk_{len(chunks)-1}')
for chunk,(start,count) in enumerate(chunks):
    a.label(f'chunk_{chunk}');a.lda_zp(5);a.beq(f'low_{chunk}')
    # Diagonal tables $2000/$2C00 remain distinct under either H or V mirroring.
    a.lda_imm(0x2C+start//256);a.jmp(f'addr_{chunk}')
    a.label(f'low_{chunk}');a.lda_imm(0x20+start//256);a.label(f'addr_{chunk}')
    a.sta(0x2006);a.lda_imm(start&255);a.sta(0x2006)
    for i in range(count):a.lda_abs(0x6000+start+i);a.sta(0x2007)
    a.jmp('copied')
a.label('copied');a.inc_zp(3);a.lda_zp(3);a.cmp_imm(len(chunks));a.beq('flip');a.jmp('restore')
a.label('flip');a.lda_imm(0);a.sta_zp(3)
a.lda_imm(0x3F);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
for i in range(32):a.lda_abs(0x5D00+i);a.sta(0x2007)
a.lda_zp(5);a.sta_zp(4);a.lda_imm(1);a.sta_zp(6)
if readback:
    a.sta_zp(10);a.sta(0x5F20)
    a.lda_imm(0)
    if palette_log:a.sta(0x5F54)
    for zp in ((7,8,9,11,12,13) if capability else (7,8,9)):a.sta_zp(zp)
    a.jmp('restore')
    a.label('verify');a.lda_zp(10);a.bne('verify_active');a.jmp('restore')
    a.label('verify_active')
    if capability:
        from palette_capability import emit_capability
        emit_capability(a)
    else:
        # 32 bytes per VBlank, buffered $2007 read after resetting PPUADDR.
        a.lda_zp(7)
        for _ in range(5):a.asl_a()
        a.sta_zp(14)
        a.lda_zp(7)
        for _ in range(3):a.lsr_a()
        a.sta_zp(12);a.clc();a.adc_imm(0x70 if chr_readback else 0x60);a.sta_zp(15)
        a.lda_zp(4);a.beq('verify_base0');a.lda_imm(0x10 if chr_readback else 0x2C);a.jmp('verify_base')
        a.label('verify_base0');a.lda_imm(0 if chr_readback else 0x20);a.label('verify_base')
        a.clc();a.bytes_([0x65,12],'ADC $0C');a.sta(0x2006)
        a.lda_zp(14);a.sta(0x2006);a.lda_abs(0x2007) # discard delayed-read buffer
        a.ldy_imm(0);a.label('verify_byte');a.lda_abs(0x2007)
        if palette_log:
            a.sta_zp(17)
            a.bytes_([0xB1,14],'LDA ($0E),Y');a.sta_zp(18)
            a.bytes_([0xC5,17],'CMP $11');a.beq('verify_match')
            a.lda_zp(8);a.ora_zp(9);a.bne('nt_log_done')
            a.tya();a.clc();a.bytes_([0x65,14],'ADC $0E');a.sta(0x5F50)
            a.lda_zp(12);a.adc_imm(0);a.sta(0x5F51)
            a.lda_zp(17);a.sta(0x5F52)
            a.lda_zp(18);a.sta(0x5F53)
            a.lda_imm(1);a.sta(0x5F54);a.label('nt_log_done')
        else:
            a.bytes_([0xD1,14],'CMP ($0E),Y');a.beq('verify_match')
        a.inc_zp(8);a.bne('verify_match');a.inc_zp(9)
        a.label('verify_match');a.iny();a.cpy_imm(32);a.bne('verify_byte')
        a.inc_zp(7);a.lda_zp(7);a.cmp_imm(128 if chr_readback else 32);a.beq('verify_done');a.jmp('restore')
        a.label('verify_done');a.lda_imm(0);a.sta_zp(10)
        a.lda_zp(8);a.sta(0x5F21);a.lda_zp(9);a.sta(0x5F22)
        a.lda_zp(8);a.ora_zp(9);a.beq('verify_pass')
        a.lda_imm(3);a.sta(0x5F20)
        if frame_readback:a.jmp('restore')
        else:a.lda_imm(0x12 if chr_readback else 0x16);a.jmp('verify_colour')
        a.label('verify_pass')
        if palette_readback:
            # Palette reads bypass the delayed $2007 buffer; upper two bits are open bus.
            a.lda_imm(0x3F);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
            for i in range(16):
                a.lda_abs(0x2007);a.and_imm(0x3F)
                if palette_log:
                    a.sta(0x5F30+i);a.sta_zp(17)
                    a.lda_abs(0x5D00+i);a.sta(0x5F40+i);a.bytes_([0xC5,17],'CMP $11')
                else:a.cmp_abs(0x5D00+i)
                a.beq(f'palette_match_{i}');a.inc_zp(8);a.label(f'palette_match_{i}')
            a.lda_zp(8);a.sta(0x5F23);a.beq('palette_pass')
            a.lda_imm(4);a.sta(0x5F20);a.jmp('restore')
            a.label('palette_pass')
        a.lda_imm(2);a.sta(0x5F20)
        if not frame_readback:
            a.lda_imm(0x1A)
            a.label('verify_colour');a.sta_zp(11)
            a.lda_imm(0x3F);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
            a.lda_zp(11)
            for _ in range(32):a.sta(0x2007)

a.label('restore');a.lda_zp(4);a.beq('visible0')
a.lda_imm(0x93);a.sta(0x2000);a.lda_imm(0x2C);a.jmp('scroll')
a.label('visible0');a.lda_imm(0x80);a.sta(0x2000);a.lda_imm(0x20)
a.label('scroll');a.sta(0x2006);a.lda_imm(0);a.sta(0x2006);a.sta(0x2005);a.sta(0x2005)
a.lda_zp(6);a.beq('inputs');a.lda_zp(4);a.sta(0x5F11)
a.label('inputs');a.lda_imm(1);a.sta(0x4016);a.lda_imm(0);a.sta(0x4016);a.ldx_imm(8)
a.label('pad');a.lda_abs(0x4016);a.lsr_a();a.rol_abs(0x5F00);a.dex();a.bne('pad')

if desktop_keyboard:
    # Match Famicom-Expand-USB-Adapter's 500us column settling. All PPU
    # operations above are already complete; the scan may run past VBlank.
    a.lda_imm(5);a.sta(0x4016);a.jsr('kbwait');a.ldy_imm(0)
    a.label('kbscan');a.lda_imm(4);a.sta(0x4016);a.jsr('kbwait')
    a.lda_abs(0x4017);a.and_imm(0x1E);a.lsr_a();a.sta_zp(16)
    a.lda_imm(6);a.sta(0x4016);a.jsr('kbwait')
    a.lda_abs(0x4017);a.and_imm(0x1E);a.asl_a();a.asl_a();a.asl_a();a.ora_zp(16)
    a.sta_absy(0x5F01);a.iny();a.cpy_imm(9);a.bne('kbscan')
    a.lda_imm(0);a.sta(0x4016)
a.inc_abs(0x5F0F);a.pla();a.tay();a.pla();a.tax();a.pla();a.rti()

if desktop_keyboard:
    a.label('kbwait');a.ldx_imm(177);a.label('kbwait_loop');a.dex();a.bne('kbwait_loop');a.rts()
a.label('irq');a.rti()
prg,listing=a.build(16384,{'nmi':'nmi','reset':'reset','irq':'irq'})
def arr(name,data):
    return f'static const uint8_t {name}[{len(data)}]={{\n'+''.join(' '+','.join(f'0x{v:02x}' for v in data[i:i+16])+',\n' for i in range(0,len(data),16))+'};\n'
out=Path(sys.argv[1]);out.write_text('#pragma once\n#include <stdint.h>\n#define RD_PAL 0x5D00\n#define RD_ATTR 0x5D20\n#define RD_OAM 0x5E00\n#define RD_IO 0x5F00\n'+arr('remote_prg',prg)+arr('remote_spr_chr',bytes(64)))
out.with_suffix('.bin').write_bytes(prg)
print('Desktop keyboard driver generated; 500us settling' if desktop_keyboard else 'Readback diagnostic driver generated' if readback else 'Atomic video driver generated; sprites and keyboard disabled for video trial')
