from pathlib import Path
import sys, json
import numpy as np
from PIL import Image
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
from nesframe import _nes_colors
out=here/'latest-preview'
palette=np.array(_nes_colors(),dtype=np.uint8)
results={}
for mode in ('gray','color','color-flat','video-gray','video-color-flat'):
    ram=(out/f'{mode}.srm').read_bytes()
    rom=(out/f'{mode}.nes').read_bytes()
    chr=rom[16+16384:]
    expected=np.zeros((240,256,3),dtype=np.uint8)
    for y in range(240):
        for x in range(256):
            tile=ram[(y//8)*32+x//8]
            bit=7-x%8
            c=((chr[tile*16+y%8]>>bit)&1)|(((chr[tile*16+8+y%8]>>bit)&1)<<1)
            attr=ram[960+(y//32)*8+x//32]
            group=(attr>>(((y%32)//16)*4+((x%32)//16)*2))&3
            pi=0 if c==0 else group*4+c
            expected[y,x]=palette[ram[0x400+pi]&63]
    screenshot=Image.open(out/f'{mode}-retroarch.png').convert('RGB')
    got=np.array(screenshot)
    diff=np.any(got!=expected,axis=2)
    cursor_changes=int(diff[110:126,120:136].sum())
    diff[110:126,120:136]=False
    assert not diff.any(), (mode,int(diff.sum()))
    assert cursor_changes>0
    screenshot.resize((768,720),Image.Resampling.NEAREST).save(out/f'{mode}-retroarch-3x.png')
    results[mode]={'background_pixel_errors':int(diff.sum()),'cursor_changed_pixels':cursor_changes}
(out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(results)
