"""Host verification of real C parser/ADPCM/ring; no device access."""
from pathlib import Path
import ctypes as C
import json,struct,subprocess,sys,tempfile,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ima_audio import encode,decode

WRAPPER=r'''
#include "fcpv.h"
#include "pcm_ring.h"
__declspec(dllexport) int parse(const uint8_t *p,unsigned n) {fcpv_info v;return fcpv_parse(p,n,&v);}
__declspec(dllexport) unsigned decode_all(const uint8_t *p,unsigned n,uint8_t *out) {
    pcm_ring_state s={.source=p,.length=n,.adpcm=true};
    for(unsigned i=0;i<n+300;i++)out[i]=pcm_ring_sample(&s);
    return s.next;
}
__declspec(dllexport) unsigned ring_all(const uint8_t *p,unsigned n,uint8_t *out) {
    pcm_ring_state s;uint32_t ring[8192];pcm_ring_init_adpcm(&s,ring,p,n);
    for(unsigned i=0;i<n+9000;i++) {
        unsigned at=i&8191;out[i]=ring[at];
        pcm_ring_refill(&s,ring,(at+1)&8191);
    }
    return s.next;
}
'''

def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('media',nargs='?',type=Path);args=ap.parse_args()
    zig=next(Path('C:/Users/Yugo/pico/zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='fcpv2-test-') as d:
        d=Path(d);(d/'test.c').write_text(WRAPPER)
        subprocess.run([str(zig),'cc','-O2','-shared','-I',str(ROOT/'standalone_video'),str(d/'test.c'),'-o',str(d/'test.dll')],check=True)
        lib=C.CDLL(str(d/'test.dll'));lib.parse.argtypes=[C.c_void_p,C.c_uint]
        for name in ('decode_all','ring_all'):getattr(lib,name).argtypes=[C.c_void_p,C.c_uint,C.c_void_p]
        rng=np.random.default_rng(19)
        inputs=[np.zeros(1,np.int16),np.full(257,32767,np.int16),np.full(8193,-32768,np.int16),rng.integers(-32768,32768,35003,dtype=np.int16),(np.sin(np.arange(64000)*2*np.pi*440/32000)*28000).astype(np.int16)]
        for samples in inputs:
            data=encode(samples);expected=((decode(data,len(samples)).astype(np.int32)+32768)>>8).astype(np.uint8)
            out=np.zeros(len(samples)+9000,np.uint8)
            assert lib.decode_all(data,len(samples),out.ctypes.data)==len(samples)
            assert np.array_equal(out[:len(samples)],expected) and np.all(out[len(samples):len(samples)+300]==128)
            assert lib.ring_all(data,len(samples),out.ctypes.data)==len(samples)
            assert np.array_equal(out[:len(samples)],expected) and np.all(out[len(samples):]==128)
        print('PASS C/Python IMA bit equality, partial blocks, clipping, ring wrap and EOF silence',flush=True)
        # Minimal valid 1-frame clip, then malformed sizes/flags/indices.
        audio=encode(np.zeros(4000,np.int16));body=bytes(5152)+audio
        h=[b'FCPV',2,64,1,8,1,32000,4000,5152,64,5216,64+len(body),zlib.crc32(body),2,256,0]
        blob=struct.pack('<4s15I',*h)+body;assert lib.parse(blob,len(blob))
        for index,value in ((1,3),(2,65),(7,0),(10,0xffffffff),(11,0xffffffff),(13,1),(14,255),(15,1)):
            bad=h.copy();bad[index]=value;b=struct.pack('<4s15I',*bad)+body;assert not lib.parse(b,len(b)),index
        for size in (0,4,63,len(blob)-1):assert not lib.parse(blob,size)
        for offset,value in ((5218,89),(5219,1)):
            bad=bytearray(blob);bad[offset]=value;assert not lib.parse(bytes(bad),len(bad))
        oldaudio=bytes([128])*4000;oldbody=bytes(5152)+oldaudio;old=h.copy();old[1]=1;old[11]=64+len(oldbody);old[12]=zlib.crc32(oldbody);old[13:]=[1,0,0]
        legacy=struct.pack('<4s15I',*old)+oldbody;assert lib.parse(legacy,len(legacy))
        fullbody=bytes(15456)+audio
        full=h.copy();full[1]=3;full[8]=15456;full[10]=64+15456
        full[11]=64+len(fullbody);full[12]=zlib.crc32(fullbody)
        fullblob=struct.pack('<4s15I',*full)+fullbody
        assert lib.parse(fullblob,len(fullblob))
        for index,value in ((1,2),(8,5152),(10,5216),(11,len(fullblob)-1)):
            bad=full.copy();bad[index]=value
            assert not lib.parse(struct.pack('<4s15I',*bad)+fullbody,len(fullblob)),index
        print('PASS full-frame v3 accepted; mixed v2/v3 record layouts rejected',flush=True)
        print('PASS v1 compatibility and malformed v2 headers/blocks rejected',flush=True)
        result=dict(c_python_bit_exact=True,ring_wrap_eof=True,legacy_v1=True,malformed_rejected=True,hardware_tested=False)
        if args.media:
            data=args.media.read_bytes();h=struct.unpack('<4s15I',data[:64]);assert lib.parse(data,len(data))
            assert zlib.crc32(data[64:])==h[12]
            audio=data[h[10]:];samples=h[7];expected=((decode(audio,samples).astype(np.int32)+32768)>>8).astype(np.uint8)
            out=np.zeros(samples+9000,np.uint8)
            assert lib.ring_all(audio,samples,out.ctypes.data)==samples
            assert np.array_equal(out[:samples],expected) and np.all(out[samples:]==128)
            result.update(frames=h[3],samples=samples,media_bytes=len(data),full_audio_c_ring_verified=True)
            args.media.with_suffix('.adpcm-tests.json').write_text(json.dumps(result,indent=2))
            print('PASS full-clip C ring matches Python reconstruction, CRC and EOF',flush=True)
        import _ctypes
        _ctypes.FreeLibrary(lib._handle)
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
