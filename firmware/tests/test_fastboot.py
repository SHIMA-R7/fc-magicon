"""Execute generated 6502 code against the actual C mailbox protocol."""
from pathlib import Path
import ctypes
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'fastboot'))
sys.path.insert(0, str(Path(tempfile.gettempdir())/'fc-nsf-deps-20261013'))
from gen_boot import generate
from py65.devices.mpu6502 import MPU

WRAPPER = r'''
#include "boot_protocol.h"
#include "nrom_image.h"
static fc_boot_state state;
static uint8_t prg[32768];
__declspec(dllexport) void init(void) {
    fc_boot_init(&state);
    for(unsigned i=0;i<sizeof prg;i++)prg[i]=0xea;
    prg[0x7ffc]=0x34;prg[0x7ffd]=0x92;
    prg[0x7ffa]=0x78;prg[0x7ffb]=0x96;
    prg[0x7ffe]=0xbc;prg[0x7fff]=0x9a;
}
__declspec(dllexport) unsigned read_byte(unsigned a) { return fc_boot_read(&state,a,prg); }
__declspec(dllexport) void write_byte(unsigned a,unsigned v) { fc_boot_write(&state,a,v); }
__declspec(dllexport) void publish(void) { atomic_store_explicit(&state.ready,true,memory_order_release); }
__declspec(dllexport) unsigned waiting(void) { return atomic_load(&state.waiting); }
__declspec(dllexport) unsigned active(void) { return state.game_active; }
__declspec(dllexport) unsigned load_image(const uint8_t *image,unsigned size) {
    uint8_t chr[8192];bool vertical=false;
    return fc_load_nrom_image(image,size,prg,chr,&vertical)==NULL ? 1+vertical : 0;
}
'''

def main():
    generate()
    zig=next(Path(r'C:\Users\Yugo\pico\zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='fc-fastboot-') as folder:
        folder=Path(folder)
        source=folder/'protocol.c';source.write_text(WRAPPER)
        dll=folder/'protocol.dll'
        subprocess.run([str(zig),'cc','-O2','-shared','-I',str(ROOT/'fastboot'),str(source),'-o',str(dll)],check=True,timeout=120)
        lib=ctypes.CDLL(str(dll))
        def image(banks=1,flags=0,reset=0x9234):
            import struct
            header=b'NES\x1a'+bytes([banks,1,flags])+bytes(9)
            data=bytearray(b'\xea'*(banks*16384))
            data[-4:-2]=struct.pack('<H',reset)
            nes=header+data+bytes(8192)
            return b'FCMG'+struct.pack('<III',len(nes),sum(nes),0)+nes
        def load(data):
            buffer=ctypes.create_string_buffer(data)
            return lib.load_image(buffer,len(data))
        assert load(image())==1 and load(image(2,1))==2
        for invalid in (b'',image()[:-1],image(flags=4),image(flags=0x40),image(reset=0),
                        b'FCLB'+image()[4:],image()[:20]+b'X'+image()[21:]):
            lib.init()
            assert load(invalid)==0 and not lib.active() and not lib.waiting()
        print('PASS: actual C loader accepts 16/32KB NROM, rejects malformed/unsupported images')
        class Memory:
            def __init__(self): self.ram=bytearray(32768)
            def __getitem__(self,a):
                return lib.read_byte(a) if a>=0x8000 else self.ram[a&0x7ff] if a<0x2000 else self.ram[a]
            def __setitem__(self,a,v):
                if a>=0x8000: lib.write_byte(a,v)
                elif a<0x2000: self.ram[a&0x7ff]=v
                else: self.ram[a]=v
        for early in (False,True):
            lib.init()
            lib.write_byte(0xfff1,0) # a stray write must not acknowledge the copy
            if early: lib.publish()
            assert lib.read_byte(0xfff0)==0 and not lib.active()
            memory=Memory();cpu=MPU(memory=memory,pc=None)
            for _ in range(300):
                cpu.step()
                if lib.waiting(): break
            assert lib.waiting() and 0x200<=cpu.pc<0x20e
            if not early:
                for _ in range(2000):
                    cpu.step()
                    assert 0x200<=cpu.pc<0x20e and not lib.active()
                lib.publish()
            for _ in range(12):
                cpu.step()
                if cpu.pc==0x9234: break
            assert cpu.pc==0x9234 and lib.active()
            assert cpu.p&4 # IRQ masked on entry to game's reset code
            assert memory[0x2000]==0 and memory[0x2001]==0 and memory[0x4015]==0
            # Mailbox addresses now return actual game data; game IRQ/NMI unchanged.
            assert lib.read_byte(0xfff0)==0xea and lib.read_byte(0xfff1)==0xea
            assert lib.read_byte(0xfffa)==0x78 and lib.read_byte(0xfffe)==0xbc
            cpu.reset();assert cpu.pc==0x9234
            print(f'PASS: actual C/6502 bootstrap, early_ready={early}, RAM wait, handoff and reset')
        # Unprepared/failed load never publishes game vectors.
        lib.init();memory=Memory();cpu=MPU(memory=memory,pc=None)
        for _ in range(10000): cpu.step()
        assert lib.waiting() and not lib.active() and 0x200<=cpu.pc<0x20e
        print('PASS: failed/unpublished load stays in internal RAM')
        # ctypes must release its DLL before TemporaryDirectory removes the files.
        import _ctypes
        _ctypes.FreeLibrary(lib._handle)

if __name__=='__main__': main()
