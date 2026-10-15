"""Combine a standalone firmware UF2 and local FCPV into one verified UF2. No flashing."""
import argparse,hashlib,json,struct,zlib,subprocess,tempfile
from pathlib import Path

MAGIC0=0x0a324655
MAGIC1=0x9e5d5157
END=0x0ab16f30
BASE=0x10000000
MEDIA=BASE+0x00800000
LIMIT=BASE+0x01000000

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('firmware',type=Path);ap.add_argument('media',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--picotool',type=Path,default=Path(r'C:\Users\Yugo\pico\picotool\picotool\picotool.exe'))
    ap.add_argument('--cold-boot',action='store_true',help='Mark the USB-disabled early-response firmware variant')
    ap.add_argument('--post-diagnostic-usb',action='store_true',help='USB is enabled only after a diagnostic has completed')
    a=ap.parse_args();fw=a.firmware.read_bytes();media=a.media.read_bytes()
    assert len(fw)%512==0 and len(media)>=64 and media[:4]==b'FCPV'
    mh=struct.unpack('<4s15I',media[:64]);assert mh[11]==len(media)
    assert zlib.crc32(media[64:])==mh[12] and MEDIA+len(media)<=LIMIT
    family=None;intervals=[];firmware_payload={}
    for at in range(0,len(fw),512):
        block=fw[at:at+512];h=struct.unpack_from('<8I',block)
        assert h[0:2]==(MAGIC0,MAGIC1) and struct.unpack_from('<I',block,508)[0]==END
        # Official RP2350-E10 ignored absolute block; picotool preserves it.
        if h[7]==0xe48bff57:
            assert h[2]==0xa000 and h[3]==0x10ffff00 and h[4]==256 and h[5:7]==(0,2)
            assert block[32:288]==b'\xef'*256
            continue
        assert h[2]==0x2000 and 0<h[4]<=476 and BASE<=h[3]<h[3]+h[4]<=MEDIA
        if family is None:family=h[7]
        assert family==h[7]
        intervals.append((h[3],h[3]+h[4]))
        firmware_payload[h[3]]=block[32:32+h[4]]
    assert all(left[1]<=right[0] for left,right in zip(sorted(intervals),sorted(intervals)[1:])), 'overlapping firmware blocks'
    with tempfile.TemporaryDirectory(prefix='fc-pv-uf2-') as directory:
        temporary=Path(directory)
        firmware_file=temporary/'firmware.uf2';firmware_file.write_bytes(fw)
        media_file=temporary/'media.bin';media_file.write_bytes(media)
        media_uf2=temporary/'media.uf2';combined=temporary/'combined.uf2'
        subprocess.run([str(a.picotool),'uf2','convert',str(media_file),'-t','bin',str(media_uf2),
            '-o',hex(MEDIA),'--family',hex(family),'--platform','rp2350'],check=True,timeout=60)
        subprocess.run([str(a.picotool),'uf2','combine',str(firmware_file),str(media_uf2),str(combined)],check=True,timeout=60)
        result=combined.read_bytes()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(result)
    # Reconstruct flash bytes from the final file, not from the input buffers.
    got=a.output.read_bytes();rebuilt=bytearray((len(media)+255)//256*256)
    seen_firmware={};seen_media=set();families={}
    for at in range(0,len(got),512):
        block=got[at:at+512];h=struct.unpack_from('<8I',block)
        if h[7]!=family:continue
        assert h[5]==families.get(family,0)
        families[family]=h[5]+1
        if h[3]>=MEDIA:
            assert MEDIA<=h[3]<h[3]+h[4]<=MEDIA+len(rebuilt) and h[3] not in seen_media
            seen_media.add(h[3]);rebuilt[h[3]-MEDIA:h[3]-MEDIA+h[4]]=block[32:32+h[4]]
        else:seen_firmware[h[3]]=block[32:32+h[4]]
    assert rebuilt[:len(media)]==media and seen_firmware==firmware_payload
    manifest=dict(firmware=str(a.firmware.resolve()),media=str(a.media.resolve()),
        firmware_bytes=len(fw),media_bytes=len(media),uf2_bytes=len(got),blocks=len(got)//512,
        family_id=f'0x{family:08x}',media_address=f'0x{MEDIA:08x}',
        sha256=hashlib.sha256(got).hexdigest(),media_reconstruction_matches=True,
        device_written=False,cold_boot=a.cold_boot,
        usb_recovery=('BOOTSEL required; USB device deliberately disabled' if a.cold_boot else
                      'Optional CDC/picotool; BOOTSEL also available; playback never waits for a host'))
    if a.post_diagnostic_usb:
        manifest['post_diagnostic_usb']=True
        manifest['usb_recovery']='USB CDC starts only after diagnostic completion; BOOTSEL remains available'
    a.output.with_suffix('.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
