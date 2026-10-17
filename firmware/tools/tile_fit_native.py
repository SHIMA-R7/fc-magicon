"""Host-only acceleration of existing tile fitting, with the same objective."""
from pathlib import Path
import ctypes as C
import subprocess
import hashlib
import sys
import numpy as np
import nesframe as nf

def load_native():
    if getattr(sys,'frozen',False):
        lib=C.CDLL(str(Path(sys._MEIPASS)/'tilefit.dll'))
        lib.tile_fit.argtypes=[C.c_int,C.c_int]+[C.c_void_p]*5
        return lib
    source=Path(__file__).with_suffix('.c')
    folder=Path('C:/Users/Yugo/pico/work-video-quality-20261017');folder.mkdir(exist_ok=True)
    dll=folder/('tilefit-'+hashlib.sha256(source.read_bytes()).hexdigest()[:12]+'.dll')
    if not dll.exists() or source.stat().st_mtime>dll.stat().st_mtime:
        zig=next(Path('C:/Users/Yugo/pico/zig').rglob('zig.exe'))
        subprocess.run([str(zig),'cc','-shared','-O3','-ffp-contract=off',str(source),'-o',str(dll)],check=True)
    lib=C.CDLL(str(dll));lib.tile_fit.argtypes=[C.c_int,C.c_int]+[C.c_void_p]*5
    return lib

_lib=None
def fit_tiles_native(frame,limit=256):
    global _lib
    tiles=frame.idx.reshape(30,8,32,8).transpose(0,2,1,3).reshape(960,64)
    patterns,inverse=np.unique(tiles.astype(np.uint8),axis=0,return_inverse=True)
    n=len(patterns)
    if n<=limit:return frame,dict(unique_before=n,unique_after=n)
    if _lib is None:_lib=load_native()
    attr=np.frombuffer(frame.attr,np.uint8)
    y,x=np.indices((30,32));bp=((attr[(y//4)*8+x//4]>>(((y//2%2)*2+x//2%2)*2))&3).ravel()
    weights=np.zeros((4,n),np.float32);np.add.at(weights,(bp,inverse),1)
    colors=nf.lab(nf.NES[np.asarray(frame.pal[:16]).reshape(4,4)])
    cost=np.ascontiguousarray(((colors[:,:,None,:]-colors[:,None,:,:])**2).sum(-1))
    selected=np.zeros(limit,np.int32);assignment=np.zeros((4,n),np.int32)
    code=_lib.tile_fit(n,limit,patterns.ctypes.data,weights.ctypes.data,cost.ctypes.data,selected.ctypes.data,assignment.ctypes.data)
    if code:raise RuntimeError(f'tile_fit failed: {code}')
    fitted=patterns[assignment[bp,inverse]]
    idx=fitted.reshape(30,32,8,8).transpose(0,2,1,3).reshape(240,256)
    result=nf.Frame(idx,list(frame.pal),frame.attr);result.pals=frame.pals
    return result,dict(unique_before=n,unique_after=len(np.unique(fitted,axis=0)))
