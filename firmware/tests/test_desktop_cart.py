"""Actual desktop C commit path: exact pre-fitted framebuffer, both banks, fast palette."""
from pathlib import Path
import ctypes as C,subprocess,tempfile,sys
import numpy as np
from PIL import Image
from test_standalone_video import WRAPPER,ROOT,SRC
sys.path.insert(0,str(ROOT/'tools'))
import nesframe as nf
from tile_fit_native import fit_tiles_native

EXTRA=r'''
__declspec(dllexport) unsigned desktop_idle(void){return cart_desktop_idle();}
__declspec(dllexport) unsigned desktop_send(const uint8_t *fb,const uint8_t *pal,const uint8_t *attr){
    if(rd_ready)return 0;
    memcpy(rd_fb_back,fb,15360);cart_remote_commit(pal,attr,0,0,false);return 1;
}
__declspec(dllexport) void desktop_fb(uint8_t *out){
    unsigned bank=rd_visible_bank^1u;
    for(unsigned t=0;t<960;t++)for(unsigned y=0;y<8;y++)for(unsigned p=0;p<2;p++)
        out[(((t/32)*8+y)*32+t%32)*2+p]=diag_chr_lookup[bank*4096+rd_nt[t]*16+y+p*8]&255;
}
'''

def main():
    zig=next(Path('C:/Users/Yugo/pico/zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='desktop-cart-',ignore_cleanup_errors=True) as d:
        folder=Path(d);src=folder/'test.c';dll=folder/'test.dll';src.write_text(WRAPPER+EXTRA)
        subprocess.run([str(zig),'cc','-shared','-O2','-DFC_REMOTE_DESKTOP=1','-DFC_PLAYER_FAST_READS=1','-I',str(SRC),'-I',str(ROOT/'sim'),str(src),'-o',str(dll)],check=True)
        lib=C.CDLL(str(dll));lib.init();assert lib.fast_audit()==0
        images=np.memmap('C:/Users/Yugo/pico/work-standalone-video-20261014/source-full-8fps-stretch-4x3.rgb',mode='r',dtype=np.uint8,shape=(792,240,256,3))
        for k in (56,160,360):
            fr,_=fit_tiles_native(nf.encode(Image.fromarray(images[k]),'color',dither=0))
            fb=C.create_string_buffer(fr.fb);pal=C.create_string_buffer(bytes(fr.pal));attr=C.create_string_buffer(fr.attr)
            assert lib.desktop_send(fb,pal,attr)==1 and lib.desktop_send(fb,pal,attr)==0
            assert lib.fast_audit()==0
            assert bytes(lib.read_byte(0x5d00+i) for i in range(32))==bytes(fr.pal)
            assert bytes(lib.read_byte(0x63c0+i) for i in range(64))==fr.attr
            got=C.create_string_buffer(15360);lib.desktop_fb(got);assert got.raw==fr.fb
            visible=lib.visible();lib.write_byte(0x5f11,visible^1)
            assert not lib.pending() and lib.visible()==visible^1
        assert lib.desktop_idle() and lib.pending()
        assert not lib.desktop_idle()
        lib.write_byte(0x5f11,lib.visible()^1);assert not lib.pending()
        print('PASS: actual C FCFR commit preserves pre-fitted image and attributes, fast palette replies, busy protection and alternating banks')
        print('PASS: idle screen is staged once and respects the outstanding-frame ACK')

if __name__=='__main__':main()
