from pathlib import Path
import os,sys,time,json,ctypes as C,shutil,subprocess
import numpy as np
from PIL import Image
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
import nesframe as nf
from scene_palette import segments,choose_palette,encode_fixed
from tile_quality import fit_tiles
from imageio_ffmpeg import get_ffmpeg_exe
source=here/'youtube-U6Wlb18KLrI';out=source/'quality-4fps-stable';out.mkdir(exist_ok=True)
z=np.load(source/'sequence.npz');original=z['original'][np.arange(120)*30//4]
baseline=np.load(source/'quality-4fps/sequence.npz')['expected']
shots=segments(original);print('Shots:',shots,flush=True)
lib=C.CDLL(str(here/'converter-stream.dll'));lib.convert.argtypes=[C.c_void_p]*3
chr=np.zeros(4096,np.uint8);nt=np.zeros(1024,np.uint8)
fb=[];palettes=[];attrs=[];images=[];records=[]
for begin,end in shots:
    pal,pals=choose_palette(original[begin:end]);prev=None
    for k in range(begin,end):
        start=time.perf_counter();fr,prev=encode_fixed(original[k],pal,pals,prev,dither=0)
        fitted,counts=fit_tiles(fr);b=np.frombuffer(fitted.fb,np.uint8).copy()
        lib.convert(b.ctypes.data,chr.ctypes.data,nt.ctypes.data)
        t=chr.reshape(256,16)[nt[:960].reshape(30,32)]
        idx=(np.unpackbits(t[:,:,:8],axis=2).reshape(30,32,8,8)+2*np.unpackbits(t[:,:,8:],axis=2).reshape(30,32,8,8)).transpose(0,2,1,3).reshape(240,256)
        got=np.asarray(nf.render(idx,fitted.pal,fitted.attr));assert np.array_equal(got,np.asarray(fitted.preview)),k
        fb.append(b);palettes.append(fitted.pal);attrs.append(np.frombuffer(fitted.attr,np.uint8));images.append(got)
        lab=nf.lab(original[k]);old=float(np.mean(np.sum((nf.lab(baseline[k])-lab)**2,axis=-1)))
        new=float(np.mean(np.sum((nf.lab(got)-lab)**2,axis=-1)))
        records.append(dict(frame=k,shot_start=begin,lab_mse_old=old,lab_mse_new=new,seconds=time.perf_counter()-start,**counts))
        if k%20==0:print('Converted and verified',k+1,'/120',flush=True)
images=np.array(images)
np.savez_compressed(out/'sequence.npz',fb=np.array(fb),pal=np.array(palettes,np.uint8),attr=np.array(attrs),expected=images)
shutil.copyfile(source/'audio-32k.wav',out/'audio-32k.wav')
def motion_error(rendered):
    total=0.;pixels=0
    for i in range(1,len(original)):
        mask=np.mean(np.abs(original[i].astype(float)-original[i-1].astype(float)),axis=-1)<3
        change=np.linalg.norm((nf.lab(rendered[i])-nf.lab(rendered[i-1]))-(nf.lab(original[i])-nf.lab(original[i-1])),axis=-1)
        total+=change[mask].sum();pixels+=mask.sum()
    return float(total/max(pixels,1))
result={'fps':4,'frames':120,'shots':shots,'extra_firmware_rgb_errors':0,'mean_lab_mse_old':float(np.mean([r['lab_mse_old'] for r in records])),
        'mean_lab_mse_new':float(np.mean([r['lab_mse_new'] for r in records])),
        'low_motion_temporal_error_old':motion_error(baseline),'low_motion_temporal_error_new':motion_error(images),'records':records}
(out/'conversion-results.json').write_text(json.dumps(result,indent=2))
for second in (5,10,20):Image.fromarray(images[second*4]).resize((768,720),Image.Resampling.NEAREST).save(out/f'frame-{second:02d}s.png')
comparison=Image.new('RGB',(768,720))
for row,k in enumerate((20,40,80)):
    for col,pic in enumerate((original[k],baseline[k],images[k])):comparison.paste(Image.fromarray(pic),(col*256,row*240))
comparison.save(out/'comparison.png')
proc=subprocess.Popen([get_ffmpeg_exe(),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','256x240','-r','4','-i','pipe:0','-i',str(out/'audio-32k.wav'),'-t','30','-vf','scale=768:720:flags=neighbor','-af','volume=20','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(out/'quality-preview-30s.mp4')],stdin=subprocess.PIPE)
for img in images:proc.stdin.write(img.tobytes())
proc.stdin.close();assert proc.wait()==0
print({k:v for k,v in result.items() if k not in ('records','shots')},flush=True)
