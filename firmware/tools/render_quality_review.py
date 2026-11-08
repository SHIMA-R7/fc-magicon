"""Original/current/new comparison and complete-record checks for quality video."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from pathlib import Path
import sys,struct,json,subprocess,tempfile,argparse
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from build_quality_video import ROOT,OLD,OUT,SOURCE,MEDIA,score
import nesframe as nf
sys.path.insert(0,str(Path(tempfile.gettempdir())/'fc-video-deps-20261013'))
from imageio_ffmpeg import get_ffmpeg_exe

def decode(blob):
    chr=np.frombuffer(blob[:4096],np.uint8).reshape(256,16)
    nt=np.frombuffer(blob[4096:5120],np.uint8);pal=np.frombuffer(blob[5120:],np.uint8)
    assert len(set(int(pal[j]) for j in (0,4,8,12,16,20,24,28)))==1
    tiles=chr[nt[:960].reshape(30,32)]
    idx=(np.unpackbits(tiles[:,:,:8],axis=2).reshape(30,32,8,8)+2*np.unpackbits(tiles[:,:,8:],axis=2).reshape(30,32,8,8)).transpose(0,2,1,3).reshape(240,256)
    return np.asarray(nf.render(idx,pal,nt[960:].tobytes()))

def main():
    global OUT
    ap=argparse.ArgumentParser();ap.add_argument('--directory',type=Path,default=OUT);ap.add_argument('--media',default='pv-full-99s-8fps-quality.fcpv');args=ap.parse_args()
    OUT=args.directory
    before=MEDIA.read_bytes();after=(OUT/args.media).read_bytes()
    h=struct.unpack('<4s15I',after[:64]);images=np.memmap(SOURCE,mode='r',dtype=np.uint8,shape=(792,240,256,3))
    assert after[h[10]:]==before[h[10]:]
    oldscore=[];newscore=[];changed=0
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    banner=Image.new('RGB',(1152,60),'black');draw=ImageDraw.Draw(banner)
    for x,label in [(8,'Original source'),(392,'Current successful version'),(776,'New conversion')]:draw.text((x,4),label,fill='white',font=font)
    draw.text((8,34),'PC reconstruction / 8fps / identical audio / not an FC recording',fill='#bbbbbb',font=font)
    contact=Image.new('RGB',(1152,60+318*5),'black');contact.paste(banner,(0,0))
    chosen={56:0,160:1,200:2,360:3,560:4}
    with tempfile.TemporaryDirectory(prefix='fc-quality-review-') as folder:
        pcm=Path(folder)/'audio.pcm';pcm.write_bytes(after[h[10]:h[10]+30*32000])
        command=[get_ffmpeg_exe(),'-y','-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size','1152x348','-framerate','8','-i','pipe:0','-f','u8','-ar','32000','-ac','1','-i',str(pcm),'-t','30','-vf','fps=24','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-movflags','+faststart',str(OUT/'comparison-first30s.mp4')]
        encoder=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for k in range(792):
                oldblob=before[64+k*5152:64+(k+1)*5152];newblob=after[64+k*5152:64+(k+1)*5152]
                old=decode(oldblob);new=decode(newblob)
                with np.load(OUT/'frames'/f'{k:04d}.npz') as z:assert np.array_equal(new,z['expected']),k
                oldscore.append(score(images[k],old));newscore.append(score(images[k],new));changed+=oldblob!=newblob
                if k<240 or k in chosen:
                    panel=Image.new('RGB',(1152,348),'black');panel.paste(banner,(0,0))
                    for c,pic in enumerate([images[k],old,new]):panel.paste(Image.fromarray(pic).resize((384,288),Image.Resampling.NEAREST),(c*384,60))
                    if k<240:encoder.stdin.write(panel.tobytes())
                    if k in chosen:
                        y=60+chosen[k]*318
                        contact.paste(panel.crop((0,60,1152,348)),(0,y+30))
                        ImageDraw.Draw(contact).text((8,y+5),f'{k/8:g}s',fill='white',font=font)
                if k%160==0:print(f'REVIEW {k+1}/792',flush=True)
            encoder.stdin.close();errors=encoder.stderr.read().decode(errors='replace')
            if encoder.wait(timeout=60):raise RuntimeError(errors)
        except BaseException:encoder.kill();encoder.wait();raise
    contact.save(OUT/'final-comparison.png')
    result=dict(frames_reconstructed_and_verified=792,changed_frames=changed,audio_bit_identical=True,
        mean_old_score=float(np.mean(oldscore)),mean_new_score=float(np.mean(newscore)),
        score_reduction_pct=float(100*(1-np.mean(newscore)/np.mean(oldscore))),
        frames_lower_score=int(np.sum(np.array(newscore)<oldscore)),frames_higher_score=int(np.sum(np.array(newscore)>oldscore)),
        metric='0.4 edge-weighted per-pixel squared Lab error + 0.6 squared error after 2x2 Lab averaging; not a subjective quality percentage',
        video='comparison-first30s.mp4',hardware_capture=False)
    (OUT/'full-review.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
