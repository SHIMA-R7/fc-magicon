from pathlib import Path
import os,sys,subprocess,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
here=Path(__file__).resolve().parent;out=here/'youtube-U6Wlb18KLrI'
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
from imageio_ffmpeg import get_ffmpeg_exe
with np.load(out/'sequence.npz') as z:original=z['original'];expected=z['expected']
with np.load(out/'nestopia/rendered.npz') as z:native=z['rgb']
assert len(native)==900 and np.array_equal(native,expected)
results=json.loads((out/'nestopia/stream-results.json').read_text())
assert len(results)==1800 and all(r['pixel_errors']==0 for r in results)
def video(name,frames,size,scale):
 cmd=[get_ffmpeg_exe(),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{size[0]}x{size[1]}','-r','30','-i','pipe:0','-i',str(out/'audio-transferred.wav'),'-t','30','-vf',f'scale={scale[0]}:{scale[1]}:flags=neighbor','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(out/name)]
 p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
 for frame in frames:p.stdin.write(np.asarray(frame,dtype=np.uint8).tobytes())
 p.stdin.close();err=p.stderr.read();assert p.wait()==0,err.decode(errors='replace')
video('transferred-30s.mp4',native,(256,240),(768,720))
font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',14)
def comparison():
 for source,shown in zip(original,native):
  image=Image.new('RGB',(512,264));image.paste(Image.fromarray(source),(0,24));image.paste(Image.fromarray(shown),(256,24))
  d=ImageDraw.Draw(image);d.text((5,4),'SOURCE / 0-30 SECONDS',font=font,fill='white');d.text((260,4),'NESTOPIA / COLOR TRANSFER',font=font,fill='white')
  yield image
video('comparison-30s.mp4',comparison(),(512,264),(1024,528))
for i in [150,300,600]:Image.fromarray(native[i]).resize((768,720),Image.Resampling.NEAREST).save(out/f'frame-{i//30:02}s.png')
(out/'validation-results.json').write_text(json.dumps({'source_frames':900,'displayed_frames':1800,'rgb_pixel_errors':0,'test_type':'ideal full framebuffer Nestopia core; no real cartridge or real network','audio':'actual PCM16 packet encoder/C decoder + 10-bit PWM quantization; no real analog output'},indent=2))
print('PASS 900 source / 1800 displayed frames, no RGB errors; two 30-second MP4s written')
