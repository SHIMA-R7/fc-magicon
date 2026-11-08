"""Run the actual direct-boot cart handler and 6502 player up to palette writes."""
import ctypes as C
from pathlib import Path
import subprocess,tempfile
from test_standalone_video import WRAPPER,ROOT,SRC,MPU

zig=next(Path(r'C:\Users\Yugo\pico\zig').rglob('zig.exe'))
with tempfile.TemporaryDirectory(prefix='fc-direct-boot-',ignore_cleanup_errors=True) as directory:
    directory=Path(directory);source=directory/'test.c';dll=directory/'test.dll'
    source.write_text(WRAPPER)
    subprocess.run([str(zig),'cc','-shared','-O2','-DFC_PLAYER_COLD_BOOT=1',
        '-DFC_PLAYER_DIRECT_BOOT=1','-DFC_PLAYER_FAST_READS=1',
        '-I',str(SRC),'-I',str(ROOT/'sim'),str(source),'-o',str(dll)],check=True)
    lib=C.CDLL(str(dll));lib.init()
    assert lib.cold_active()==1
    vector=lib.read_byte(0xfffc)|(lib.read_byte(0xfffd)<<8)
    assert vector in (0x8000,0xc000) and lib.read_byte(vector)==0x78,hex(vector)
    class Memory:
        def __init__(self):self.ram=bytearray(2048);self.ppu_writes=0
        def __getitem__(self,a):
            if a<0x2000:return self.ram[a&2047]
            if a==0x2002:return 0x80
            if a>=0x5000:return lib.read_byte(a)
            return 0
        def __setitem__(self,a,v):
            if a<0x2000:self.ram[a&2047]=v
            elif a==0x2007:self.ppu_writes+=1
            elif a>=0x5000:lib.write_byte(a,v)
    memory=Memory();cpu=MPU(memory=memory,pc=None)
    for steps in range(100000):
        cpu.step()
        if memory.ppu_writes>=32:break
    else:raise AssertionError('Direct player did not reach palette initialization')
    print('PASS: direct SRAM reset vector, active without bootstrap handshake, 32 PPU palette writes;',steps+1,'instructions')
