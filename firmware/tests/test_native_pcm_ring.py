"""Exercise actual native PCM C ring: ADPCM, downsampling, wrap, EOF and fault."""
import ctypes as C,subprocess,sys,tempfile
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools'))
from ima_audio import encode,decode
zig=next(Path('C:/Users/Yugo/pico/zig').rglob('zig.exe'))
wrapper=r'''
#include "native_pcm.c"
__declspec(dllexport) int run(const uint8_t *p,unsigned n,uint8_t *out) {
 if(!native_pcm_start(p,n,32000,true))return 0;
 unsigned length=(n+3)/4;
 for(unsigned i=0;i<length+257;i++) {
  if(native_pcm_running) {
   out[i]=native_pcm_replies[native_pcm_consumed&8191]&127;
   native_pcm_consumed++;
  } else out[i]=64;
  if(i%137==0 || i+1==length)native_pcm_poll();
 }
 return !native_pcm_faulted() && !native_pcm_running;
}
__declspec(dllexport) int underrun(const uint8_t *p,unsigned n) {
 native_pcm_start(p,n,32000,true);native_pcm_consumed=8192;native_pcm_poll();
 return native_pcm_faulted() && !native_pcm_running;
}
'''
with tempfile.TemporaryDirectory() as d:
 d=Path(d);(d/'pico').mkdir();(d/'hardware').mkdir()
 (d/'pico/stdlib.h').write_text('#include <stdint.h>\n#include <stdbool.h>\ntypedef unsigned uint;\n')
 (d/'hardware/sync.h').write_text('#define __dmb() ((void)0)\n')
 (d/'test.c').write_text(wrapper)
 subprocess.run([str(zig),'cc','-O2','-shared','-I',str(d),'-I',str(root/'standalone_video'),str(d/'test.c'),'-o',str(d/'test.dll')],check=True)
 lib=C.CDLL(str(d/'test.dll'));lib.run.argtypes=[C.c_void_p,C.c_uint,C.c_void_p];lib.underrun.argtypes=[C.c_void_p,C.c_uint]
 rng=np.random.default_rng(224)
 for n in (1,257,35003,150007):
  samples=rng.integers(-32768,32768,n,dtype=np.int16);encoded=encode(samples)
  pcm=((decode(encoded,n).astype(np.int32)+32768)>>8)
  pcm=np.pad(pcm,(0,(-n)%4),constant_values=128)
  expected=((pcm.reshape(-1,4).sum(1)+2)>>3).astype(np.uint8)
  result=np.zeros(len(expected)+257,np.uint8)
  assert lib.run(encoded,n,result.ctypes.data)
  assert np.array_equal(result[:len(expected)],expected)
  assert np.all(result[len(expected):]==64) and int(result.max())<=127
  assert lib.underrun(encoded,n)
 import _ctypes
 _ctypes.FreeLibrary(lib._handle)
print('PASS native C ring: bit-exact decimation, partial blocks, wrap, EOF, underrun')
