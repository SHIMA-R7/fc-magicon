"""Offline palette-boundary trial. Native 16x16 attributes, no dithering.

Not enabled in the video converter: temporal stability still needs checking.
"""
import numpy as np
import nesframe as nf


def reduce_palette_seams(image, palette, attributes, weight=4., skin_weight=3.):
    a=np.asarray(image,dtype=np.uint8)
    if a.shape!=(240,256,3):raise ValueError('Expected a 256x240 RGB image')
    pal=np.asarray(palette,dtype=np.uint8)
    attr=np.frombuffer(attributes,np.uint8) if isinstance(attributes,bytes) else np.asarray(attributes,np.uint8)
    if pal.shape!=(32,) or attr.shape!=(64,):raise ValueError('Expected 32 palette and 64 attribute bytes')
    q=((a[...,0].astype(int)>>3)<<10)|((a[...,1].astype(int)>>3)<<5)|(a[...,2].astype(int)>>3)
    lut=nf._palette_pixel_lut(tuple(map(int,pal[:16])))
    idx=np.array([lut[p,q] for p in range(4)])
    rgb=nf.NES[pal[:16].reshape(4,4)][np.arange(4)[:,None,None],idx]
    target=nf.lab(a).astype(np.float32);labs=nf.lab(rgb).astype(np.float32)
    # Conservative light warm-colour mask; prevents boundary smoothing from
    # sacrificing skin solely to make a grey region continuous.
    af=a.astype(np.int16)
    skin=(af[...,0]>af[...,1]+6)&(af[...,1]>175)&(af[...,2]>145)&(af[...,0]>af[...,2])
    pixel_weight=1+skin*(skin_weight-1)
    unary=(((labs-target[None])**2).sum(-1)*pixel_weight).reshape(4,15,16,16,16).sum((2,4)).transpose(1,2,0)
    choice=np.array([[(attr[(y//2)*8+x//2]>>(((y%2)*2+x%2)*2))&3 for x in range(16)] for y in range(15)])
    original=choice.copy()
    protected=skin.reshape(15,16,16,16).sum((1,3))>=4
    horizontal=np.empty((15,15,4,4),np.float32)
    vertical=np.empty((14,16,4,4),np.float32)
    for y in range(15):
        for x in range(15):
            l=labs[:,y*16:y*16+16,x*16+15];r=labs[:,y*16:y*16+16,x*16+16]
            delta=target[y*16:y*16+16,x*16+15]-target[y*16:y*16+16,x*16+16]
            horizontal[y,x]=((l[:,None]-r[None]-delta[None,None])**2).sum((2,3))
    for y in range(14):
        for x in range(16):
            t=labs[:,y*16+15,x*16:x*16+16];b=labs[:,y*16+16,x*16:x*16+16]
            delta=target[y*16+15,x*16:x*16+16]-target[y*16+16,x*16:x*16+16]
            vertical[y,x]=((t[:,None]-b[None]-delta[None,None])**2).sum((2,3))
    for _ in range(12):
        changes=0
        for parity in (0,1):
            for y in range(15):
                for x in range(16):
                    if (x+y)%2!=parity:continue
                    if protected[y,x]:continue
                    cost=unary[y,x].copy()
                    if x:cost+=weight*horizontal[y,x-1,choice[y,x-1],:]
                    if x<15:cost+=weight*horizontal[y,x,:,choice[y,x+1]]
                    if y:cost+=weight*vertical[y-1,x,choice[y-1,x],:]
                    if y<14:cost+=weight*vertical[y,x,:,choice[y+1,x]]
                    p=int(np.argmin(cost));changes+=p!=choice[y,x];choice[y,x]=p
        if not changes:break
    pixels=np.repeat(np.repeat(choice,16,axis=0),16,axis=1)
    newidx=idx[pixels,np.arange(240)[:,None],np.arange(256)[None,:]]
    frame=nf.Frame(newidx,list(map(int,pal)),nf.attr_of(choice))
    return frame,dict(changed_blocks=int(np.count_nonzero(choice!=original)),weight=weight,skin_weight=skin_weight)
