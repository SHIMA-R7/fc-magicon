"""Pack preconverted CHR/NT/palette + unsigned PCM8 for a future standalone player.

No serial/device access. FCPV v1: 64-byte little-endian header (4s + 15 uint32),
then fixed 5152-byte video records (CHR4096, NT1024 including attrs, palette32),
then mono unsigned PCM8. CRC32 covers the complete body.
"""
import argparse
import ctypes as C
import json
import struct
import wave
import zlib
from pathlib import Path
import numpy as np
import nesframe as nf

HEADER=struct.Struct('<4s15I')
FRAME_BYTES=4096+1024+32

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('folder',type=Path)
    ap.add_argument('output',type=Path)
    ap.add_argument('--converter',required=True,type=Path)
    ap.add_argument('--fps',required=True,type=int)
    ap.add_argument('--gain',type=float,default=20)
    args=ap.parse_args()
    if args.fps<=0 or not np.isfinite(args.gain) or args.gain<0:
        ap.error('fps must be positive; gain must be finite and nonnegative')
    lib=C.CDLL(str(args.converter.resolve()));lib.convert.argtypes=[C.c_void_p]*3
    with np.load(args.folder/'sequence.npz',allow_pickle=False) as z:
        fb=z['fb'];pal=z['pal'];attr=z['attr'];expected=z['expected']
    count=len(fb)
    assert count and fb.shape==(count,15360) and pal.shape==(count,32) and attr.shape==(count,64)
    assert all(v.dtype==np.uint8 for v in (fb,pal,attr,expected))
    chr_data=np.zeros(4096,np.uint8);nt=np.zeros(1024,np.uint8)
    video=bytearray()
    for k in range(count):
        frame=np.ascontiguousarray(fb[k])
        lib.convert(frame.ctypes.data,chr_data.ctypes.data,nt.ctypes.data)
        nt[960:]=attr[k]
        tiles=chr_data.reshape(256,16)[nt[:960].reshape(30,32)]
        pixels=(np.unpackbits(tiles[:,:,:8],axis=2).reshape(30,32,8,8)+
                2*np.unpackbits(tiles[:,:,8:],axis=2).reshape(30,32,8,8))
        pixels=pixels.transpose(0,2,1,3).reshape(240,256)
        got=np.asarray(nf.render(pixels,pal[k],nt[960:].tobytes()))
        assert np.array_equal(got,expected[k]),f'frame {k} differs from reference'
        video+=chr_data.tobytes()+nt.tobytes()+pal[k].tobytes()
    with wave.open(str(args.folder/'audio-32k.wav'),'rb') as w:
        assert w.getnchannels()==1 and w.getsampwidth()==2
        rate=w.getframerate()
        audio=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64)*args.gain
    clipped=int(np.count_nonzero((audio>32767)|(audio<-32768)))
    pcm=np.clip(np.rint(np.clip(audio,-32768,32767)/256)+128,0,255).astype(np.uint8).tobytes()
    assert abs(len(pcm)/rate-count/args.fps)<0.1,'audio/video durations differ'
    body=bytes(video)+pcm
    # version, header size, frames, fps numerator/denominator, sample rate/count,
    # record size, video offset, audio offset, total size, CRC32, flags, reserved2.
    values=(1,HEADER.size,count,args.fps,1,rate,len(pcm),FRAME_BYTES,HEADER.size,
            HEADER.size+len(video),HEADER.size+len(body),zlib.crc32(body),1,0,0)
    blob=HEADER.pack(b'FCPV',*values)+body
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(blob)
    check=args.output.read_bytes()
    assert check==blob and zlib.crc32(check[HEADER.size:])==values[11]
    result=dict(format='FCPV v1',frames=count,fps=args.fps,duration_s=count/args.fps,
        record_bytes=FRAME_BYTES,video_bytes=len(video),audio_bytes=len(pcm),
        audio_format='unsigned mono PCM8',audio_rate=rate,gain=args.gain,
        clipped_samples=clipped,total_bytes=len(blob),flash_slot_bytes=8*1024*1024,
        all_frames_match_reference=True,crc32=f'{values[11]:08x}',device_written=False)
    args.output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
