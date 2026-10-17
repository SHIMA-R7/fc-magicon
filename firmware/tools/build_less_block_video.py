"""No-dither, old-palette conversion with explicit tile seam penalties."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import ctypes as C
import json,struct,zlib,argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import nesframe as nf
from build_quality_video import OLD,MEDIA,SOURCE,ROOT,old_frame,record,quant
from tile_fit_native import load_native

OUT=ROOT/'sim/less-block-20261017'
LIB=None

def tiles(a):
    return a.reshape(30,8,32,8,*a.shape[2:]).transpose(0,2,1,3,*range(4,a.ndim+2)).reshape(960,64,*a.shape[2:])

def raster(a):return a.reshape(30,32,8,8,*a.shape[2:]).transpose(0,2,1,3,*range(4,a.ndim+2)).reshape(240,256,*a.shape[2:])

def seam_error(pic,source):
    a=nf.lab(pic);b=nf.lab(source);r=a-b
    return float(np.mean((r[:,8::8]-r[:,7:-1:8])**2)+np.mean((r[8::8]-r[7:-1:8])**2))

def fit(image,old):
    global LIB
    pal=old['pal'];choice=old['choice'];attr=nf.attr_of(choice)
    bp=np.repeat(np.repeat(choice,2,0),2,1).ravel()
    pix=np.repeat(np.repeat(choice,16,0),16,1)
    idx=nf._palette_pixel_lut(tuple(map(int,pal[:16])))[pix,quant(image)]
    raw=tiles(idx).astype(np.uint8)
    patterns=np.unique(raw,axis=0);n=len(patterns)
    colors=nf.NES_LAB[pal[:16].reshape(4,4)].astype(np.float32)
    # Target is the original solid-color quantisation, before tile approximation.
    target=colors[bp[:,None],raw]
    candidates=colors[:,patterns]
    # Pixel fidelity plus tile-average and shape fidelity; no dot synthesis.
    cost=np.empty((960,n),np.float32)
    weights=np.ones((8,8),np.float32);weights[[0,-1],:]+=1;weights[:,[0,-1]]+=1
    for p in range(4):
        rows=np.flatnonzero(bp==p);a=target[rows];b=candidates[p]
        if not len(rows):continue
        ac=a*weights.reshape(1,64,1)
        c=(ac*a).sum((1,2))[:,None]+(b*b*weights.reshape(1,64,1)).sum((1,2))[None,:]-2*ac.reshape(-1,192)@b.reshape(n,192).T
        am=a.mean(1);bm=b.mean(1)
        c+=64*((am*am).sum(1)[:,None]+(bm*bm).sum(1)[None,:]-2*am@bm.T)
        ag=a.reshape(-1,8,8,3);bg=b.reshape(-1,8,8,3)
        for axis in (1,2):
            ad=np.diff(ag,axis=axis).reshape(len(rows),-1);bd=np.diff(bg,axis=axis).reshape(n,-1)
            c+=.3*((ad*ad).sum(1)[:,None]+(bd*bd).sum(1)[None,:]-2*ad@bd.T)
        cost[rows]=np.maximum(c,0)
    if LIB is None:
        LIB=load_native();LIB.tile_select_costs.argtypes=[C.c_int]*3+[C.c_void_p]*3
        LIB.tile_join.argtypes=[C.c_int]+[C.c_void_p]*5
    if n<=256:selected=np.arange(n,dtype=np.int32);assign=np.argmin(cost,axis=1).astype(np.int32)
    else:
        selected=np.zeros(256,np.int32);assign=np.zeros(960,np.int32)
        assert LIB.tile_select_costs(960,n,256,cost.ctypes.data,selected.ctypes.data,assign.ctypes.data)==0
    chosen=candidates[:,selected]
    base=np.ascontiguousarray(cost[:,selected]);chosen=np.ascontiguousarray(chosen)
    # Minimise spurious boundary jumps relative to the uncompressed image.
    # Checkerboard updates guarantee that simultaneously changed tiles do not touch.
    bp=np.ascontiguousarray(bp,dtype=np.int64)
    LIB.tile_join(len(selected),base.ctypes.data,chosen.ctypes.data,target.ctypes.data,bp.ctypes.data,assign.ctypes.data)
    fitted=patterns[selected[assign]]
    frame=nf.Frame(raster(fitted),list(map(int,pal)),attr);frame.pals=pal[:16].reshape(4,4)[:,1:]
    return frame,n

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--full',action='store_true');args=ap.parse_args()
    OUT.mkdir(exist_ok=True);cache=OUT/'frames';cache.mkdir(exist_ok=True)
    images=np.memmap(SOURCE,mode='r',dtype=np.uint8,shape=(792,240,256,3))
    before=MEDIA.read_bytes();h=struct.unpack('<4s15I',before[:64])
    sample=[32,56,160,200,360,560]
    contact=Image.new('RGB',(768,40+260*len(sample)),'black');draw=ImageDraw.Draw(contact)
    for x,label in [(0,'Original'),(256,'Old successful'),(512,'Less-block candidate')]:draw.text((x+5,10),label,fill='white')
    metrics=[]
    for k in range(792) if args.full else sample:
        old=old_frame(k);target=cache/f'{k:04d}.npz'
        if target.exists():
            with np.load(target) as z:pic=z['expected'];blob=z['record'].tobytes();m=json.loads(str(z['metrics']))
        else:
            frame,n=fit(images[k],old);pic=np.asarray(frame.preview)
            olderr=float(np.mean((nf.lab(images[k])-nf.lab(old['expected']))**2));newerr=float(np.mean((nf.lab(images[k])-nf.lab(pic))**2))
            olds=seam_error(old['expected'],images[k]);news=seam_error(pic,images[k])
            # Keep old frame if seam reduction costs too much source fidelity.
            use=news<olds*.97 and newerr<=olderr*1.03
            blob=record(frame) if use else before[64+k*5152:64+(k+1)*5152]
            if not use:pic=old['expected']
            m=dict(k=k,patterns=n,used=bool(use),old_seam=olds,new_seam=news,old_error=olderr,new_error=newerr)
            np.savez_compressed(target,record=np.frombuffer(blob,np.uint8),expected=pic,choice=old['choice'],metrics=json.dumps(m))
        metrics.append(m)
        if k in sample:
            y=40+sample.index(k)*260;draw.text((5,y),f'{k/8:g}s: candidate used={m["used"]}; seam {m["old_seam"]:.1f} -> {m["new_seam"]:.1f}',fill='white')
            for c,p in enumerate([images[k],old['expected'],pic]):contact.paste(Image.fromarray(p),(c*256,y+20))
        if not args.full or k%16==0:print(json.dumps(m),flush=True)
    contact.save(OUT/'comparison.png')
    (OUT/('metrics.json' if args.full else 'sample-metrics.json')).write_text(json.dumps(metrics,indent=2))
    if args.full:
        body=b''.join(np.load(cache/f'{k:04d}.npz')['record'].tobytes() for k in range(792))+before[h[10]:]
        newh=list(h);newh[12]=zlib.crc32(body);output=struct.pack('<4s15I',*newh)+body
        assert len(output)==len(before) and output[h[10]:]==before[h[10]:]
        (OUT/'pv-full-99s-8fps-less-block.fcpv').write_bytes(output)
        print(json.dumps(dict(frames=792,changed=sum(m['used'] for m in metrics),audio_identical=True)),flush=True)

if __name__=='__main__':main()
