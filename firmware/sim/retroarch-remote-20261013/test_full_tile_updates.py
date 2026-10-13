"""Actual full-tile converter with the driver's eight-frame NT copy schedule."""
from pathlib import Path
import ctypes as C,subprocess,json
import numpy as np
here=Path(__file__).resolve().parent;out=here/'video-load'
code='''#include <stdint.h>
#include <stdbool.h>
typedef unsigned uint;
static uint32_t diag_chr_lookup[8192];
#include "../../magicon/remote_full.h"
__declspec(dllexport) void convert(const uint8_t *fb,uint8_t *chr,uint8_t *nt){
 remote_full_convert(fb);
 for(uint i=0;i<4096;i++)chr[i]=(uint8_t)diag_chr_lookup[i];
 memcpy(nt,rd_nt,1024);
}
'''
(here/'converter-stream.c').write_text(code)
subprocess.run(['C:/Users/Yugo/pico/zig/zig-x86_64-windows-0.16.0/zig.exe','cc','-O2','-shared',str(here/'converter-stream.c'),'-o',str(here/'converter-stream.dll')],check=True)
lib=C.CDLL(str(here/'converter-stream.dll'));lib.convert.argtypes=[C.c_void_p]*3
with np.load(out/'sequence.npz') as z:fb=z['fb'];attrs=z['attr']
chr=np.zeros(4096,dtype=np.uint8);desired=np.zeros(1024,dtype=np.uint8);ppu=np.zeros(1024,dtype=np.uint8)
def pixels(nt):
 ids=nt[:960].reshape(30,32)
 tiles=chr.reshape(256,16)[ids]
 lo=np.unpackbits(tiles[:,:,:8],axis=2).reshape(30,32,8,8)
 hi=np.unpackbits(tiles[:,:,8:],axis=2).reshape(30,32,8,8)
 return (lo+hi*2).transpose(0,2,1,3).reshape(240,256)
records=[]
for tick in range(360):
 i=tick//2
 if tick%2==0:
  lib.convert(fb[i].ctypes.data,chr.ctypes.data,desired.ctypes.data);desired[960:]=attrs[i]
  if tick==0:ppu[:]=desired # Start from a completed first frame, isolating later updates.
 chunk=tick%8;ppu[chunk*128:(chunk+1)*128]=desired[chunk*128:(chunk+1)*128]
 ideal=pixels(desired);got=pixels(ppu)
 raw=fb[i].reshape(240,32,2)
 original=np.unpackbits(raw[:,:,0],axis=1)+np.unpackbits(raw[:,:,1],axis=1)*2
 records.append({'emulator_frame':tick,'source_frame':i,'tile_approximation_index_errors':int((ideal!=original).sum()),'additional_nt_mix_index_errors':int((got!=ideal).sum()),'mixed_attribute_bytes':int((ppu[960:]!=desired[960:]).sum())})
result={'displayed_frames':360,'frames_with_additional_nt_mix':sum(r['additional_nt_mix_index_errors']>0 or r['mixed_attribute_bytes']>0 for r in records),'max_additional_index_errors':max(r['additional_nt_mix_index_errors'] for r in records),'mean_tile_approximation_index_errors':float(np.mean([r['tile_approximation_index_errors'] for r in records])),'records':records}
(out/'tile-update-results.json').write_text(json.dumps(result,indent=2))
print({k:v for k,v in result.items() if k!='records'})
