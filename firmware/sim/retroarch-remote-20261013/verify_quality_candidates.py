from pathlib import Path
import sys,ctypes as C,json
import numpy as np
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
from nesframe import render,lab
folder=here/'youtube-U6Wlb18KLrI'
z=np.load(folder/'sequence.npz')
lib=C.CDLL(str(here/'converter-stream.dll'));lib.convert.argtypes=[C.c_void_p]*3
chr=np.zeros(4096,np.uint8);nt=np.zeros(1024,np.uint8)
def reconstruct(fb,pal,attr):
    lib.convert(fb.ctypes.data,chr.ctypes.data,nt.ctypes.data)
    t=chr.reshape(256,16)[nt[:960].reshape(30,32)]
    idx=(np.unpackbits(t[:,:,:8],axis=2).reshape(30,32,8,8)+2*np.unpackbits(t[:,:,8:],axis=2).reshape(30,32,8,8)).transpose(0,2,1,3).reshape(240,256)
    return np.asarray(render(idx,pal,attr))
records=[]
for i in (150,300,600):
    baseline=reconstruct(z['fb'][i].copy(),z['pal'][i],z['attr'][i])
    data=(folder/f'quality-frame-{i}.bin').read_bytes()
    fb=np.frombuffer(data[:15360],np.uint8).copy();pal=list(data[15360:15392]);attr=data[15392:15456]
    raw=fb.reshape(240,32,2)
    ideal=np.asarray(render(np.unpackbits(raw[:,:,0],axis=1)+2*np.unpackbits(raw[:,:,1],axis=1),pal,attr))
    for _ in range(3):got=reconstruct(fb,pal,attr)
    assert np.array_equal(got,ideal),'Firmware introduced additional approximation'
    source=lab(z['original'][i])
    old=float(np.mean(np.sum((lab(baseline)-source)**2,axis=-1)))
    new=float(np.mean(np.sum((lab(got)-source)**2,axis=-1)))
    records.append(dict(frame=i,baseline_lab_mse=old,candidate_lab_mse=new,reduction_percent=100*(old-new)/old,firmware_extra_rgb_errors=0))
(folder/'quality-verification.json').write_text(json.dumps(records,indent=2))
print(records)
