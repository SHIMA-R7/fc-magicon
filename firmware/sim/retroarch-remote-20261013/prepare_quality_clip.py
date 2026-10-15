"""Offline 8fps quality trial; verify every frame against actual tile converter."""
from pathlib import Path
import sys,os,time,json,ctypes as C,shutil,subprocess,argparse
import numpy as np
from PIL import Image
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
import nesframe as nf
from tile_quality import fit_tiles
from imageio_ffmpeg import get_ffmpeg_exe
ap=argparse.ArgumentParser();ap.add_argument('--fps',type=int,default=8);ap.add_argument('--independent-palettes',action='store_true')
args=ap.parse_args()
if not 1<=args.fps<=30:ap.error('fps must be 1..30')
source=here/'youtube-U6Wlb18KLrI';out=source/f'quality-{args.fps}fps';out.mkdir(exist_ok=True)
z=np.load(source/'sequence.npz');original=z['original']
lib=C.CDLL(str(here/'converter-stream.dll'));lib.convert.argtypes=[C.c_void_p]*3
chr=np.zeros(4096,np.uint8);nt=np.zeros(1024,np.uint8)
fb=[];pal=[];attr=[];images=[];records=[];prev=None
count=30*args.fps
for k in range(count):
    i=int(k*30/args.fps);start=time.perf_counter()
    seed=None if args.independent_palettes else prev
    fr=nf.encode(Image.fromarray(original[i]),'color',iters=8 if args.independent_palettes else 4 if prev is None else 2,dither=False,smooth=0,prev=seed,_bg_mode='best4')
    prev=fr
    fitted,counts=fit_tiles(fr)
    b=np.frombuffer(fitted.fb,np.uint8).copy()
    lib.convert(b.ctypes.data,chr.ctypes.data,nt.ctypes.data)
    t=chr.reshape(256,16)[nt[:960].reshape(30,32)]
    idx=(np.unpackbits(t[:,:,:8],axis=2).reshape(30,32,8,8)+2*np.unpackbits(t[:,:,8:],axis=2).reshape(30,32,8,8)).transpose(0,2,1,3).reshape(240,256)
    got=np.asarray(nf.render(idx,fitted.pal,fitted.attr))
    assert np.array_equal(got,np.asarray(fitted.preview)),k
    fb.append(b);pal.append(fitted.pal);attr.append(np.frombuffer(fitted.attr,np.uint8));images.append(got)
    records.append(dict(frame=k,source_frame=i,seconds=time.perf_counter()-start,**counts))
    if k%20==0:print(f'Converted and verified {k+1}/{count}',flush=True)
np.savez_compressed(out/'sequence.npz',fb=np.array(fb),pal=np.array(pal,np.uint8),attr=np.array(attr),expected=np.array(images))
shutil.copyfile(source/'audio-32k.wav',out/'audio-32k.wav')
(out/'conversion-results.json').write_text(json.dumps({'fps':args.fps,'duration':30,'frames':count,'independent_palettes':args.independent_palettes,'extra_firmware_rgb_errors':0,'records':records},indent=2))
for second in (5,10,20):Image.fromarray(images[second*args.fps]).resize((768,720),Image.Resampling.NEAREST).save(out/f'frame-{second:02d}s.png')
proc=subprocess.Popen([get_ffmpeg_exe(),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','256x240','-r',str(args.fps),'-i','pipe:0','-i',str(out/'audio-32k.wav'),'-t','30','-vf','scale=768:720:flags=neighbor','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(out/'quality-preview-30s.mp4')],stdin=subprocess.PIPE)
for img in images:proc.stdin.write(img.tobytes())
proc.stdin.close();assert proc.wait()==0
print(f'DONE: {count} frames verified; ideal {args.fps}fps preview saved',flush=True)
