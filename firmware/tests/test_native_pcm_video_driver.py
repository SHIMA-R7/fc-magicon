"""Check constant DAC cadence and VBlank bounds with ready/idle frame paths."""
import subprocess,sys,tempfile
from pathlib import Path
from py65.devices.mpu6502 import MPU
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
    header=Path(d)/'driver.h'
    subprocess.run([sys.executable,str(root/'standalone_video/gen_full_tiles_driver.py'),str(header),'--movie','--native-pcm'] + (['--ram'] if '--ram' in sys.argv else []),check=True)
    prg=header.with_suffix('.bin').read_bytes()

class Mem:
    def __init__(self):
        self.ram=bytearray(2048);self.cpu=None;self.status_frame=-1
        self.toggle=0;self.addr=0;self.active=False;self.writes=[]
        self.samples=[];self.acks=0;self.acked=set();self.frame_starts=[]
    def frame(self):return int(self.cpu.processorCycles//29780.6666667)
    def in_vblank(self):return self.cpu.processorCycles%29780.6666667>=29780.6666667-2273
    def __getitem__(self,a):
        if a>=0x8000:return prg[a&0x3fff]
        if a<0x2000:return self.ram[a&2047]
        if a==0x2002:
            self.toggle=0
            f=self.frame()
            if self.in_vblank() and self.status_frame!=f:
                self.status_frame=f;return 128
            return 0
        if a==0x5f20:return len(self.samples)&127
        if a==0x5f10:return int(self.frame()%4!=0 and self.frame() not in self.acked)
        if 0x5d00<=a<0x5d20:return (a&31)+1
        if 0x63c0<=a<=0x63ff:return (a&63)^0xa5
        return 0
    def __setitem__(self,a,v):
        if a<0x2000:self.ram[a&2047]=v
        if a==0x4011:
            self.active=True;self.samples.append(self.cpu.processorCycles)
        if a==0x2006:
            self.addr=v<<8 if not self.toggle else (self.addr&0xff00)|v
            self.toggle^=1
        if a==0x2007:
            if self.active:
                assert self.in_vblank(),('outside VBlank',self.cpu.processorCycles,self.addr)
                self.writes.append((self.addr,v))
            self.addr+=1
        if a==0x5f11:
            expected=[(0x3f00+i,i+1) for i in range(32)]+[(0x23c0+i,i^0xa5) for i in range(64)]
            assert self.writes==expected,(len(self.writes),self.writes[:4])
            assert self.in_vblank()
            self.writes.clear();self.acked.add(self.frame());self.acks+=1

m=Mem();c=MPU(memory=m,pc=None);m.cpu=c
while c.processorCycles<1500000:c.step()
intervals={b-a for a,b in zip(m.samples,m.samples[1:])}
assert intervals=={224},intervals
assert m.acks>25,m.acks
print('PASS native PCM/video:',len(m.samples),'samples; cadence',intervals,'cycles;',m.acks,'complete VBlank updates')
