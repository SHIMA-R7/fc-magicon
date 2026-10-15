"""Render original video beside RGB reconstructed from the actual FCPV records."""
import argparse,json,os,struct,subprocess,sys,tempfile,zlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import nesframe as nf

sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
from imageio_ffmpeg import get_ffmpeg_exe,read_frames

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('media',type=Path);ap.add_argument('source',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--original-frames',type=Path,help='Optional raw RGB source frames sampled for this conversion')
    a=ap.parse_args();data=a.media.read_bytes();h=struct.unpack('<4s15I',data[:64])
    assert h[0]==b'FCPV' and h[1]==1 and h[11]==len(data) and zlib.crc32(data[64:])==h[12]
    count,fps_num,fps_den,rate,samples,record,voff,aoff=h[3:11]
    assert record==5152 and aoff==voff+count*record and aoff+samples==len(data)
    duration=count*fps_den/fps_num
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fc-comparison-') as directory:
        directory=Path(directory);pcm=directory/'audio.pcm'
        pcm.write_bytes(data[aoff:])
        banner=Image.new('RGB',(1280,64),'black');draw=ImageDraw.Draw(banner)
        font=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',23)
        small=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',17)
        draw.text((24,5),'Original video (24 fps)',font=font,fill='white')
        draw.text((664,5),f'FC 4:3 display ({fps_num/fps_den:g} fps) / PCM8 audio',font=font,fill='white')
        draw.text((24,37),'PC reconstruction from flash data; Twin Famicom playback is not yet verified.',font=small,fill='#bbbbbb')
        banner.save(directory/'banner.png')
        filters=(f'[0:v]tpad=stop_mode=clone:stop_duration=1,trim=duration={duration:g},fps=24,'
            'scale=640:360:flags=lanczos,pad=640:480:0:60:black,setsar=1[l];'
            '[1:v]scale=640:480:flags=neighbor,fps=24,setsar=1[r];'
            '[l][r]hstack=inputs=2,pad=1280:544:0:64:black[base];'
            '[base][3:v]overlay=0:0:shortest=1[v]')
        temporary=directory/'comparison.mp4'
        process=subprocess.Popen([get_ffmpeg_exe(),'-y','-v','error','-i',str(a.source.resolve()),
            '-f','rawvideo','-pixel_format','rgb24','-video_size','256x240',
            '-framerate',f'{fps_num}/{fps_den}','-i','pipe:0',
            '-f','u8','-ar',str(rate),'-ac','1','-i',str(pcm),
            '-loop','1','-i',str(directory/'banner.png'),'-filter_complex',filters,
            '-map','[v]','-map','2:a','-t',str(duration),'-c:v','libx264','-preset','fast','-crf','18',
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(temporary)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        stills=[]
        try:
            for k in range(count):
                p=memoryview(data)[voff+k*record:voff+(k+1)*record]
                chr=np.frombuffer(p[:4096],np.uint8).reshape(256,16)
                nt=np.frombuffer(p[4096:5120],np.uint8);pal=np.frombuffer(p[5120:],np.uint8)
                tiles=chr[nt[:960].reshape(30,32)]
                idx=(np.unpackbits(tiles[:,:,:8],axis=2).reshape(30,32,8,8)+
                     2*np.unpackbits(tiles[:,:,8:],axis=2).reshape(30,32,8,8))
                idx=idx.transpose(0,2,1,3).reshape(240,256)
                pic=np.asarray(nf.render(idx,pal,nt[960:].tobytes()))
                process.stdin.write(pic.tobytes())
                if k in [int(s*fps_num/fps_den) for s in (5,20,45,70,90) if s<duration]:
                    stills.append((k,Image.fromarray(pic)))
            process.stdin.close()
            errors=process.stderr.read().decode(errors='replace')
            if process.wait(timeout=300):raise RuntimeError(errors)
        except BaseException:
            process.kill();process.wait()
            raise
        probe=read_frames(str(temporary));metadata=next(probe);probe.close()
        assert metadata['size']==(1280,544) and abs(metadata['duration']-duration)<0.15
        a.output.write_bytes(temporary.read_bytes())
        contact=Image.new('RGB',(768,288*len(stills)))
        # Full-colour source decoded at the same exact 8fps sampling used to encode.
        original_path=a.original_frames
        if original_path and original_path.exists() and original_path.stat().st_size==count*256*240*3:
            originals=np.memmap(original_path,mode='r',dtype=np.uint8,shape=(count,240,256,3))
            for row,(k,pic) in enumerate(stills):
                contact.paste(Image.fromarray(originals[k]).resize((384,288)),(0,row*288))
                contact.paste(pic.resize((384,288),Image.Resampling.NEAREST),(384,row*288))
            contact.save(a.output.with_suffix('.contact.png'))
    result=dict(duration_s=duration,frames=count,fps=fps_num/fps_den,resolution=[1280,544],
        display_aspect='4:3',pixel_aspect='5:4',
        left='original full-colour source at 24fps',right='FCPV CHR/NT/palette reconstruction',
        audio='saved unsigned PCM8 transcoded to AAC',hardware_recording=False,
        source_url='https://www.youtube.com/watch?v=U6Wlb18KLrI',bytes=a.output.stat().st_size)
    a.output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
