"""Static full-tile trial: nametable IDs are irrelevant; attributes stay native."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from asm6502 import Asm
a=Asm(0xc000)
native='--native-pcm' in sys.argv
ram='--ram' in sys.argv
if ram and not native:raise ValueError('RAM driver requires native PCM')
if native and '--movie' not in sys.argv:raise ValueError('Native PCM requires movie mode')
a.label('reset');a.sei();a.cld();a.ldx_imm(255);a.txs()
a.lda_imm(0);a.sta(0x2000);a.sta(0x2001);a.sta(0x4015);a.sta(0x4010)
a.lda_imm(0x40);a.sta(0x4017)
for label in ['wait1','wait2']:
    a.label(label);a.bit(0x2002);a.bpl(label)
a.lda_imm(0x3f);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
for i in range(32):a.lda_abs(0x5d00+i);a.sta(0x2007)
a.lda_imm(0x20);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
for page in range(4):
    a.ldx_imm(0);a.label('clear'+str(page));a.sta(0x2007);a.inx();a.bne('clear'+str(page))
a.lda_imm(0x23);a.sta(0x2006);a.lda_imm(0xc0);a.sta(0x2006)
for i in range(64):a.lda_abs(0x63c0+i);a.sta(0x2007)
a.label('wait3');a.bit(0x2002);a.bpl('wait3')
a.lda_imm(0);a.sta_zp(3);a.sta(0x2005);a.sta(0x2005)
a.lda_imm(0 if native else 0x80);a.sta(0x2000);a.lda_imm(0x0a);a.sta(0x2001)

if native:
    initializer=a
    if ram:a=Asm(0x0200)
    # Each path, including VBlank work, takes exactly 224 CPU cycles.
    # Eight 12-byte jobs complete 96 writes within one NTSC VBlank.
    def align():
        address=a.org+sum(a._size(it) for it in a.items)
        a.bytes_([0xea]*((-address)&(127 if ram else 255)))
    def delay(cycles):
        n=(cycles-1)//5;left=cycles-(5*n+1)
        if left==1:n-=1;left+=5
        assert 1<=n<=255 and left in (0,2,3,4,6),(cycles,n,left)
        label='delay_'+str(len(a.items))
        a.ldx_imm(n);a.label(label);a.dex();a.bne(label)
        if left==3:a.bytes_([0x24,0]) # three-cycle zero-page BIT
        elif left:
            for _ in range(left//2):a.nop()
    def sample():a.lda_abs(0x5f20);a.sta(0x4011)
    a.jmp('pcm_main')
    align();a.label('pcm_main');sample();a.bit(0x2002);a.bpl('pcm_idle')
    a.inc_zp(3);a.lda_zp(3);a.sta(0x5f0f)
    a.lda_abs(0x5f10);a.and_imm(1);a.beq('pcm_no_frame')
    delay(224-(8+4+2+12+4+2+2+3));a.jmp('video_job0')
    a.label('pcm_no_frame');delay(224-(8+4+2+12+4+2+3+3));a.jmp('pcm_main')
    a.label('pcm_idle');delay(224-(8+4+3+3));a.jmp('pcm_main')
    entries=[(0x5d00+i,False) for i in range(32)]+[(0x63c0+i,i==0) for i in range(64)]
    for job in range(8):
        align();a.label('video_job'+str(job));sample();cost=8
        if job==0:
            a.lda_imm(0x3f);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006);cost+=12
        for address,attr_start in entries[job*12:(job+1)*12]:
            if attr_start:
                a.lda_imm(0x23);a.sta(0x2006);a.lda_imm(0xc0);a.sta(0x2006);cost+=12
            a.lda_abs(address);a.sta(0x2007);cost+=8
        if job==7:
            a.lda_imm(1);a.sta(0x5f11)
            a.lda_imm(0);a.sta(0x2005);a.sta(0x2005);cost+=16
        delay(224-cost-3);a.jmp('pcm_main' if job==7 else 'video_job'+str(job+1))
    a.label('native_irq');a.rti()
    if ram:
        used=sum(a._size(it) for it in a.items)
        size=(used+255)&~255
        assert size<=0x600,(used,size)
        runtime,_=a.build(size)
        address=a.org
        for item in a.items:
            if item[0]=='rel':
                assert ((address+2)&~255)==(a.labels[item[1][1]]&~255),item
            address+=a._size(item)
        for page in range(size//256):
            initializer.ldx_imm(0)
            label='copy_runtime_'+str(page)
            initializer.label(label)
            initializer.lda_absx(0xc800+page*256)
            initializer.sta_absx(0x0200+page*256)
            initializer.inx();initializer.bne(label)
        initializer.jmp(a.labels['pcm_main'])
        assert sum(initializer._size(it) for it in initializer.items)<0x800
        prg,_=initializer.build(16384)
        prg[0x800:0x800+size]=runtime
        irq=a.labels['native_irq']
        for offset,value in ((16378,irq),(16380,initializer.labels['reset']),(16382,irq)):
            prg[offset:offset+2]=value.to_bytes(2,'little')
        print('Native DAC RAM driver',used,'bytes, reset',hex(initializer.labels['reset']),flush=True)
    else:
        prg,_=a.build(16384,{'reset':'reset','nmi':'native_irq','irq':'native_irq'})
    out=Path(sys.argv[1]);out.write_text('#pragma once\n#include <stdint.h>\nstatic const uint8_t remote_prg[16384]={'+','.join(map(str,prg))+'};\nstatic const uint8_t remote_spr_chr[64]={0};\n')
    out.with_suffix('.bin').write_bytes(prg)
    sys.exit(0)
a.label('main');a.jmp('main')
a.label('nmi');a.pha();a.bit(0x2002)
if '--movie' in sys.argv:
    a.lda_abs(0x5f10);a.and_imm(1);a.bne('update_frame');a.jmp('no_frame')
    a.label('update_frame')
    a.lda_imm(0x3f);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
    for i in range(32):a.lda_abs(0x5d00+i);a.sta(0x2007)
    a.lda_imm(0x23);a.sta(0x2006);a.lda_imm(0xc0);a.sta(0x2006)
    for i in range(64):a.lda_abs(0x63c0+i);a.sta(0x2007)
    a.lda_imm(1);a.sta(0x5f11)
    a.label('no_frame')
a.lda_imm(0);a.sta(0x2005);a.sta(0x2005)
a.inc_zp(3);a.lda_zp(3);a.sta(0x5f0f);a.pla();a.rti()
a.label('irq');a.rti()
prg,_=a.build(16384,{'reset':'reset','nmi':'nmi','irq':'irq'})
out=Path(sys.argv[1]);out.write_text('#pragma once\n#include <stdint.h>\nstatic const uint8_t remote_prg[16384]={'+','.join(map(str,prg))+'};\nstatic const uint8_t remote_spr_chr[64]={0};\n')
out.with_suffix('.bin').write_bytes(prg)
