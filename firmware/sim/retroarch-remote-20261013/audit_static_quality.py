"""Compare transmitted pixels with the actual 256-tile converter, after settling."""
from pathlib import Path
import ctypes as C
import sys, json
import numpy as np
from PIL import Image
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tools'))
from nesframe import render
lib = C.CDLL(str(here / 'converter-stream.dll'))
lib.convert.argtypes = [C.c_void_p] * 3
folder = here / 'youtube-U6Wlb18KLrI'
z = np.load(folder / 'sequence.npz')
fb = z['fb'][150].copy()
chr = np.zeros(4096, np.uint8)
nt = np.zeros(1024, np.uint8)
for _ in range(40):
    lib.convert(fb.ctypes.data, chr.ctypes.data, nt.ctypes.data)
tiles = chr.reshape(256,16)[nt[:960].reshape(30,32)]
idx = (np.unpackbits(tiles[:,:,:8],axis=2).reshape(30,32,8,8)
       + 2*np.unpackbits(tiles[:,:,8:],axis=2).reshape(30,32,8,8))
idx = idx.transpose(0,2,1,3).reshape(240,256)
raw = fb.reshape(240,32,2)
ideal = np.unpackbits(raw[:,:,0],axis=1)+2*np.unpackbits(raw[:,:,1],axis=1)
before = render(ideal,z['pal'][150],z['attr'][150])
after = render(idx,z['pal'][150],z['attr'][150])
comparison = Image.new('RGB',(512,240))
comparison.paste(before,(0,0)); comparison.paste(after,(256,0))
comparison.resize((1536,720),Image.Resampling.NEAREST).save(folder/'static-tile-comparison.png')
tile_bytes = fb.reshape(240,32,2).reshape(30,8,32,2).transpose(0,2,1,3).reshape(960,16)
result = {'source_frame':150,'unique_tiles':len(np.unique(tile_bytes,axis=0)),
          'index_pixels_changed':int((idx!=ideal).sum()),
          'rgb_pixels_changed':int(np.any(np.asarray(before)!=np.asarray(after),axis=2).sum()),
          'total_pixels':61440,'physical_capture_comparison':False}
(folder/'static-tile-quality.json').write_text(json.dumps(result,indent=2))
print(result)
