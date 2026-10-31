"""Generate and emulate native APU + seven-chunk video NMIs (requires py65)."""
from pathlib import Path
import sys,json,subprocess,tempfile
from py65.devices.mpu6502 import MPU
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='fc-apu-driver-') as directory:
    header=Path(directory)/'apu_driver.h'
    subprocess.run([sys.executable,str(ROOT/'standalone_video/gen_video_driver.py'),str(header),'--apu-stream'],check=True)
    prg=header.with_suffix('.bin').read_bytes()
regs=(0x4000,0x4002,0x4003,0x4004,0x4006,0x4007,0x4008,0x400a,0x400b,0x400c,0x400e,0x400f)
values=[0xbf,200,0xf9,0xb8,100,0xfa,0xff,150,0xf9,0x3a,6,0xf8]
class Mem:
    def __init__(self):self.ram=bytearray(2048);self.io=bytearray(256);self.apu=[];self.ready=0;self.pending=0;self.mask=4095
    def __getitem__(self,a):
        if a>=0x8000:return prg[(a-0x8000)&0x3fff]
        if a<0x2000:return self.ram[a&2047]
        if a==0x2002:return 0x80
        if a==0x5f10:return self.pending
        if 0x5f00<=a<0x6000:return self.io[a&255]
        if 0x5c00<=a<=0x5c0b:return values[a-0x5c00]
        if a==0x5c0c:return self.mask&255
        if a==0x5c0d:return self.mask>>8
        if a==0x5c0e:return self.ready
        return 0
    def __setitem__(self,a,v):
        if a<0x2000:self.ram[a&2047]=v
        if 0x4000<=a<=0x4017:self.apu.append((a,v))
        if 0x5f00<=a<0x6000:
            self.io[a&255]=v
            if a==0x5f14:self.ready=0
m=Mem();c=MPU(memory=m,pc=None)
for _ in range(50000):c.step()
assert list(m.ram[3:11])==[0]*8,list(m.ram[3:11])
pc=c.pc;sp=c.sp;budgets=[]
for frame in range(14):
    m.apu.clear();m.ready=1;m.pending=3
    before=c.processorCycles;c.nmi()
    for _ in range(5000):
        c.step()
        if c.pc==pc and c.sp==sp:break
    else:raise AssertionError('NMI did not return')
    assert [v for v in m.apu if v[0] in regs]==list(zip(regs,values)),m.apu
    assert m.ready==0
    budgets.append(c.processorCycles-before)
assert max(budgets)<2273,budgets
m.apu.clear();m.ready=1;m.mask=0;before=c.processorCycles;c.nmi()
for _ in range(5000):
    c.step()
    if c.pc==pc and c.sp==sp:break
assert not [v for v in m.apu if v[0] in regs] and m.ready==0
result={'full_register_writes_verified':12,'nmi_cycles':budgets,'max_nmi_cycles':max(budgets),'budget':2273,'empty_mask_verified':True}
print(json.dumps(result,indent=2))
