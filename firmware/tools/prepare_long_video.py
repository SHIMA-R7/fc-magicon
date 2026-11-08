"""Build a full-length 8fps FCPV2, using the accepted solid-colour seam fitter.
Offline only. Each frame is cached; source media is never published.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import argparse,json,math,struct,subprocess,sys,time,wave,zlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
from imageio_ffmpeg import get_ffmpeg_exe
import nesframe as nf
from scene_palette import segments,choose_palette,encode_fixed
from tile_fit_native import fit_tiles_native
from build_less_block_video import fit,seam_error
from build_quality_video import record
from ima_audio import encode,decode
from concurrent.futures import ProcessPoolExecutor

def convert_shot(task):
    raw,frames,cache,shot=task
    images=np.memmap(raw,mode='r',dtype=np.uint8,shape=(frames,240,256,3));previous=None
    for k in range(shot['begin'],shot['end']):
        target=cache/f'{k:05d}.npz'
        if target.exists():
            with np.load(target) as z:previous=z['choice'].copy()
            continue
        base,previous=encode_fixed(images[k],shot['pal'],np.asarray(shot['pals']),previous,dither=0)
        baseline,_=fit_tiles_native(base);oldpic=np.asarray(baseline.preview)
        candidate,n=fit(images[k],dict(pal=np.asarray(shot['pal'],np.uint8),choice=previous))
        pic=np.asarray(candidate.preview)
        olderr=float(np.mean((nf.lab(images[k])-nf.lab(oldpic))**2));newerr=float(np.mean((nf.lab(images[k])-nf.lab(pic))**2))
        oldseam=seam_error(oldpic,images[k]);newseam=seam_error(pic,images[k])
        use=newseam<oldseam*.97 and newerr<=olderr*1.03
        blob=record(candidate if use else baseline)
        np.savez_compressed(target,record=np.frombuffer(blob,np.uint8),choice=previous,less_block=np.asarray(use))
    return shot['end']-shot['begin']

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--duration',type=float,required=True)
    ap.add_argument('--source-url',default='')
    ap.add_argument('--jobs',type=int,default=3)
    a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    frames=math.ceil(a.duration*8);duration=frames/8
    raw=a.output/'source-8fps.rgb';wav=a.output/'audio-32k.wav';ff=get_ffmpeg_exe()
    if not raw.exists():
        subprocess.run([ff,'-y','-v','error','-i',str(a.source),'-an','-vf',f'tpad=stop_mode=clone:stop_duration=1,trim=duration={duration},fps=8,scale=256:240:flags=lanczos','-frames:v',str(frames),'-pix_fmt','rgb24','-f','rawvideo',str(raw)],check=True)
    assert raw.stat().st_size==frames*240*256*3
    if not wav.exists():
        subprocess.run([ff,'-y','-v','error','-i',str(a.source),'-vn','-ac','1','-ar','32000','-af',f'apad,atrim=duration={duration}','-c:a','pcm_s16le',str(wav)],check=True)
    images=np.memmap(raw,mode='r',dtype=np.uint8,shape=(frames,240,256,3))
    palfile=a.output/'palettes.json'
    if palfile.exists():shots=json.loads(palfile.read_text())
    else:
        shots=[]
        for begin,end in segments(images):
            indices=np.unique(np.linspace(begin,end-1,min(5,end-begin),dtype=int))
            pal,pals=choose_palette(images[indices])
            shots.append(dict(begin=begin,end=end,pal=list(map(int,pal)),pals=np.asarray(pals).astype(int).tolist()))
            print(f'PALETTE {len(shots)} end={end}/{frames}',flush=True)
        palfile.write_text(json.dumps(shots,indent=2))
    cache=a.output/'frames';cache.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=max(1,a.jobs)) as pool:
        done=0
        for n in pool.map(convert_shot,[(raw,frames,cache,shot) for shot in shots]):
            done+=n;print(f'FRAMES {done}/{frames}',flush=True)
    video=b''.join(np.load(cache/f'{k:05d}.npz')['record'].tobytes() for k in range(frames))
    with wave.open(str(wav),'rb') as w:
        assert w.getframerate()==32000 and w.getnchannels()==1 and w.getsampwidth()==2
        original=np.frombuffer(w.readframes(w.getnframes()),'<i2').astype(np.float64)
    peak=float(np.max(np.abs(original)));gain=min(4.,30000/max(peak,1))
    samples=np.rint(np.clip(original*gain,-32768,32767)).astype(np.int16)
    audio=encode(samples);decoded=decode(audio,len(samples));error=samples.astype(float)-decoded.astype(float)
    snr=float(10*np.log10(max(np.mean(samples.astype(float)**2),1)/max(np.mean(error**2),1e-12)))
    body=video+audio
    header=struct.pack('<4s15I',b'FCPV',2,64,frames,8,1,32000,len(samples),5152,64,64+len(video),64+len(body),zlib.crc32(body),2,256,0)
    output=a.output/'full-8fps-adpcm.fcpv';output.write_bytes(header+body)
    pcm8=((decoded.astype(np.int32)+32768)>>8).astype(np.uint8);(a.output/'decoded-audio.pcm').write_bytes(pcm8.tobytes())
    result=dict(source_url=a.source_url,source_seconds=a.duration,duration_s=duration,frames=frames,fps=8,format='FCPV2 IMA ADPCM 256-sample blocks',rate=32000,audio_gain=gain,audio_snr_db=snr,video_bytes=len(video),audio_bytes=len(audio),media_bytes=64+len(body),media_offset=0x100000,slot_bytes=15*1024*1024,geometry='full-frame stretch to 4:3',hardware_tested=False)
    assert len(header+body)<=result['slot_bytes']
    output.with_suffix('.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

if __name__=='__main__':main()
