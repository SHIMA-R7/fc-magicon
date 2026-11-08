"""Verify the real bounded C decoder and indexed FCPV4 against Python LZ4."""
import ctypes as C,hashlib,json,struct,subprocess,sys,tempfile,zlib
from pathlib import Path
import numpy as np
import lz4.block
root=Path(__file__).resolve().parents[1]
zig=next(Path('C:/Users/Yugo/pico/zig').rglob('zig.exe'))
wrapper=r'''
#include "fcpv.h"
__declspec(dllexport) int parse(const uint8_t *p,unsigned n){fcpv_info v;return fcpv_parse(p,n,&v);}
__declspec(dllexport) int frame(const uint8_t *p,unsigned n,unsigned index,uint8_t *out){
 fcpv_info v;if(!fcpv_parse(p,n,&v))return 0;return fcpv_unpack_frame(p,&v,index,out,15456);
}
__declspec(dllexport) int unpack(const uint8_t *p,unsigned n,uint8_t *out,unsigned size){return lz4_block_decode(p,n,out,size);}
'''
with tempfile.TemporaryDirectory() as d:
 d=Path(d);(d/'test.c').write_text(wrapper)
 subprocess.run([str(zig),'cc','-O2','-shared','-I',str(root/'standalone_video'),str(d/'test.c'),'-o',str(d/'test.dll')],check=True)
 lib=C.CDLL(str(d/'test.dll'));lib.parse.argtypes=[C.c_void_p,C.c_uint];lib.frame.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_void_p];lib.unpack.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
 rng=np.random.default_rng(1939)
 for n in (0,1,4,15,16,280,15456):
  for source in (bytes(n),rng.integers(0,256,n,dtype=np.uint8).tobytes(),(b'ABCD'*((n+3)//4))[:n]):
   packed=lz4.block.compress(source,store_size=False)
   dest=np.full(n+32,0xa7,np.uint8)
   assert lib.unpack(packed,len(packed),dest.ctypes.data,n)
   assert dest[:n].tobytes()==source and np.all(dest[n:]==0xa7)
   if n>1:assert not lib.unpack(packed,len(packed),dest.ctypes.data,n-1)
   for cut in range(min(8,len(packed))):
    assert not lib.unpack(packed[:cut],cut,dest.ctypes.data,n)
 for bad in (b'\x00\x00\x00',b'\x00\x01\x00',b'\xf0\xff',b'\x10A\x00\x00'):
  dest=np.full(15488,0xa7,np.uint8);assert not lib.unpack(bad,len(bad),dest.ctypes.data,15456);assert np.all(dest[15456:]==0xa7)
 print('PASS C LZ4: literal/match lengths, overlap, incompressible data, truncation and bounds')
 if len(sys.argv)>1:
  media=Path(sys.argv[1]);data=media.read_bytes();h=struct.unpack('<4s15I',data[:64]);assert h[1]==4 and lib.parse(data,len(data))
  assert zlib.crc32(data[64:])==h[12]
  digest=hashlib.sha256();dest=np.empty(15456,np.uint8)
  for i in range(h[3]):
   assert lib.frame(data,len(data),i,dest.ctypes.data),i
   begin,end=struct.unpack_from('<II',data,64+i*4)
   expected=bytearray(lz4.block.decompress(data[begin+1:end],uncompressed_size=15456))
   if data[begin]:
    for j in range(64,15360):expected[j]^=expected[j-64]
   assert dest.tobytes()==expected,i
   digest.update(dest)
  manifest=json.loads(media.with_name('manifest.json').read_text());assert digest.hexdigest()==manifest['expanded_sha256']
  # Reject broken index tables and unknown frame transforms.
  for where,value in ((64,0),(68,64),(64+4*h[3],h[10]-1)):
   bad=bytearray(data);struct.pack_into('<I',bad,where,value);assert not lib.parse(bytes(bad),len(bad))
  bad=bytearray(data);first=struct.unpack_from('<I',data,64)[0];bad[first]=2;assert not lib.parse(bytes(bad),len(bad))
  assert not lib.frame(data,len(data),h[3],dest.ctypes.data)
  result={'frames_verified':h[3],'expanded_sha256':digest.hexdigest(),'c_python_bit_exact':True,'crc32_verified':True,'malformed_index_rejected':True}
  media.with_suffix('.c-tests.json').write_text(json.dumps(result,indent=2))
  print('PASS C/Python full media:',h[3],'frames; expanded digest',digest.hexdigest())
 import _ctypes
 _ctypes.FreeLibrary(lib._handle)
