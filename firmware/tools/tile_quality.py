"""Offline palette-aware selection of at most 256 background patterns.

Unlike frequency-only selection, minimize visible Lab error in each tile's
own attribute palette. Not intended as a real-time encoder yet.
"""
import numpy as np
from nesframe import Frame, NES, lab

def fit_tiles(frame, limit=256):
    raw = np.frombuffer(frame.fb, np.uint8).reshape(240,32,2)
    idx = np.unpackbits(raw[:,:,0],axis=1)+2*np.unpackbits(raw[:,:,1],axis=1)
    tiles = idx.reshape(30,8,32,8).transpose(0,2,1,3).reshape(960,64)
    patterns, inverse = np.unique(tiles,axis=0,return_inverse=True)
    if len(patterns)<=limit:
        return frame, {'unique_before':len(patterns),'unique_after':len(patterns)}
    bp = np.zeros((30,32),np.intp)
    for y in range(30):
        for x in range(32):
            bp[y,x]=(frame.attr[(y//4)*8+x//4]>>(((y//2%2)*2+x//2%2)*2))&3
    weights=np.zeros((4,len(patterns)),np.float32)
    np.add.at(weights,(bp.ravel(),inverse),1)
    colors=lab(NES[np.array(frame.pal[:16]).reshape(4,4)])
    colorcost=((colors[:,:,None,:]-colors[:,None,:,:])**2).sum(-1)
    costs=np.zeros((4,len(patterns),len(patterns)),np.float32)
    for p in range(64):
        costs+=colorcost[:,patterns[:,p,None],patterns[None,:,p]]
    weighted=(costs*weights[:,:,None]).sum(0)
    selected=[int(weighted.sum(0).argmin())]
    best=weighted[:,selected[0]].copy()
    for _ in range(limit-1):
        gains=np.maximum(best[:,None]-weighted,0).sum(0)
        gains[selected]=-1
        choice=int(gains.argmax());selected.append(choice)
        best=np.minimum(best,weighted[:,choice])
    chosen=patterns[selected]
    assignment=costs[:,:,selected].argmin(2)
    fitted=chosen[assignment[bp.ravel(),inverse]]
    output=fitted.reshape(30,32,8,8).transpose(0,2,1,3).reshape(240,256)
    result=Frame(output,list(frame.pal),frame.attr)
    result.pals=frame.pals
    return result,{'unique_before':len(patterns),'unique_after':len(np.unique(fitted,axis=0))}
