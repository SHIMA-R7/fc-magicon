"""Convert the full 99s PV to shot-stable 8fps frames, with per-frame resume files."""
from pathlib import Path
import ctypes as C
import argparse,json,os,subprocess,sys,time,wave
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'tools'))
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
import nesframe as nf
from scene_palette import segments,choose_palette,encode_fixed
from tile_quality import fit_tiles
from imageio_ffmpeg import get_ffmpeg_exe

parser=argparse.ArgumentParser(description=__doc__)
geometry=parser.add_mutually_exclusive_group()
geometry.add_argument('--display-4x3',action='store_true',help='Precompensate non-square pixels for a 4:3 display')
geometry.add_argument('--stretch-4x3',action='store_true',help='Stretch the complete source to the full 4:3 display, without letterboxing or cropping')
args=parser.parse_args()
suffix='-stretch-4x3' if args.stretch_4x3 else '-4x3' if args.display_4x3 else ''
# A 256x240 raster displayed as 4:3 has pixel aspect 5:4.
# 256 * (5/4) / (16/9) = 180 stored rows for a 16:9 source.
content_height=240 if args.stretch_4x3 else 180 if args.display_4x3 else 144
top=(240-content_height)//2
source=Path(r'C:\Users\Yugo\pico\work-standalone-video-20261014\source-full.mp4')
work=source.parent
out=HERE/f'standalone-video-20261014/full-8fps{suffix}';out.mkdir(parents=True,exist_ok=True)
cache=out/'frames';cache.mkdir(exist_ok=True)
raw=work/f'source-full-8fps{suffix}.rgb';wav=work/'source-full-32k.wav'
ff=get_ffmpeg_exe()
if not raw.exists():
    subprocess.run([ff,'-y','-v','error','-i',str(source),'-an','-vf',
        f'tpad=stop_mode=clone:stop_duration=1,trim=duration=99,fps=8,scale=256:{content_height}:flags=lanczos,pad=256:240:0:{top}:black',
        '-pix_fmt','rgb24','-f','rawvideo',str(raw)],check=True)
assert raw.stat().st_size==792*240*256*3
if not wav.exists():
    subprocess.run([ff,'-y','-v','error','-i',str(source),'-vn','-ac','1','-ar','32000',
        '-af','apad,atrim=duration=99','-c:a','pcm_s16le',str(wav)],check=True)
images=np.memmap(raw,mode='r',dtype=np.uint8,shape=(792,240,256,3))
shots=segments(images)
palfile=out/'shot-palettes.json'
if palfile.exists():palettes=json.loads(palfile.read_text())
else:
    palettes=[]
    for i,(begin,end) in enumerate(shots):
        pal,pals=choose_palette(images[begin:end])
        palettes.append(dict(begin=begin,end=end,pal=list(map(int,pal)),pals=np.asarray(pals).astype(int).tolist()))
        print(f'Palette {i+1}/{len(shots)} ({begin}:{end})',flush=True)
    palfile.write_text(json.dumps(palettes,indent=2),encoding='utf-8')
lib=C.CDLL(str(HERE/'retroarch-remote-20261013/converter-stream.dll'))
lib.convert.argtypes=[C.c_void_p]*3
chr=np.zeros(4096,np.uint8);nt=np.zeros(1024,np.uint8)
for shot in palettes:
    previous=None
    for k in range(shot['begin'],shot['end']):
        target=cache/f'{k:04d}.npz'
        if target.exists():
            with np.load(target,allow_pickle=False) as z:previous=z['choice']
            continue
        started=time.monotonic()
        encoded,previous=encode_fixed(images[k],shot['pal'],np.asarray(shot['pals']),previous,dither=0)
        fitted,counts=fit_tiles(encoded)
        b=np.frombuffer(fitted.fb,np.uint8).copy()
        lib.convert(b.ctypes.data,chr.ctypes.data,nt.ctypes.data)
        tiles=chr.reshape(256,16)[nt[:960].reshape(30,32)]
        idx=(np.unpackbits(tiles[:,:,:8],axis=2).reshape(30,32,8,8)+
            2*np.unpackbits(tiles[:,:,8:],axis=2).reshape(30,32,8,8)).transpose(0,2,1,3).reshape(240,256)
        got=np.asarray(nf.render(idx,fitted.pal,fitted.attr))
        assert np.array_equal(got,np.asarray(fitted.preview)),k
        np.savez_compressed(target,fb=b,pal=np.asarray(fitted.pal,np.uint8),
            attr=np.frombuffer(fitted.attr,np.uint8),expected=got,choice=previous)
        if k%16==0:print(f'Frame {k+1}/792, {counts}, {time.monotonic()-started:.2f}s',flush=True)
combined={key:[] for key in ('fb','pal','attr','expected')}
for k in range(792):
    with np.load(cache/f'{k:04d}.npz',allow_pickle=False) as z:
        for key in combined:combined[key].append(z[key])
np.savez_compressed(out/'sequence.npz',**{key:np.asarray(value) for key,value in combined.items()})
(out/'audio-32k.wav').write_bytes(wav.read_bytes())
with wave.open(str(wav),'rb') as w:
    audio=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.int32)
peak=int(np.abs(audio).max());gain=min(20.,30000./max(peak,1))
result=dict(source_url='https://www.youtube.com/watch?v=U6Wlb18KLrI',fps=8,frames=792,
    duration_s=99,shots=len(shots),rgb_errors=0,audio_peak_before_gain=peak,
    display_aspect='4:3' if args.display_4x3 or args.stretch_4x3 else 'square pixels',
    geometry='stretch' if args.stretch_4x3 else 'letterbox',
    content_raster=[256,content_height],letterbox_rows=top,
    suggested_audio_gain=gain,note='Final video frame and audio padded only as needed to 99s')
(out/'conversion-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
