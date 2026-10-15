"""Run generated 6502 code; validate hidden page, VBlank budget and flips."""
from pathlib import Path
import sys,os
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-nsf-deps-20261013'))
from py65.devices.mpu6502 import MPU
class Memory:
    def __init__(self,prg):
        self.data=bytearray(65536);self.data[0xC000:]=prg
        self.nt=bytearray(2048);self.palette=bytearray(32)
        self.staged=bytes((i*17+3)&255 for i in range(1024))
        self.pal=bytes(range(32));self.latch=0;self.addr=0;self.request=0;self.ctrl=0;self.acks=0
    def __getitem__(self,a):
        if a==0x2002:self.latch=0;return 0x80
        if a==0x5F10:return self.request
        if 0x6000<=a<0x6400:return self.staged[a-0x6000]
        if 0x5D00<=a<0x5D20:return self.pal[a-0x5D00]
        return self.data[a]
    def __setitem__(self,a,v):
        v&=255
        if a==0x2006:
            if not self.latch:self.addr=v<<8
            else:self.addr=(self.addr&0xff00)|v
            self.latch^=1
        elif a==0x2007:
            if 0x2000<=self.addr<0x3000:self.nt[(self.addr-0x2000)&2047]=v
            elif 0x3F00<=self.addr<0x3F20:self.palette[self.addr-0x3F00]=v
            self.addr+=1
        elif a==0x2000:self.ctrl=v
        elif a==0x5F11:
            bank=v&1
            assert ((self.ctrl>>4)&1)==bank and (self.ctrl&1)==bank
            assert self.nt[bank*1024:(bank+1)*1024]==self.staged
            assert self.palette==self.pal
            self.request=0;self.acks+=1
        self.data[a]=v
mem=Memory(Path(sys.argv[1]).read_bytes());cpu=MPU(memory=mem,pc=None)
for _ in range(30000):
    cpu.step()
    if mem.ctrl==0x80 and mem.data[0x2001]==0x0A:break
else:raise AssertionError('Reset did not enable rendering')
main=cpu.pc;budgets=[];visible=0
for frame in range(6):
    target=visible^1
    mem.staged=bytes((i*19+frame*47+11)&255 for i in range(1024))
    old_page=bytes(mem.nt[visible*1024:(visible+1)*1024]);old_palette=bytes(mem.palette)
    mem.pal=bytes((i+frame*3)&63 for i in range(32));mem.request=1|(target<<1)
    for chunk in range(8):
        start=cpu.processorCycles;cpu.nmi()
        for _ in range(3000):
            cpu.step()
            if cpu.pc==main:break
        else:raise AssertionError('NMI did not return')
        budgets.append(cpu.processorCycles-start)
        if chunk<7:
            assert mem.ctrl==(0x80 if visible==0 else 0x91)
            assert mem.nt[visible*1024:(visible+1)*1024]==old_page
            assert mem.palette==old_palette and mem.request
        else:assert mem.request==0 and mem.acks==frame+1
    visible=target
assert max(budgets)<2273,max(budgets)
print(f'PASS: 6 alternating frames, hidden NT/palette preserved until final VBlank, NMI max {max(budgets)} cycles')
