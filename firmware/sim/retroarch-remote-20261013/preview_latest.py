"""Build static remote desktop fixtures using the actual converter and 6502 driver."""
from pathlib import Path
import re, sys, subprocess, json
import numpy as np
from PIL import Image

here=Path(__file__).resolve().parent
firmware=here.parents[1]
sys.path.insert(0,str(firmware/'tools'))
from nesframe import encode
out=here/'latest-preview'
out.mkdir(exist_ok=True)
header=(firmware/'magicon/remote_full_emulator_driver.h').read_text(encoding='utf-8')
def array(name):
    body=re.search(r'\b'+name+r'\[\d+\]\s*=\s*\{(.*?)\};',header,re.S).group(1)
    return bytes(int(x,16) for x in re.findall(r'0x([0-9A-Fa-f]{2})',body))
prg,spr=array('remote_prg'),array('remote_spr_chr')
original=Image.open(sys.argv[1]).convert('RGB')
source=original.resize((256,240),Image.Resampling.LANCZOS)
source.save(out/'pc-source.png')
video=original.crop((10,94,1348,846)).resize((256,240),Image.Resampling.LANCZOS)
for case,mode,img,dither in [('gray','gray',source,False),('color','color',source,True),('color-flat','color',source,False),('video-gray','gray',video,False),('video-color-flat','color',video,False)]:
    frame=encode(img,mode,dither=dither)
    mode=case
    (out/f'{mode}.fb').write_bytes(frame.fb)
    subprocess.run([str(here/'converter.exe'),str(out/f'{mode}.fb'),str(out/f'{mode}.chr'),str(out/f'{mode}.nt')],check=True)
    nt=bytearray((out/f'{mode}.nt').read_bytes());nt[960:1024]=frame.attr
    chr=bytearray((out/f'{mode}.chr').read_bytes());chr[4096:]=bytes(4096);chr[4096:4160]=spr
    ram=bytearray(8192);ram[:1024]=nt;ram[0x400:0x420]=bytes(frame.pal);ram[0x420:0x460]=frame.attr
    ram[0x500:0x600]=bytes([0xf0])*256
    cx,cy=120,110
    for i in range(4):
        ram[0x500+i*4:0x504+i*4]=bytes([cy+(i//2)*8-1,i,0,cx+(i%2)*8])
    # Mapper 0, battery-backed SRAM, one 16KiB PRG mirrored, 8KiB CHR.
    (out/f'{mode}.nes').write_bytes(b'NES\x1a'+bytes([1,1,2,0])+bytes(8)+prg+chr)
    (out/f'{mode}.srm').write_bytes(ram)
    frame.preview.save(out/f'{mode}-encoded.png')
print(out)
