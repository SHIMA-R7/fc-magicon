"""Actual standalone C parser, cart, audio ring and 6502 driver; no device access."""
from pathlib import Path
import ctypes as C
import json,os,struct,subprocess,sys,tempfile,zlib

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'standalone_video'
sys.path.insert(0,str(Path(tempfile.gettempdir())/'fc-nsf-deps-20261013'))
from py65.devices.mpu6502 import MPU

WRAPPER=r'''
#define CART_HOST 1
#define FC_REMOTE_DMA 1
#define FC_REMOTE_FULL 1
static unsigned diag_chr_lookup[8192];
#include "baseline/cart.c"
#include "fcpv.h"
#include "pcm_ring.h"
bool host_irq;
static pcm_ring_state audio;
static uint32_t ring[PCM_RING_SIZE];
static pcm_refill_deadline refill_deadline;
__declspec(dllexport) void init(void) {
#if FC_PLAYER_COLD_BOOT
    cart_boot_reset_protocol();
#endif
    cart_info_t i;cart_load((const uint8_t*)"FCRD",4,&i);
}
__declspec(dllexport) void cold_publish(void) {
#if FC_PLAYER_COLD_BOOT
    cart_boot_publish();
#endif
}
__declspec(dllexport) void cold_load(void) {cart_info_t i;cart_load((const uint8_t*)"FCRD",4,&i);}
__declspec(dllexport) unsigned cold_active(void) {
#if FC_PLAYER_COLD_BOOT
    return cart_boot_active();
#else
    return 1;
#endif
}
__declspec(dllexport) unsigned read_byte(unsigned a) {
    unsigned h=((a&0x7fff)<<8)|B_RW|(a<0x8000 ? B_ROMSEL : 0);
#if FC_PLAYER_COLD_BOOT
    if(!cart_boot_active())return cart_boot_cpu_access(h)&255;
#endif
#if FC_PLAYER_FAST_READS
    uint32_t r;if(remote_fast_read(h,&r))return r&255;
#endif
    return remote_cpu_access(h)&255;
}
__declspec(dllexport) void write_byte(unsigned a,unsigned v) {
#if FC_PLAYER_COLD_BOOT
    if(!cart_boot_active()) {
        unsigned h=((a&0x7fff)<<8)|(a<0x8000 ? B_ROMSEL : 0);
        cart_boot_cpu_access(h);cart_boot_cpu_access(v);return;
    }
#endif
    remote_write(a,v);
}
__declspec(dllexport) unsigned stage(const uint8_t *p) {return cart_video_stage(p);}
__declspec(dllexport) unsigned pending(void) {return rd_ready;}
__declspec(dllexport) unsigned visible(void) {return rd_visible_bank;}
__declspec(dllexport) unsigned *lookup(void) {return diag_chr_lookup;}
__declspec(dllexport) unsigned fast_audit(void) {
#if FC_PLAYER_FAST_READS
    uint32_t reply;
    for(unsigned a=0;a<65536;a++) {
        uint32_t h=((a&0x7fff)<<8)|B_RW|(a<0x8000?B_ROMSEL:0);
        bool fast=remote_fast_read(h,&reply);
        bool selected=a>=0x8000 || (a>=0x6000&&a<0x6400) || (a>=0x5d00&&a<0x5d20);
        if(fast!=selected)return a+1;
        if(fast && reply!=(remote_cpu_access(h)|0x80000000u))return a+1;
        if(remote_fast_read(h&~B_RW,&reply))return a+1;
    }
    wr_pending=true;
    bool handled=remote_fast_read(0x01000000u,&reply);
    wr_pending=false;
    if(handled)return 0x10001;
#endif
    return 0;
}
__declspec(dllexport) unsigned validate(const uint8_t *p,unsigned n,unsigned crc) {
    fcpv_info i;if(!fcpv_parse(p,n,&i))return 0;
    return !crc || fcpv_crc32(p+64,i.total-64)==i.crc;
}
__declspec(dllexport) unsigned due(unsigned frame,unsigned played,unsigned fps) {
    fcpv_info i={.rate=32000,.fps_num=fps,.fps_den=1};return fcpv_frame_due(&i,frame,played);
}
__declspec(dllexport) void audio_init(const uint8_t *p,unsigned n) {pcm_ring_init(&audio,ring,p,n);}
__declspec(dllexport) unsigned audio_get(unsigned index) {return ring[index&(PCM_RING_SIZE-1)];}
__declspec(dllexport) unsigned audio_refill(unsigned index) {return pcm_ring_refill(&audio,ring,index);}
__declspec(dllexport) void deadline_init(void) {refill_deadline=(pcm_refill_deadline){.last_us=1000};}
__declspec(dllexport) unsigned deadline_check(unsigned now_us) {return pcm_refill_on_time(&refill_deadline,now_us);}
'''

