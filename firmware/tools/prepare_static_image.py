"""Compile the requested image to a 128x128, four-gray NROM background asset.

No upload or console display. Output is CHR, nametable, palette, and preview.
"""
from pathlib import Path
import json
from PIL import Image
from asm6502 import Asm, write_header

ROOT = Path(__file__).resolve().parents[2]

def main():
    source=ROOT/'JN7xCleD_400x400.jpg'
    dest=ROOT/'firmware/out-image-diagnostic'
    dest.mkdir(exist_ok=True)
    gray=Image.open(source).convert('L').resize((128,128),Image.Resampling.LANCZOS)
    pixels=[min(3,(v+42)//85) for v in gray.getdata()]
    tiles=[bytes(16)]; mapping={tiles[0]:0}; nt=bytearray(1024)
    for ty in range(16):
        for tx in range(16):
            planes=bytearray(16)
            for row in range(8):
                for col in range(8):
                    v=pixels[(ty*8+row)*128+tx*8+col]
                    planes[row]|=(v&1)<<(7-col)
                    planes[row+8]|=((v>>1)&1)<<(7-col)
            tile=bytes(planes)
            if tile not in mapping:
                mapping[tile]=len(tiles);tiles.append(tile)
            nt[(ty+7)*32+tx+8]=mapping[tile]
    assert len(tiles)<=256, f'{len(tiles)} tiles exceed one pattern table'
    chr_data=b''.join(tiles).ljust(8192,b'\0')
    for ty in range(16):
        for tx in range(16):
            tile=nt[(ty+7)*32+tx+8]
            for row in range(8):
                for col in range(8):
                    decoded=((chr_data[tile*16+row]>>(7-col))&1)|(((chr_data[tile*16+8+row]>>(7-col))&1)<<1)
                    assert decoded==pixels[(ty*8+row)*128+tx*8+col]
    preview=Image.new('RGB',(256,240),'black')
    part=Image.new('L',(128,128));part.putdata([v*85 for v in pixels]);preview.paste(part,(64,56))
    preview.save(dest/'JN7xCleD-preview.png')
    (dest/'JN7xCleD.chr').write_bytes(chr_data)
    (dest/'JN7xCleD.nametable').write_bytes(nt)
    (dest/'JN7xCleD.palette').write_bytes(bytes([0x0f,0x00,0x10,0x30])*4)
    a=Asm(0xc000)
    a.label('reset');a.sei();a.cld();a.ldx_imm(255);a.txs()
    a.lda_imm(0);a.sta(0x2000);a.sta(0x2001);a.sta(0x4015);a.sta_zp(0)
    for vblank in ('vbl1','vbl2'):
        a.label(vblank);a.bit(0x2002);a.bpl(vblank)
    a.lda_imm(0x3f);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006);a.ldx_imm(0)
    a.label('pal');a.lda_absx('palette');a.sta(0x2007);a.inx();a.cpx_imm(16);a.bne('pal')
    a.lda_imm(0x20);a.sta(0x2006);a.lda_imm(0);a.sta(0x2006)
    for page in range(4):
        a.ldx_imm(0);a.label(f'nt{page}');a.lda_absx(f'ntdata{page}')
        a.sta(0x2007);a.inx();a.bne(f'nt{page}')
    a.lda_imm(0);a.sta(0x2005);a.sta(0x2005);a.sta(0x2000)
    a.lda_imm(0x0a);a.sta(0x2001)
    a.label('loop');a.inc_zp(0);a.lda_zp(0);a.sta(0x8000);a.jmp('loop')
    a.label('loop_end');a.label('nmi');a.rti()
    a.label('palette');a.bytes_(bytes([0x0f,0x00,0x10,0x30])*4)
    for page in range(4):a.label(f'ntdata{page}');a.bytes_(nt[page*256:(page+1)*256])
    prg,listing=a.build(0x4000,{'nmi':'nmi','reset':'reset','irq':'nmi'})
    header=ROOT/'firmware/magicon/static_image.h'
    write_header(str(header),'static_image_prg',prg,listing,'Generated static JN7xCleD image diagnostic PRG')
    with header.open('a',encoding='utf-8') as f:
        f.write(f'\n#define STATIC_IMAGE_LOOP_START {a.labels["loop"]&0x3fff}\n')
        f.write(f'#define STATIC_IMAGE_LOOP_END {a.labels["loop_end"]&0x3fff}\n')
        f.write('static const unsigned char static_image_chr[8192] = {\n')
        for offset in range(0,8192,16):f.write('  '+','.join(str(v) for v in chr_data[offset:offset+16])+',\n')
        f.write('};\n')
    (dest/'JN7xCleD.nes').write_bytes(b'NES\x1a'+bytes([1,1,1,0])+bytes(8)+bytes(prg)+chr_data)
    assert len(prg)==16384 and prg[a.labels['loop']-0xc000:a.labels['loop_end']-0xc000][:7]==bytes([0xe6,0,0xa5,0,0x8d,0,0x80])
    meta={'source':str(source),'image_pixels':[128,128],'position':[64,56],
          'unique_tiles':len(tiles),'mode':'four gray levels','console_displayed':False}
    (dest/'JN7xCleD.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Prepared {len(tiles)} tiles and NROM PRG; every image pixel verified against CHR/nametable. Not uploaded.')

if __name__=='__main__':main()
