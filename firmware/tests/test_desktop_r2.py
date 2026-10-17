"""Chunk-invariant sound, 3 crop levels, and actual 6502 keyboard timing."""
import sys,tempfile,subprocess,ctypes as C
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pcaudio import Resampler
import remote_pc as pc
from test_standalone_video import WRAPPER,MPU

def sound_and_view():
    for rate in (24000,32000,44100,48000,96000):
        x=np.sin(np.arange(rate*2)*2*np.pi*997/rate).astype(np.float32)
        a=Resampler(rate).process(x);r=Resampler(rate);parts=[];start=0;rng=np.random.default_rng(42)
        while start<len(x):
            end=min(len(x),start+int(rng.integers(1,1800)));parts.append(r.process(x[start:end]));start=end
        b=np.concatenate(parts)
        assert len(a)==len(b) and abs(len(b)-64000)<=2
        assert np.max(np.abs(a-b))<2e-5,(rate,np.max(np.abs(a-b)))
    print('PASS: resampling has identical counts and continuous phase across random chunk sizes at five rates')
    class Grab:
        def grab(self,source,destination):self.source=source;return None
    view=pc.View.__new__(pc.View);view.mode='fit';view.follow=True;view.stretch=True;view.zx=view.zy=0;view.g=Grab()
    oldscreen,oldcursor=pc.screen_size,pc.cursor_pos
    try:
        pc.screen_size=lambda:(1920,1080);pc.cursor_pos=lambda:(1900,1060)
        for mode,size in [('fit',(1920,1080)),('mid',(512,480)),('zoom',(256,240)),('fit',(1920,1080))]:
            assert view.mode==mode;view.grab();x,y,w,h=view.g.source
            assert (w,h)==size and x>=0 and y>=0 and x+w<=1920 and y+h<=1080
            view.cycle()
        view.mode='mid';view.grab();view.follow=False;fixed=view.g.source;pc.cursor_pos=lambda:(10,10);view.grab();assert view.g.source==fixed
        pc.screen_size=lambda:(200,150);view.mode='zoom';view.grab();assert view.g.source==(0,0,200,150)
    finally:pc.screen_size,pc.cursor_pos=oldscreen,oldcursor
    print('PASS: normal / 512x480 / 256x240 cycling, crop limits, and fixed follow mode')

def keyboard_driver():
    zig=next(Path('C:/Users/Yugo/pico/zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='desktop-keyboard-',ignore_cleanup_errors=True) as d:
        folder=Path(d);(folder/'test.c').write_text(WRAPPER)
        subprocess.run([str(zig),'cc','-shared','-O2','-DFC_REMOTE_DESKTOP=1','-DFC_PLAYER_FAST_READS=1','-I',str(ROOT/'standalone_video'),'-I',str(ROOT/'sim'),str(folder/'test.c'),'-o',str(folder/'test.dll')],check=True)
        lib=C.CDLL(str(folder/'test.dll'));lib.init()
        rows=bytes([0xfe,0xbd,0xff,0x7f,0xef,0xf7,0xfb,0xfd,0xdf])
        class Memory:
            def __init__(self):
                self.ram=bytearray(32768);self.cpu=None;self.control=0;self.latch=0;self.addr=0;self.scan_row=0;self.output=0;self.pad_index=0;self.changed=0;self.ppu_times=[]
            def __getitem__(self,a):
                if a==0x2002:self.latch=0;return 128
                if a==0x4016:
                    v=(0xa5>>(7-self.pad_index%8))&1;self.pad_index+=1;return v
                if a==0x4017:
                    assert self.cpu.processorCycles-self.changed>=880
                    bits=rows[self.scan_row%9];return (((bits>>4) if self.output==6 else bits)&15)<<1
                if a>=0x5000:return lib.read_byte(a)
                return self.ram[a&0x7ff] if a<0x2000 else self.ram[a]
            def __setitem__(self,a,v):
                if 0x2000<=a<=0x2007 and self.cpu:self.ppu_times.append(self.cpu.processorCycles)
                if a==0x2000:self.control=v
                if a==0x2006:self.addr=((v<<8)|(self.addr&255)) if not self.latch else ((self.addr&0xff00)|v);self.latch^=1
                if a==0x2007:self.addr+=1
                if a==0x4016:
                    if v==1:self.pad_index=0
                    if v==5:self.scan_row=0
                    elif v==4 and self.output==6:self.scan_row+=1
                    self.output=v;self.changed=self.cpu.processorCycles
                if a>=0x5000:lib.write_byte(a,v)
                elif a<0x2000:self.ram[a&0x7ff]=v
                else:self.ram[a]=v
        mem=Memory();cpu=MPU(memory=mem,pc=None);mem.cpu=cpu
        for _ in range(30000):
            cpu.step()
            if mem.control==128 and mem.ram[0x2001]==10:break
        else:raise AssertionError('startup')
        main=cpu.pc
        media=(ROOT/'sim/less-block-20261017/pv-full-99s-8fps-less-block.fcpv').read_bytes()
        assert lib.stage(C.create_string_buffer(media[64:64+5152]))
        total=[];ppu=[]
        for _ in range(7):
            begin=cpu.processorCycles;mem.ppu_times=[];cpu.nmi()
            for _ in range(14000):
                cpu.step()
                if cpu.pc==main:break
            else:raise AssertionError('NMI did not return')
            total.append(cpu.processorCycles-begin);ppu.append(max(mem.ppu_times)-begin)
            assert bytes(lib.read_byte(0x5f01+i) for i in range(9))==rows
            assert lib.read_byte(0x5f00)==0xa5
        assert not lib.pending() and max(total)<29700 and max(ppu)<2273,(total,ppu)
        print('PASS: actual keyboard scan/pad + 7-VBlank flip; PPU last write',max(ppu),'cycles; entire NMI',max(total),'cycles')

if __name__=='__main__':sound_and_view();keyboard_driver()