def main():
    media_path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'sim/standalone-video-20261014/pv-30s-4fps.fcpv'
    cold='--cold' in sys.argv
    horizontal='--horizontal' in sys.argv
    capability='--palette-capability' in sys.argv
    legacy_palette='--legacy-palette' in sys.argv
    capability_fault='--capability-fault' in sys.argv
    chr_readback='--chr-readback' in sys.argv
    fast_reads='--fast-reads' in sys.argv
    palette_log='--palette-log' in sys.argv
    palette_readback='--palette-readback' in sys.argv or palette_log
    frame_readback='--frame-readback' in sys.argv or palette_readback
    readback='--readback' in sys.argv or chr_readback or frame_readback or capability
    nt_fault='--nt-fault' in sys.argv
    nt_fault_offset=int(sys.argv[sys.argv.index('--nt-fault-offset')+1],0) if '--nt-fault-offset' in sys.argv else None
    if nt_fault_offset is not None:assert nt_fault and 0<=nt_fault_offset<1024
    chr_fault='--chr-fault' in sys.argv
    pal_fault='--pal-fault' in sys.argv
    data=media_path.read_bytes();h=struct.unpack('<4s15I',data[:64]);count=h[3];record_bytes=h[8]
    zig=next(Path(r'C:\Users\Yugo\pico\zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='fc-standalone-test-',ignore_cleanup_errors=True) as d:
        folder=Path(d);(folder/'test.c').write_text(WRAPPER,encoding='utf-8')
        dll=folder/'test.dll'
        subprocess.run([str(zig),'cc','-shared','-O2',f'-DFC_PLAYER_COLD_BOOT={int(cold)}',f'-DFC_PLAYER_READBACK={int(readback)}',f'-DFC_PLAYER_CHR_READBACK={int(chr_readback)}',f'-DFC_PLAYER_FRAME_READBACK={int(frame_readback)}',f'-DFC_PLAYER_PALETTE_READBACK={int(palette_readback)}',f'-DFC_PLAYER_PALETTE_CAPABILITY={int(capability)}',f'-DFC_PLAYER_PALETTE_LOG={int(palette_log)}',f'-DFC_PLAYER_FAST_READS={int(fast_reads)}','-I',str(SRC),'-I',str(ROOT/'sim'),
            str(folder/'test.c'),'-o',str(dll)],check=True,timeout=120)
        lib=C.CDLL(str(dll));lib.lookup.restype=C.POINTER(C.c_uint32)
        buf=C.create_string_buffer(data)
        assert lib.validate(buf,len(data),1)
        for field,value in [(1,2),(2,63),(3,0xffffffff),(4,0),(4,9),(5,0),(6,0),(8,5151),
                            (9,0),(10,0xffffffff),(11,len(data)+1),(13,0),(14,1),(15,1)]:
            bad=bytearray(data);struct.pack_into('<I',bad,4*field,value)
            assert not lib.validate(C.create_string_buffer(bytes(bad)),len(bad),1),(field,value)
        assert not lib.validate(buf,63,1) and not lib.validate(buf,len(data)-1,1)
        bad=bytearray(data);bad[-1]^=1
        assert not lib.validate(C.create_string_buffer(bytes(bad)),len(bad),1)
        print('PASS: actual C parser validates generated file and rejects length/overflow/header/CRC faults')

        lib.init()
        if fast_reads:assert lib.fast_audit()==0
        class Memory:
            def __init__(self):
                self.ram=bytearray(32768);self.nt=bytearray(2048);self.pal=bytearray(32)
                self.latch=0;self.addr=0;self.ctrl=0;self.acks=0;self.record=None;self.read_buffer=0xa5;self.corrupt_chr=False
            def __getitem__(self,a):
                if a==0x2002:self.latch=0;return 0x80
                if a==0x2007:
                    if 0x3f00<=self.addr<0x3f20:
                        if legacy_palette:
                            value=self.read_buffer;self.read_buffer=self.nt[self.nt_index(self.addr-0x1000)]
                        else:value=self.pal[(self.addr-0x3f00)&31]^(1 if capability_fault else 0)
                        self.addr+=1
                        return value|0xc0 # palette upper bits are not colour data
                    old=self.read_buffer
                    if self.addr<0x2000:self.read_buffer=(lib.lookup()[self.addr]&255)^(1 if self.corrupt_chr else 0)
                    else:self.read_buffer=self.nt[self.nt_index(self.addr)]
                    self.addr=(self.addr+1)&0x3fff
                    return old
                if a>=0x5000:return lib.read_byte(a)
                return self.ram[a&0x7ff] if a<0x2000 else self.ram[a]
            def nt_index(self,addr):
                offset=(addr-0x2000)&0xfff
                bank=(offset>>11)&1 if horizontal else (offset>>10)&1
                return bank*1024+(offset&1023)
            def __setitem__(self,a,v):
                if a==0x2006:
                    self.addr=((self.addr&255)|(v<<8)) if not self.latch else ((self.addr&0xff00)|v)
                    self.latch^=1
                elif a==0x2007:
                    if 0x2000<=self.addr<0x3000:self.nt[self.nt_index(self.addr)]=v
                    if 0x3f00<=self.addr<0x3f20:self.pal[self.addr-0x3f00]=v
                    self.addr+=1
                elif a==0x2000:self.ctrl=v
                if a>=0x5000:
                    if a==0x5f11:
                        assert (self.ctrl&1)==(v&1)==((self.ctrl>>4)&1)
                        assert self.nt[(v&1)*1024:((v&1)+1)*1024]==self.record[4096:5120]
                        assert self.pal==self.record[5120:]
                        self.acks+=1
                    lib.write_byte(a,v)
                elif a<0x2000:self.ram[a&0x7ff]=v
                else:self.ram[a]=v
        if cold:
            lib.cold_publish()
            early_memory=Memory();early_cpu=MPU(memory=early_memory,pc=None)
            assert early_cpu.pc==0x8000 and not lib.cold_active()
            for _ in range(30000):
                early_cpu.step()
                if early_memory.ctrl==0x80 and early_memory.ram[0x2001]==0x0a:break
            else:raise AssertionError('early-ready startup did not reach player')
            assert lib.cold_active()
            print('PASS: player ready before first FC read still enters bootstrap and hands off correctly')
            lib.init()
        mem=Memory();cpu=MPU(memory=mem,pc=None)
        if cold:
            assert cpu.pc==0x8000 and not lib.cold_active()
            for _ in range(300):
                cpu.step()
                if cpu.pc==0x0200:break
            else:raise AssertionError('early ROM did not enter FC RAM')
            for _ in range(1000):
                cpu.step();assert 0x0200<=cpu.pc<0x020e and not lib.cold_active()
            # Recreate the full driver while the FC is executing only the bootstrap/RAM.
            lib.cold_load()
            for _ in range(200):cpu.step();assert not lib.cold_active()
            lib.cold_publish()
            print('PASS: actual early C responder holds FC in RAM across deferred player load')
        for _ in range(30000):
            cpu.step()
            if mem.ctrl==0x80 and mem.ram[0x2001]==0x0a:break
        else:raise AssertionError('driver did not enable rendering')
        main_pc=cpu.pc;budgets=[]
        assert lib.cold_active()
        tested_count=1 if readback and not frame_readback else count
        for frame in range(tested_count):
            record=data[64+frame*record_bytes:64+(frame+1)*record_bytes]
            visible=lib.visible();lookup=lib.lookup()
            old_chr=list(lookup[visible*4096:(visible+1)*4096])
            old_nt=bytes(mem.nt[visible*1024:(visible+1)*1024]);old_pal=bytes(mem.pal)
            rb=C.create_string_buffer(record);assert lib.stage(rb)
            assert not lib.stage(rb) # cannot overwrite a frame awaiting the FC's ACK
            assert list(lookup[visible*4096:(visible+1)*4096])==old_chr
            assert bytes(x&255 for x in lookup[(visible^1)*4096:((visible^1)+1)*4096])==record[:4096]
            mem.record=record
            if fast_reads:assert lib.fast_audit()==0
            for chunk in range(7):
                begin=cpu.processorCycles;cpu.nmi()
                for _ in range(3000):
                    cpu.step()
                    if cpu.pc==main_pc:break
                else:raise AssertionError('NMI did not return')
                budgets.append(cpu.processorCycles-begin)
                if chunk<6:
                    assert lib.pending() and lib.visible()==visible
                    assert mem.nt[visible*1024:(visible+1)*1024]==old_nt and mem.pal==old_pal
                else:assert not lib.pending() and lib.visible()==(visible^1) and mem.acks==frame+1
            if capability:
                chunks=2;errors=0
                for trial in range(2):
                    begin=cpu.processorCycles;cpu.nmi()
                    for _ in range(4000):
                        cpu.step()
                        if cpu.pc==main_pc:break
                    else:raise AssertionError('capability NMI did not return')
                    budgets.append(cpu.processorCycles-begin)
                expected=4 if capability_fault else 3 if legacy_palette else 2
                assert lib.read_byte(0x5f20)==expected
                counts=[lib.read_byte(a) for a in (0x5f24,0x5f25,0x5f26)]
                assert counts==([0,0,64] if capability_fault else [0,64,0] if legacy_palette else [64,0,0]),counts
                colours=set()
                for tick in range(120):
                    begin=cpu.processorCycles;cpu.nmi()
                    for _ in range(4000):
                        cpu.step()
                        if cpu.pc==main_pc:break
                    else:raise AssertionError('display NMI did not return')
                    budgets.append(cpu.processorCycles-begin);colours.add(mem.pal[0])
                    assert lib.read_byte(0x5f20)==expected
                assert colours=={0x1a,0x12},colours
                print(f'PASS: palette capability result={expected}, counts={counts}, green/blue alternation, max NMI={max(budgets)}')
            elif readback:
                bank=lib.visible()
                if nt_fault:
                    for i in (range(1024) if nt_fault_offset is None else [nt_fault_offset]):mem.nt[bank*1024+i]^=1
                if pal_fault:
                    for i in range(16):mem.pal[i]^=1
                mem.corrupt_chr=chr_fault
                chunks=128 if chr_readback else 32
                for chunk in range(chunks):
                    begin=cpu.processorCycles;cpu.nmi()
                    for _ in range(4000):
                        cpu.step()
                        if cpu.pc==main_pc:break
                    else:raise AssertionError('readback NMI did not return')
                    budgets.append(cpu.processorCycles-begin)
                    if chunk<chunks-1:assert lib.read_byte(0x5f20)==1
                assert max(budgets)<2273,max(budgets)
                fault=chr_fault if chr_readback else nt_fault
                assert lib.read_byte(0x5f20)==(3 if fault else 4 if palette_readback and pal_fault else 2)
                errors=lib.read_byte(0x5f21)+256*lib.read_byte(0x5f22)
                assert errors==((1 if nt_fault_offset is not None and not chr_readback else chunks*32) if fault else 0),errors
                if palette_log:
                    assert lib.read_byte(0x5f54)==int(nt_fault)
                    if nt_fault:
                        offset=nt_fault_offset or 0
                        assert lib.read_byte(0x5f50)+256*lib.read_byte(0x5f51)==offset
                        assert lib.read_byte(0x5f52)==(record[4096+offset]^1)
                        assert lib.read_byte(0x5f53)==record[4096+offset]
                if frame_readback:
                    expected_palette=bytearray(record[5120:])
                    if pal_fault:
                        for i in range(16):expected_palette[i]^=1
                    assert mem.pal==expected_palette
                    if palette_readback and not fault:assert lib.read_byte(0x5f23)==(16 if pal_fault else 0)
                    if palette_log and not fault:
                        assert bytes(lib.read_byte(0x5f30+i) for i in range(16))==mem.pal[:16]
                        assert bytes(lib.read_byte(0x5f40+i) for i in range(16))==record[5120:5136]
                else:assert mem.pal==bytes([(0x12 if chr_readback else 0x16) if fault else 0x1a])*32
                print(f'PASS: actual 6502 buffered readback, {chunks*32} bytes, errors={errors}, max NMI={max(budgets)} cycles')
        assert max(budgets)<2273
        print(f'PASS: actual C cart + 6502, {tested_count} frames, atomic 7-VBlank flips, maximum {max(budgets)} CPU cycles')

        pcm=bytes((i*17+5)&255 for i in range(25000));ab=C.create_string_buffer(pcm);lib.audio_init(ab,len(pcm))
        for start in range(0,len(pcm)+10000,37):
            for pos in range(start,min(start+37,len(pcm)+10000)):
                assert lib.audio_get(pos)==(pcm[pos] if pos<len(pcm) else 128),pos
            lib.audio_refill(min(start+37,len(pcm)+10000)&8191)
        print('PASS: actual PCM ring preserves samples across wraps, then outputs unsigned silence 128')
        lib.deadline_init()
        assert lib.deadline_check(1999) and lib.deadline_check(201998)
        assert not lib.deadline_check(401998) and not lib.deadline_check(401999)
        print('PASS: refill deadline accepts <200ms service gaps, latches fault at 200ms and does not resume stale audio')
        for fps in (4,8):
            n=1
            for played in range(99*32000):
                if n<99*fps and lib.due(n,played,fps):
                    due=n*32000/fps
                    assert 3400<due-played<3500,(fps,n,played)
                    n+=1
            assert n==99*fps
        print('PASS: sample-clock scheduling reaches all 4/8fps frames over 99s without accumulating drift')
        # Simulate display acknowledgements on actual NTSC VBlank boundaries,
        # while running the real C schedule against a quantised 32026.71Hz DAC.
        display_errors=[]
        for fps in (4,8):
            next_frame=1;pending=None;chunks=0;next_vblank=32026.710276/60.098813
            interval=next_vblank
            for played in range(0,99*32000,16):
                while next_vblank<=played:
                    if pending is not None:
                        chunks-=1
                        if not chunks:
                            display_errors.append(next_vblank/32000-pending/fps)
                            pending=None
                    next_vblank+=interval
                if next_frame<99*fps and pending is None and lib.due(next_frame,played,fps):
                    pending=next_frame;next_frame+=1;chunks=7
            assert next_frame==99*fps and pending is None
        maximum_display_error_ms=max(map(abs,display_errors))*1000
        assert maximum_display_error_ms<12,maximum_display_error_ms
        print(f'PASS: modelled 4/8fps display ACKs over 99s, A/V error <= {maximum_display_error_ms:.2f}ms (not hardware measured)')
        result=dict(frames=tested_count,vblanks_per_frame=7,max_nmi_cpu_cycles=max(budgets),
            vblank_budget=2273,actual_c_parser=True,actual_c_cart=True,actual_c_audio_ring=True,
            py65_driver=True,cold_boot_protocol=cold,modelled_max_av_error_ms=maximum_display_error_ms,hardware_verified=False)
        result['fast_reads']=fast_reads
        result['mirroring']='horizontal' if horizontal else 'vertical'
        suffix=('.cold-tests' if cold else '.tests')+('-horizontal' if horizontal else '')+'.json'
        if readback:
            result.update(readback_bytes=64 if capability else 4096 if chr_readback else 1024,injected_nt_fault=nt_fault,injected_chr_fault=chr_fault,detected_errors=errors)
            suffix=('.readback-fault' if nt_fault else '.readback-pass')+('-horizontal' if horizontal else '')+'.json'
            if frame_readback:suffix='.frames'+('.fault' if nt_fault else '.pass')+('-horizontal' if horizontal else '')+'.json'
            if palette_readback:
                result['palette_errors']=16 if pal_fault else 0
                suffix=('.palette-log' if palette_log else '.palette')+('.fault' if pal_fault else '.pass')+'.json'
            if fast_reads:suffix='.fast'+suffix
            if capability:
                result.update(capability_result=expected,capability_counts=counts,legacy_palette_model=legacy_palette,capability_fault_model=capability_fault)
                suffix='.capability'+('.legacy' if legacy_palette else '.fault' if capability_fault else '.modern')+'.json'
            if chr_readback:suffix='.chr'+('.fault' if chr_fault else '.pass')+('-horizontal' if horizontal else '')+'.json'
        media_path.with_suffix(suffix).write_text(json.dumps(result,indent=2),encoding='utf-8')
        import _ctypes
        _ctypes.FreeLibrary(lib._handle)

if __name__=='__main__':main()
