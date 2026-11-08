"""Local FCPV3 trial: raw full-resolution bitplanes, native attributes, ADPCM."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import sys,json,struct,zlib,argparse,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scene_palette import encode_fixed
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('converted',type=Path,help='Existing prepare_long_video.py output folder')
ap.add_argument('output',type=Path)
ap.add_argument('--compress',action='store_true',help='FCPV4 indexed LZ4 blocks with optional row XOR')
a=ap.parse_args();root=a.converted;out=a.output
out.mkdir(parents=True,exist_ok=True)
old=(root/'full-8fps-adpcm.fcpv').read_bytes()
h=list(struct.unpack('<4s15I',old[:64]));count=h[3]
assert h[:3]==[b'FCPV',2,64] and h[4:7]==[8,1,32000] and h[8]==5152
assert h[11]==len(old) and h[12]==zlib.crc32(old[64:])
if not a.compress:
 assert 64+count*15456+len(old)-h[10]<=15*1024*1024, 'Full-frame clip exceeds the 15 MiB media slot'
else:
 import lz4.block
assert (root/'source-8fps.rgb').stat().st_size==count*240*256*3
raw=np.memmap(root/'source-8fps.rgb',mode='r',dtype=np.uint8,shape=(count,240,256,3))
video=bytearray();offsets=[];expanded_hash=hashlib.sha256();xor_frames=0
shots=json.loads((root/'palettes.json').read_text())
for shot in shots:
 previous=None
 for k in range(shot['begin'],shot['end']):
  frame,previous=encode_fixed(raw[k],shot['pal'],np.asarray(shot['pals']),previous,dither=0)
  record=frame.fb+bytes(frame.pal)+bytes(frame.attr)
  expanded_hash.update(record)
  if a.compress:
   delta=np.frombuffer(frame.fb,np.uint8).reshape(240,64).copy()
   delta[1:]^=delta[:-1].copy()
   candidates=[record,delta.tobytes()+bytes(frame.pal)+bytes(frame.attr)]
   packed=[lz4.block.compress(x,store_size=False,mode='high_compression',compression=12) for x in candidates]
   method=int(len(packed[1])<len(packed[0]));block=packed[method]
   check=bytearray(lz4.block.decompress(block,uncompressed_size=15456))
   if method:
    for row in range(1,240):
     start=row*64
     check[start:start+64]=bytes(x^y for x,y in zip(check[start:start+64],check[start-64:start]))
   assert check==record,'LZ4 roundtrip mismatch'
   offsets.append(64+(count+1)*4+len(video))
   video+=bytes([method])+block;xor_frames+=method
  else:video+=record
  if k in (0,80,160,240,360,480):frame.preview.save(out/f'frame-{k:04d}-model.png')
 print('FULL_FRAMES',shot['end'],'/',count,flush=True)
if a.compress:
 offsets.append(64+(count+1)*4+len(video))
 video=bytearray(struct.pack('<'+'I'*len(offsets),*offsets))+video
else:assert len(video)==count*15456
audio=old[h[10]:h[11]]
body=video+audio
h[1]=4 if a.compress else 3;h[8]=15456;h[10]=64+len(video);h[11]=64+len(body);h[12]=zlib.crc32(body)
blob=struct.pack('<4s15I',*h)+body
assert len(blob)<15*1024*1024
(out/('full-8fps-full-tiles-lz4.fcpv' if a.compress else 'full-8fps-full-tiles.fcpv')).write_bytes(blob)
(out/'manifest.json').write_text(json.dumps(dict(frames=count,fps=8,record=15456,total=len(blob),version=h[1],row_xor_frames=xor_frames,expanded_sha256=expanded_hash.hexdigest(),crc32=f'{h[12]:08x}',audio_unchanged=True,hardware_tested=False),indent=2))
print('DONE',len(blob),flush=True)
