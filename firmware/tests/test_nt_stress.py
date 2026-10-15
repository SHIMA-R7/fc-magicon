"""Exercise the actual FC-local 6502 diagnostic against the actual C bus handler."""
from pathlib import Path
import ctypes as C,json,os,subprocess,sys,tempfile
from test_standalone_video import WRAPPER,ROOT,SRC,MPU
sys.path.insert(0,str(ROOT/'tools'))
from read_nt_stress import decode

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'normal'
    assert mode in ('normal','stuck-bit','alias','cpu-normal','cpu-fault')
    cpu_window=mode.startswith('cpu-')
    settle='--settle-ppu' in sys.argv
    zig=next(Path(r'C:\Users\Yugo\pico\zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='fc-nt-stress-',ignore_cleanup_errors=True) as d:
        d=Path(d);source=d/'test.c';dll=d/'test.dll'
        source.write_text(WRAPPER+'\n__declspec(dllexport) void stress_ack(unsigned s){cart_nt_stress_ack(s);}\n__declspec(dllexport) unsigned source_ready(unsigned s,unsigned p,unsigned b){return cart_nt_cpu_source(s,p,b);}\n')
        subprocess.run([str(zig),'cc','-shared','-O2','-DFC_PLAYER_NT_STRESS=1','-DFC_PLAYER_COLD_BOOT=1',
            '-DFC_PLAYER_FAST_READS=1',f'-DFC_PLAYER_CPU_WINDOW={int(cpu_window)}',f'-DFC_PLAYER_PPU_SETTLE={int(settle)}','-I',str(SRC),'-I',str(ROOT/'sim'),str(source),'-o',str(dll)],check=True)
        lib=C.CDLL(str(dll));lib.init();lib.cold_publish()
        class Memory:
            def __init__(self):
                self.ram=bytearray(2048);self.nt=bytearray(2048);self.pal=bytearray(32)
                self.latch=0;self.addr=0;self.buffer=0;self.ctrl=0;self.mask=0;self.reads=0;self.writes=0
                self.first_ppuaddr_cycle=None
            def index(self,addr):
                offset=(addr-0x2000)&0xfff;bank=(offset>>10)&1
                return (0 if mode=='alias' else bank*1024)+(offset&1023)
            def __getitem__(self,a):
                if a<0x2000:return self.ram[a&2047]
                if a==0x2002:self.latch=0;return 0x80
                if a==0x2007:
                    assert self.mask==0
                    old=self.buffer;self.buffer=self.nt[self.index(self.addr)]
                    if mode=='stuck-bit':self.buffer&=0xfd
                    self.addr=(self.addr+1)&0x3fff;self.reads+=1;return old
                if a>=0x5000:return lib.read_byte(a)^(2 if mode=='cpu-fault' and 0x6000<=a<0x6400 else 0)
                return 0
            def __setitem__(self,a,v):
                if a<0x2000:self.ram[a&2047]=v
                elif a==0x2000:self.ctrl=v;assert not v&0x80
                elif a==0x2001:self.mask=v;assert v==0
                elif a==0x2006:
                    if self.first_ppuaddr_cycle is None:self.first_ppuaddr_cycle=cpu.processorCycles
                    self.addr=((v<<8)|(self.addr&255)) if not self.latch else ((self.addr&0xff00)|v)
                    self.latch^=1
                elif a==0x2007:
                    if self.addr<0x3000:self.nt[self.index(self.addr)]=v;self.writes+=1
                    elif 0x3f00<=self.addr<0x3f20:self.pal[self.addr-0x3f00]=v
                    self.addr=(self.addr+1)&0x3fff
                elif a>=0x5000:lib.write_byte(a,v)
        mem=Memory();cpu=MPU(memory=mem,pc=None);reports=[];steps=0;last_request=0
        while steps<40000000:
            cpu.step();steps+=1
            if steps%100==0:
                if cpu_window:
                    request=lib.read_byte(0x5f73)
                    if 1<=request<=104 and request!=last_request:
                        assert request==last_request+1
                        assert lib.source_ready(request,lib.read_byte(0x5f70),lib.read_byte(0x5f71))
                        last_request=request
                seq=lib.read_byte(0x5f7e)
                if seq==len(reports)+1 and len(reports)<52:
                    r=decode(bytes(lib.read_byte(0x5f80+i) for i in range(32)))
                    assert r['signature']==(0xc5 if cpu_window else 0xa5) and r['sequence']==seq
                    reports.append(r);lib.stress_ack(seq)
                if len(reports)==52 and lib.read_byte(0x5f20) in (2,3):break
        else:raise AssertionError('diagnostic timed out')
        assert len(reports)==52 and mem.writes==52*2048 and mem.reads==52*4*1025
        clean=mode in ('normal','cpu-normal')
        assert lib.read_byte(0x5f20)==(2 if clean else 3)
        for _ in range(200):cpu.step()
        assert mem.pal[0]==(0x1a if clean else 0x16) and mem.addr==0x2000 and mem.mask==0
        for k,r in enumerate(reports):
            assert (r['pattern'],r['bank'],r['repeat'])==(k%13,(k//13)%2,k//26)
            assert r['ppu_base']==(0x2000 if r['bank']==0 else 0x2c00)
            if clean:assert r['errors']==0 and r['first_offset']==65535 and r['xor_mask']==0 and not any(r['bit_errors'])
            if cpu_window:
                assert r['cpu_errors']==(2048 if mode=='cpu-fault' else 0)
                assert r['cpu_xor_mask']==(2 if mode=='cpu-fault' else 0)
                if mode=='cpu-fault':assert r['errors']==4096 and r['xor_mask']==2
            if mode=='stuck-bit':
                assert r['xor_mask'] in (0,2) and all(v==0 for i,v in enumerate(r['bit_errors']) if i!=1)
                assert r['errors']==r['bit_errors'][1]
                if r['errors']:assert r['first_actual']==(r['first_expected']&0xfd)
            if mode=='alias':assert r['errors']==(4096 if r['bank']==0 else 0)
        assert clean or sum(r['errors'] for r in reports)>0
        if cpu_window:assert last_request==104
        if settle:assert mem.first_ppuaddr_cycle>51000,mem.first_ppuaddr_cycle
        result=dict(mode=mode,rounds=52,written_bytes=mem.writes,read_bytes=mem.reads,
            total_errors=sum(r['errors'] for r in reports),steps=steps,cpu_cycles=cpu.processorCycles,hardware_verified=False)
        result.update(settle_ppu=settle,first_ppuaddr_cycle=mem.first_ppuaddr_cycle)
        out=ROOT/'sim/standalone-video-20261014'/f'nt-stress-{mode}{"-settled" if settle else ""}-tests.json';out.write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
        import _ctypes
        _ctypes.FreeLibrary(lib._handle)

if __name__=='__main__':main()
