from pathlib import Path
import os,sys,subprocess,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
here=Path(__file__).resolve().parent;out=here/'video-load'
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
sys.path.insert(0,str(here.parents[1]/'tools'))
from imageio_ffmpeg import get_ffmpeg_exe
from nesframe import render
ffmpeg=get_ffmpeg_exe()
with np.load(out/'sequence.npz') as z:original=z['original'];expected=z['expected']
with np.load(out/'nestopia/rendered.npz') as z:native=z['rgb']
assert len(native)==180 and np.array_equal(native,expected)
font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',14)
def write_video(path,frames,size,audio,scale):
 cmd=[ffmpeg,'-y','-loglevel','error','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{size[0]}x{size[1]}','-framerate','30','-i','pipe:0','-i',str(audio),'-t','6','-vf',f'scale={scale[0]}:{scale[1]}:flags=neighbor','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(path)]
 proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
 for frame in frames:proc.stdin.write(np.asarray(frame,dtype=np.uint8).tobytes())
 proc.stdin.close();err=proc.stderr.read();assert proc.wait()==0,err.decode(errors='replace')
def comparison():
 for a,b in zip(original,native):
  image=Image.new('RGB',(512,264));image.paste(Image.fromarray(a),(0,24));image.paste(Image.fromarray(b),(256,24))
  d=ImageDraw.Draw(image);d.text((5,4),'SYNTHETIC SOURCE',font=font,fill='white');d.text((260,4),'NESTOPIA / IDEAL 30 FPS',font=font,fill='white')
  yield image
write_video(out/'color-video-nestopia-30fps.mp4',comparison(),(512,264),out/'test-audio.wav',(1024,528))
with np.load(out/'link-650000Bps-30fps-chunked.npz') as z:times=z['times'];packets=z['packets']
def transport_frames():
 for i in range(180):
  k=np.searchsorted(times,i/30,side='right')-1
  if k<0:yield Image.new('RGB',(256,240));continue
  packet=packets[k];fb=packet[:15360].reshape(240,32,2)
  idx=np.unpackbits(fb[:,:,0],axis=1)|np.unpackbits(fb[:,:,1],axis=1)*2
  yield render(idx,list(packet[15360:15392]),packet[15392:15456])
write_video(out/'color-audio-transport-model.mp4',transport_frames(),(256,240),out/'audio-650000Bps-30fps-chunked.wav',(768,720))
Image.fromarray(native[90]).resize((768,720),Image.Resampling.NEAREST).save(out/'color-video-frame90.png')
print('PASS 180 displayed frames equal expected; two MP4s with test audio written')
