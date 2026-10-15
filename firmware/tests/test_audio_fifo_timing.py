"""Execute the diagnostic PIO source's branches for all 256 sample values."""
from pathlib import Path
import sys
source=Path(sys.argv[1]).read_text().splitlines()
code=[];labels={};wrap=None;bottom=None
for line in source:
    line=line.split(';')[0].strip()
    if not line:continue
    if line=='.wrap_target':wrap=len(code);continue
    if line=='.wrap':bottom=len(code)-1;continue
    if line.startswith('.'):continue
    if line.endswith(':'):labels[line[:-1]]=len(code);continue
    code.append(line)
durations=[];duties=[]
for sample in range(256):
    pc=wrap;osr=sample;shifted=0;x=0;y=0;pin=0;ticks=0;high=0
    while True:
        inst=code[pc];next_pc=pc+1;ticks+=1;high+=pin
        if inst=='pull block':osr=sample;shifted=0
        elif inst=='out x, 8':x=osr&255;osr>>=8;shifted+=8
        elif inst=='mov y, isr':y=255
        elif inst=='set pins, 0':pin=0
        elif inst=='set pins, 1':pin=1
        elif inst=='out null, 2':osr>>=2;shifted+=2
        elif inst=='jmp x!=y skip':
            if x!=y:next_pc=labels['skip']
        elif inst=='jmp y-- count':
            if y:next_pc=labels['count']
            y=(y-1)&0xffffffff
        elif inst=='jmp !osre cycle':
            if shifted<32:next_pc=labels['cycle']
        else:raise AssertionError(inst)
        if pc==bottom and next_pc==pc+1:break
        pc=next_pc
        assert ticks<7000
    durations.append(ticks);duties.append(high)
assert set(durations)=={6206},set(durations)
assert all(a<b for a,b in zip(duties,duties[1:]))
print('PASS: all 256 samples take 6206 PIO cycles; monotonic duty; FIFO word consumed completely')
