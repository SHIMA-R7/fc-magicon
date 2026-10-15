from pathlib import Path
import sys,json,time
import numpy as np
from PIL import Image,ImageDraw
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
import nesframe as nf
from tile_quality import fit_tiles
folder=here/'youtube-U6Wlb18KLrI'
z=np.load(folder/'sequence.npz')
records=[]; rows=[]
for i in (150,300,600):
    source=z['original'][i]
    images=[Image.fromarray(source)];candidates=[]
    for amplitude in (48,24,0):
        nf.DITHER_RGB=amplitude
        start=time.perf_counter()
        fr=nf.encode(Image.fromarray(source),'color',iters=8,dither=amplitude>0,smooth=0,_bg_mode='best4')
        fitted,counts=fit_tiles(fr)
        error=float(np.mean(np.sum((nf.lab(np.asarray(fitted.preview))-nf.lab(source))**2,axis=-1)))
        records.append(dict(frame=i,dither=amplitude,lab_mse=error,seconds=time.perf_counter()-start,**counts))
        images.append(fitted.preview);candidates.append((error,fitted,amplitude))
        print(records[-1],flush=True)
    _,winner,amp=min(candidates,key=lambda c:c[0])
    nf.write_frame(str(folder/f'quality-frame-{i}.bin'),winner)
    winner.preview.resize((768,720),Image.Resampling.NEAREST).save(folder/f'quality-frame-{i}.png')
    row=Image.new('RGB',(1024,260))
    for x,img in enumerate(images):row.paste(img,(x*256,20))
    ImageDraw.Draw(row).text((4,3),f'{i/30:g}s: original | dither 48 | dither 24 | no dither; selected {amp}',fill='white')
    rows.append(row)
out=Image.new('RGB',(1024,780))
for j,row in enumerate(rows):out.paste(row,(0,j*260))
out.save(folder/'quality-candidates.png')
(folder/'quality-candidates.json').write_text(json.dumps(records,indent=2))
