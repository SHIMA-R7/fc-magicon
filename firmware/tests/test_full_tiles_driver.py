"""Emulate the complete per-frame palette/attribute update and VBlank ACK."""
from pathlib import Path
import subprocess,sys,tempfile
from py65.devices.mpu6502 import MPU
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
    h=Path(d)/'driver.h'
    subprocess.run([sys.executable,str(root/'standalone_video/gen_full_tiles_driver.py'),str(h),'--movie'],check=True)
    prg=h.with_suffix('.bin').read_bytes()
class Mem:
    def __init__(self):
        self.ram=bytearray(2048);self.ready=0;self.writes=[];self.addr=0;self.toggle=0;self.acks=0
    def __getitem__(self,a):
        if a>=0x8000:return prg[a&0x3fff]
        if a<0x2000:return self.ram[a&2047]
        if a==0x2002:self.toggle=0;return 128
        if a==0x5f10:return self.ready
        if 0x5d00<=a<0x5d20:return (a&31)+1
        if 0x63c0<=a<=0x63ff:return (a&63)^0xa5
        return 0
    def __setitem__(self,a,v):
        if a<0x2000:self.ram[a&2047]=v
        if a==0x2006:
            self.addr=(v<<8) if not self.toggle else (self.addr&0xff00)|v
            self.toggle^=1
        if a==0x2007:self.writes.append((self.addr,v));self.addr+=1
        if a==0x5f11:
            # This ACK is the only point where RP may switch frame banks.
            assert len(self.writes)==96
            self.ready=0;self.acks+=1
m=Mem();c=MPU(memory=m,pc=None)
for _ in range(30000):c.step()
pc,sp=c.pc,c.sp
budgets=[]
for ready in (0,1,0,1,1,0):
    m.ready=ready;m.writes.clear();before=c.processorCycles;acks=m.acks;c.nmi()
    for _ in range(3000):
        c.step()
        if c.pc==pc and c.sp==sp:break
    else:raise AssertionError('NMI failed to return')
    if ready:
        assert m.writes==[(0x3f00+i,i+1) for i in range(32)]+[(0x23c0+i,i^0xa5) for i in range(64)]
        assert m.acks==acks+1 and m.ready==0
    else:assert not m.writes and m.acks==acks
    budgets.append(c.processorCycles-before)
assert max(budgets)<2273,budgets
print('PASS full-frame driver: palette/attributes precede bank ACK; idle NMIs skip updates; cycles',budgets)
