"""Fixture for the original position-dependent CHR responder in the validation core."""
from pathlib import Path
import re,sys
from PIL import Image
here=Path(__file__).resolve().parent
firmware=here.parents[1]
sys.path.insert(0,str(firmware/'tools'))
from nesframe import encode
out=here/'latest-preview'
header=(firmware/'magicon/remote_emulator_driver.h').read_text(encoding='utf-8')
def array(name):
    body=re.search(r'\b'+name+r'\[\d+\]\s*=\s*\{(.*?)\};',header,re.S).group(1)
    return bytes(int(x,16) for x in re.findall(r'0x([0-9A-Fa-f]{2})',body))
prg,spr=array('remote_prg'),array('remote_spr_chr')
original=Image.open(sys.argv[1]).convert('RGB')
cases=[('desktop',original),('video',original.crop((10,94,1348,846)))]
if len(sys.argv)>2:cases.append(('bluearchive',Image.open(sys.argv[2]).convert('RGB')))
for case,image in cases:
 for mode in ('gray','color'):
    name=f'{case}-{mode}-lossless'
    frame=encode(image.resize((256,240),Image.Resampling.LANCZOS),mode)
    (out/f'{name}.fb').write_bytes(frame.fb)
    frame.preview.save(out/f'{name}-expected.png')
    chr=bytearray(8192);chr[4096:4160]=spr
    ram=bytearray(8192);ram[0x400:0x420]=bytes(frame.pal);ram[0x420:0x460]=frame.attr
    ram[0x500:0x600]=bytes([0xf0])*256
    for i in range(4):ram[0x500+i*4:0x504+i*4]=bytes([109+(i//2)*8,i,0,120+(i%2)*8])
    (out/f'{name}.nes').write_bytes(b'NES\x1a'+bytes([1,1,2,0])+bytes(8)+prg+chr)
    (out/f'{name}.srm').write_bytes(ram)
