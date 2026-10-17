"""Host-only solid-color tile boundary fitting; no file or device access."""
import ctypes as C
import numpy as np
import nesframe as nf
from scene_palette import quant
from tile_fit_native import load_native
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


def improve_frame(image,raw,baseline):
    attr=np.frombuffer(raw.attr,np.uint8)
    y,x=np.indices((15,16))
    choice=(attr[(y//2)*8+x//2]>>(((y%2)*2+x%2)*2))&3
    image=np.asarray(image)
    candidate,_=fit(image,dict(pal=np.asarray(raw.pal,np.uint8),choice=choice))
    a=np.asarray(baseline.preview);b=np.asarray(candidate.preview);s=nf.lab(image)
    e0=np.mean((nf.lab(a)-s)**2);e1=np.mean((nf.lab(b)-s)**2)
    return candidate if seam_error(b,image)<seam_error(a,image)*.97 and e1<=e0*1.03 else baseline
