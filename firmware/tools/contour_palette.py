"""Offline contour-priority trials, using ordinary native NES attributes.

Colour fidelity is deliberately traded for stronger tonal separation. Fit the
palette to the processed shot too; preprocessing with an unchanged palette can
otherwise discard all the additional detail during quantisation.
"""
import numpy as np
from PIL import Image, ImageFilter
import nesframe as nf
from scene_palette import quant


def prepare(image, saturation=1.35, gamma=1.45, detail=1.1):
    a = np.asarray(image, dtype=np.float32)
    if a.shape != (240,256,3):
        raise ValueError('Expected 256x240 RGB')
    y = a @ np.array([.2126,.7152,.0722],dtype=np.float32)
    blur = np.asarray(Image.fromarray(np.rint(y).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float32)
    # Bounded unsharp luminance; no artificial pixel grid or dither pattern.
    high = np.clip(y-blur,-14,14)
    tone = 255*np.power(np.clip(y/255,0,1),gamma) + detail*high
    result = tone[...,None] + saturation*(a-y[...,None])
    return np.rint(np.clip(result,0,255)).astype(np.uint8)


def choose_contour_palette(images, edge_weight=3.):
    hist = np.zeros((15,16,64),dtype=np.float64)
    block = np.arange(240)[:,None]//16*16 + np.arange(256)[None,:]//16
    for a in images:
        near = nf.NEAR_LUT[quant(a)]
        y = np.asarray(a,dtype=np.float32) @ np.array([.2126,.7152,.0722])
        dy,dx = np.gradient(y)
        # Make sparse line/shape colours count during palette fitting.
        weights = 1 + edge_weight*np.clip(np.hypot(dx,dy)/24,0,1)
        hist += np.bincount((block*64+near).ravel(),weights=weights.ravel(),minlength=240*64).reshape(15,16,64)
    counts = hist.sum((0,1));best = None
    for bg in np.argsort(-counts)[:4]:
        pals,_,cost = nf._search_palettes(hist,int(bg),False,0,10,None,mix=False)
        if best is None or cost < best[0]:best = cost,int(bg),pals
    _,bg,pals = best
    pal = sum(([bg]+list(map(int,p)) for p in pals),[]) + [bg,0x30,0x0f,0x0f]*4
    return pal,np.asarray(pals)


def prepare_ink(image, depth=52):
    """Illustrative contour overlay from source gradients, not generated detail.

    Flatten faint near-white areas, but translate their local line contrast into
    a darker stroke. Deliberately changes the artwork and can expose noise.
    """
    a=np.asarray(image,dtype=np.uint8)
    labs=nf.lab(a)
    blurred=nf.lab(np.asarray(Image.fromarray(a).filter(ImageFilter.GaussianBlur(1.1))))
    residual=labs-blurred
    strength=np.maximum(-residual[...,0],0)+.30*np.linalg.norm(residual[...,1:],axis=-1)
    pale=(labs[...,0]>90)&(np.linalg.norm(labs[...,1:],axis=-1)<25)
    threshold=np.where(pale,.65,1.5)
    ink=np.clip((strength-threshold)/3.5,0,1)**.7
    processed=prepare(a,saturation=1.4,gamma=1.35,detail=.4).astype(np.float32)
    # White highlights no longer become isolated cyan areas; contours remain.
    processed[pale]=np.maximum(processed[pale],248)
    processed-=depth*ink[...,None]
    return np.rint(np.clip(processed,0,255)).astype(np.uint8)


def hybrid_contours(image, baseline, strength=1.):
    """Conservative local contour edits, retaining baseline palette/attributes.

    Only dark-side source edges whose contrast is missing in the baseline can
    change. All other pixels retain the exact original two-bit index. This is
    a heuristic, not a guarantee of subjective improvement or temporal stability.
    """
    if not 0 <= strength <= 2:
        raise ValueError('strength must be between 0 and 2')
    a=np.asarray(image,dtype=np.uint8)
    if a.shape!=(240,256,3):raise ValueError('Expected 256x240 RGB')
    source=nf.lab(a)
    original=np.asarray(baseline.preview)
    base_lab=nf.lab(original)
    blur_source=nf.lab(np.asarray(Image.fromarray(a).filter(ImageFilter.GaussianBlur(1.1))))
    blur_base=nf.lab(np.asarray(Image.fromarray(original).filter(ImageFilter.GaussianBlur(1.1))))
    source_dark=np.maximum(blur_source[...,0]-source[...,0],0)
    base_dark=np.maximum(blur_base[...,0]-base_lab[...,0],0)
    deficit=np.maximum(source_dark*(1.4+.3*strength)-base_dark,0)
    mask=(source_dark>.7)&(deficit>.8)
    pal=np.asarray(baseline.pal,dtype=int)
    attrs=baseline.attr
    block=np.array([[(attrs[y//2*8+x//2]>>(((y%2)*2+x%2)*2))&3 for x in range(16)] for y in range(15)])
    pixels=np.repeat(np.repeat(block,16,0),16,1)
    options=pal[:16].reshape(4,4)[pixels]
    labs=nf.NES_LAB[options]
    error=((labs-source[...,None,:])**2).sum(-1)
    baseline_error=((base_lab-source)**2).sum(-1)
    target=base_lab[...,0]-np.minimum(deficit*(1+strength),10+8*strength)
    cost=error+(2+3*strength)*(labs[...,0]-target[...,None])**2
    # Hard limits on colour distortion and excessive darkening, per pixel.
    permitted=(error<=baseline_error[...,None]+100*strength)&(labs[...,0]>=base_lab[...,None,0]-12-8*strength)&(labs[...,0]<=base_lab[...,None,0])
    permitted &= np.linalg.norm(labs[...,1:]-base_lab[...,None,1:],axis=-1)<8+5*strength
    cost=np.where(permitted,cost,np.inf)
    selected=cost.argmin(-1)
    finite=np.isfinite(cost.min(-1))
    change=mask&finite&(selected!=baseline.idx)
    # Suppress weak isolated marks; retain isolated source detail only if strong.
    padded=np.pad(change,1)
    neighbours=sum(padded[dy:dy+240,dx:dx+256] for dy in range(3) for dx in range(3))
    change &= (neighbours>=2)|(source_dark>3)
    idx=np.where(change,selected,baseline.idx)
    result=nf.Frame(idx,baseline.pal,baseline.attr)
    assert np.array_equal(idx[~change],np.asarray(baseline.idx)[~change])
    return result,{'changed_pixels':int(change.sum()),'fraction':float(change.mean()),'strength':strength}
