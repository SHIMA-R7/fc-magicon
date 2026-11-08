"""Offline source-aware palette optimisation; unchanged FCPV v1 and playback FW.

Scores shot-stable candidates against original source pixels, retaining the old
shot when the evaluated candidates do not improve it. Audio bytes are preserved.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pathlib import Path
import argparse,json,struct,zlib,time
from functools import lru_cache
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import nesframe as nf
from tile_fit_native import fit_tiles_native

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'sim/standalone-video-20261014/full-8fps-stretch-4x3'
MEDIA=ROOT/'sim/standalone-video-20261014/pv-full-99s-8fps-stretch-4x3.fcpv'
OUT=ROOT/'sim/quality-enhanced-20261017'
SOURCE=Path('C:/Users/Yugo/pico/work-standalone-video-20261014/source-full-8fps-stretch-4x3.rgb')
COLORS=np.asarray(nf.USABLE)
v=np.arange(16)*2+1
qcentres=((v[:,None,None]<<10)|(v[None,:,None]<<5)|v[None,None,:]).ravel()
DIST=nf.COLOR_DISTANCE_LUT[qcentres].astype(np.float32)
BLOCK=(np.arange(240)[:,None]//16)*16+np.arange(256)[None,:]//16

def quant(a):
    a=np.asarray(a,np.int32)
    return ((a[...,0]>>3)<<10)|((a[...,1]>>3)<<5)|(a[...,2]>>3)

@lru_cache(maxsize=8)
def mix_lut(pal):
    options=np.asarray(pal[:16]).reshape(4,4)
    first=np.empty((4,32768),np.uint8);second=first.copy();fraction=np.zeros((4,32768),np.float32)
    for p in range(4):
        points=nf.NES_LAB[options[p]]
        point=nf.COLOR_DISTANCE_LUT[:,options[p]]
        nearest=point.argmin(-1);best=point.min(-1).copy()
        first[p]=nearest;second[p]=nearest
        for i in range(4):
            for j in range(i+1,4):
                delta=points[j]-points[i];length=float(delta@delta)
                if length<1e-6:continue
                t=np.clip(((nf.LAB_LUT-points[i])*delta).sum(-1)/length,0,1)
                residual=((nf.LAB_LUT-(points[i]+t[:,None]*delta))**2).sum(-1)
                cost=residual+30+length*.012
                mask=cost<best
                best[mask]=cost[mask];first[p,mask]=i;second[p,mask]=j;fraction[p,mask]=t[mask]
    return first,second,fraction

def edge_weights(image):
    a=np.asarray(image,np.float32)
    gx=np.abs(a-np.roll(a,1,1)).mean(-1);gy=np.abs(a-np.roll(a,1,0)).mean(-1)
    gx[:,0]=0;gy[0]=0
    return 1+np.minimum((gx+gy)/48,1.5)

def optimise_palette(images,old_pal):
    hist=np.zeros((240,4096),np.float32)
    for image in images:
        a=np.asarray(image,np.int32);q4=((a[...,0]>>4)<<8)|((a[...,1]>>4)<<4)|(a[...,2]>>4)
        hist+=np.bincount((BLOCK*4096+q4).ravel(),weights=edge_weights(a).ravel(),minlength=240*4096).reshape(240,4096)
    bg=int(old_pal[0]);pals=np.asarray(old_pal[:16]).reshape(4,4)[:,1:].copy()
    for iteration in range(8):
        options=np.column_stack((np.full(4,bg),pals))
        error=hist@DIST[:,options].min(-1)
        choice=error.argmin(-1)
        weights=[]
        for k in range(4):
            w=hist[choice==k].sum(0)
            if not w.any():
                w=hist[np.take_along_axis(error,choice[:,None],axis=1).ravel().argmax()]
            weights.append(w)
            for _ in range(2):
                for s in range(3):
                    others=[bg]+[int(pals[k,t]) for t in range(3) if t!=s]
                    residual=DIST[:,others].min(-1)
                    score=w@np.minimum(residual[:,None],DIST[:,COLORS])
                    old=float(w@np.minimum(residual,DIST[:,pals[k,s]]))
                    i=int(score.argmin())
                    if score[i]<old-0.01:pals[k,s]=COLORS[i]
        # Optimise the shared background without changing the four assignments.
        score=np.zeros(len(COLORS),np.float64)
        oldscore=0.
        for k,w in enumerate(weights):
            residual=DIST[:,pals[k]].min(-1)
            score+=w@np.minimum(residual[:,None],DIST[:,COLORS])
            oldscore+=float(w@np.minimum(residual,DIST[:,bg]))
        i=int(score.argmin())
        if score[i]<oldscore-0.01:bg=int(COLORS[i])
    pal=sum(([bg]+list(map(int,p)) for p in pals),[])+list(old_pal[16:32])
    for i in (16,20,24,28):pal[i]=bg
    return pal

def encode(image,pal,previous=None,dither=0):
    a=np.asarray(image,np.int32);q=quant(a);options=np.asarray(pal[:16]).reshape(4,4)
    costs=nf.COLOR_DISTANCE_LUT[q][:,:,options].min(-1).reshape(15,16,16,16,4).sum((1,3))
    if previous is not None:costs-=np.eye(4)[previous]*256*4
    choice=nf._smooth_choice(costs,256*2)
    pix=np.repeat(np.repeat(choice,16,0),16,1)
    if dither==-1:
        first,second,fraction=mix_lut(tuple(pal))
        threshold=nf.BAYER+.5
        idx=np.where(threshold<fraction[pix,q],second[pix,q],first[pix,q])
        # Preserve hard source contours instead of stippling across them.
        edge=edge_weights(image)>2.0
        nearest=nf._palette_pixel_lut(tuple(pal[:16]))[pix,q]
        idx[edge]=nearest[edge]
    else:
        if dither:q=quant(np.clip(a+(nf.BAYER*dither)[...,None],0,255).astype(np.int32))
        idx=nf._palette_pixel_lut(tuple(pal[:16]))[pix,q]
    frame=nf.Frame(idx,list(pal),nf.attr_of(choice));frame.pals=options[:,1:]
    fitted,counts=fit_tiles_native(frame)
    return fitted,choice,counts

def score(image,pic):
    a=nf.lab(image);b=nf.lab(pic);w=edge_weights(image)
    direct=np.mean(((a-b)**2).sum(-1)*w)
    a=a.reshape(120,2,128,2,3).mean((1,3));b=b.reshape(120,2,128,2,3).mean((1,3))
    return float(.4*direct+.6*np.mean(((a-b)**2).sum(-1)))

def old_frame(k):
    with np.load(OLD/'frames'/f'{k:04d}.npz') as z:return {key:z[key].copy() for key in z.files}

def record(frame):
    tiles=frame.idx.reshape(30,8,32,8).transpose(0,2,1,3).reshape(960,8,8).astype(np.uint8)
    unique,inverse=np.unique(tiles.reshape(960,64),axis=0,return_inverse=True)
    assert len(unique)<=256
    unique=unique.reshape(-1,8,8)
    patterns=np.concatenate((np.packbits(unique&1,axis=2).reshape(-1,8),np.packbits(unique>>1,axis=2).reshape(-1,8)),axis=1)
    chr=bytearray(4096);chr[:patterns.size]=patterns.tobytes()
    nt=inverse.astype(np.uint8).tobytes()+frame.attr
    assert len(nt)==1024
    # Reconstruct from packed data, not just the encoder's framebuffer.
    packed=np.frombuffer(chr,np.uint8).reshape(256,16)[inverse].reshape(30,32,16)
    idx=(np.unpackbits(packed[:,:,:8],axis=2).reshape(30,32,8,8)+2*np.unpackbits(packed[:,:,8:],axis=2).reshape(30,32,8,8)).transpose(0,2,1,3).reshape(240,256)
    assert np.array_equal(idx,frame.idx)
    pal=list(frame.pal)
    for i in (4,8,12,16,20,24,28):pal[i]=pal[0]
    return bytes(chr)+nt+bytes(pal)

def preview(images,shots,palettes):
    seconds=[7,20,25,45];modes=[('Current',None),('Optimised / no dither',0),('Optimised / tonal dither',-1)]
    canvas=Image.new('RGB',(1280,80+320*len(seconds)),(20,20,20));draw=ImageDraw.Draw(canvas);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
    draw.text((8,8),'PC conversion comparison - same 256-pattern playback format; not a new hardware capture',fill='white',font=font)
    for col,label in enumerate(['Original']+[x[0] for x in modes]):draw.text((col*320+8,40),label,fill='white',font=font)
    result=[]
    for row,sec in enumerate(seconds):
        k=sec*8;shot=next(s for s in shots if s['begin']<=k<s['end']);key=str(shot['begin'])
        old=old_frame(k);pics=[images[k],old['expected']];scores=[score(images[k],pics[1])]
        for dither in (0,-1):
            f,_,counts=encode(images[k],palettes[key],dither=dither);pics.append(np.asarray(f.preview));scores.append(score(images[k],pics[-1]))
        y=80+row*320;draw.text((8,y),f'{sec}s: score current / optimised / dither = '+ ' / '.join(f'{x:.1f}' for x in scores),fill='white',font=font)
        for col,pic in enumerate(pics):canvas.paste(Image.fromarray(pic).resize((320,300),Image.Resampling.NEAREST),(col*320,y+20))
        result.append(dict(seconds=sec,scores=scores))
    canvas.save(OUT/'candidate-comparison.png');(OUT/'preview-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--preview',action='store_true');ap.add_argument('--full',action='store_true');a=ap.parse_args()
    assert a.preview or a.full
    OUT.mkdir(exist_ok=True);cache=OUT/'frames';cache.mkdir(exist_ok=True)
    images=np.memmap(SOURCE,mode='r',dtype=np.uint8,shape=(792,240,256,3));shots=json.loads((OLD/'shot-palettes.json').read_text())
    palfile=OUT/'palettes.json';palettes=json.loads(palfile.read_text()) if palfile.exists() else {}
    for pal in palettes.values():
        for j in (4,8,12,16,20,24,28):pal[j]=pal[0]
    palfile.write_text(json.dumps(palettes,indent=2))
    needed=shots if a.full else [s for s in shots if any(s['begin']<=sec*8<s['end'] for sec in [7,20,25,45])]
    for i,s in enumerate(needed):
        key=str(s['begin'])
        if key not in palettes:
            indices=np.unique(np.linspace(s['begin'],s['end']-1,min(3,s['end']-s['begin']),dtype=int))
            palettes[key]=optimise_palette(images[indices],s['pal']);palfile.write_text(json.dumps(palettes,indent=2))
        if i%10==0:print(f'PALETTES {i+1}/{len(needed)}',flush=True)
    if a.preview:preview(images,shots,palettes)
    if not a.full:return
    oldmedia=MEDIA.read_bytes();h=struct.unpack('<4s15I',oldmedia[:64]);choicesfile=OUT/'shot-choices.json'
    choices=json.loads(choicesfile.read_text()) if choicesfile.exists() else {}
    for i,s in enumerate(shots):
        key=str(s['begin']);indices=np.unique(np.linspace(s['begin'],s['end']-1,min(3,s['end']-s['begin']),dtype=int))
        if key not in choices:
            scores=[0.,0.,0.]
            for k in indices:
                old=old_frame(k);scores[0]+=score(images[k],old['expected'])
                for n,d in enumerate((0,-1),1):
                    f,_,_=encode(images[k],palettes[key],dither=d);scores[n]+=score(images[k],np.asarray(f.preview))
            best=int(np.argmin(scores));best=best if scores[best]<scores[0]*.99 else 0
            choices[key]=dict(mode=best,scores=scores,samples=list(map(int,indices)))
            choicesfile.write_text(json.dumps(choices,indent=2))
        mode=choices[key]['mode'];previous=None
        for k in range(s['begin'],s['end']):
            target=cache/f'{k:04d}.npz'
            if target.exists():
                with np.load(target) as z:previous=z['choice'].copy()
                continue
            if mode==0:
                old=old_frame(k);blob=oldmedia[64+k*5152:64+(k+1)*5152];pic=old['expected'];previous=old['choice'];counts={}
            else:
                f,previous,counts=encode(images[k],palettes[key],previous,dither=0 if mode==1 else -1)
                blob=record(f);pic=np.asarray(f.preview)
            assert len(blob)==5152
            np.savez_compressed(target,record=np.frombuffer(blob,np.uint8),expected=pic,choice=previous,score=np.asarray(score(images[k],pic)))
        print(f'FRAMES {s["end"]}/792 shot={i+1}/115 mode={mode} sample_scores='+','.join(f'{x:.0f}' for x in choices[key]['scores']),flush=True)
    records=[];metrics=[]
    for k in range(792):
        target=cache/f'{k:04d}.npz'
        with np.load(target) as z:data={key:z[key].copy() for key in z.files}
        rec=data['record'];before=rec.copy()
        for j in (4,8,12,16,20,24,28):rec[5120+j]=rec[5120]
        assert len(set(int(rec[5120+j]) for j in (0,4,8,12,16,20,24,28)))==1
        if not np.array_equal(rec,before):np.savez_compressed(target,**data)
        records.append(rec.tobytes());metrics.append(float(data['score']))
    audio=oldmedia[h[10]:];body=b''.join(records)+audio;newh=list(h);newh[12]=zlib.crc32(body)
    blob=struct.pack('<4s15I',*newh)+body
    assert len(blob)==len(oldmedia) and blob[h[10]:]==audio and zlib.crc32(blob[64:])==newh[12]
    output=OUT/'pv-full-99s-8fps-quality.fcpv';output.write_bytes(blob)
    result=dict(frames=792,fps=8,bytes=len(blob),audio_bit_identical=True,firmware_change=False,mode_counts={str(m):sum(s['end']-s['begin'] for s in shots if choices[str(s['begin'])]['mode']==m) for m in (0,1,2)},mean_detail_score=float(np.mean(metrics)),hardware_tested=False)
    output.with_suffix('.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

if __name__=='__main__':main()
