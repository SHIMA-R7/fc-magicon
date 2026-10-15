"""Offline shot palettes: look ahead within a shot, retain colors between frames."""
import numpy as np
import nesframe as nf

def quant(image):
    a=np.asarray(image,dtype=np.int32)
    return ((a[...,0]>>3)<<10)|((a[...,1]>>3)<<5)|(a[...,2]>>3)

def segments(images,threshold=.45):
    hist=[]
    for a in images:
        near=nf.NEAR_LUT[quant(a)]
        content=~(a==0).all(-1).all(-1)
        h=np.bincount(near[content].ravel(),minlength=64).astype(float)
        hist.append(h/max(h.sum(),1))
    starts=[0]
    for i in range(1,len(images)):
        delta=float(np.abs(hist[i]-hist[i-1]).sum())
        motion=float(np.mean(np.abs(images[i].astype(float)-images[i-1].astype(float))))
        if delta>threshold and motion>18:starts.append(i)
    return list(zip(starts,starts[1:]+[len(images)]))

def choose_palette(images):
    hist=np.zeros((15,16,64),np.int64);counts=np.zeros(64,np.int64)
    blocks=(np.arange(240)[:,None]//16)*16+np.arange(256)[None,:]//16
    for a in images:
        near=nf.NEAR_LUT[quant(a)]
        hist+=np.bincount((blocks*64+near).ravel(),minlength=240*64).reshape(15,16,64)
        content=~(a==0).all(-1).all(-1)
        counts+=np.bincount(near[content].ravel(),minlength=64)
    best=None
    for bg in np.argsort(-counts)[:4]:
        pals,choice,cost=nf._search_palettes(hist,int(bg),False,0,10,None,mix=False)
        if best is None or cost<best[0]:best=(cost,int(bg),pals)
    _,bg,pals=best
    pal=sum(([bg]+list(map(int,p)) for p in pals),[])+[bg,0x30,0x0F,0x0F]*4
    return pal,pals

def encode_fixed(image,pal,pals,previous=None,dither=0):
    a=np.asarray(image,dtype=np.int32);q=quant(a)
    options=np.array(pal[:16]).reshape(4,4)
    distance=nf._color_distance_lut()[q][:,:,options]
    errors=distance.min(-1).reshape(15,16,16,16,4).sum((1,3))
    # Hold the previous block choice only for a small, explicitly bounded cost.
    if previous is not None:
        errors-=np.eye(4,dtype=np.float32)[previous]*256*4
    choice=nf._smooth_choice(errors,256*4)
    pixels=np.repeat(np.repeat(choice,16,0),16,1)
    if dither:
        q=quant(np.clip(a+(nf.BAYER*dither)[...,None],0,255).astype(np.int32))
    idx=nf._palette_pixel_lut(tuple(pal[:16]))[pixels,q].astype(np.int32)
    frame=nf.Frame(idx,list(pal),nf.attr_of(choice));frame.pals=pals
    return frame,choice
