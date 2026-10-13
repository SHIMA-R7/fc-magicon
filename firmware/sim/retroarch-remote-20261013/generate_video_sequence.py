"""Synthetic moving image and synchronized test audio; not game/video footage."""
from pathlib import Path
import sys,time,json,wave
import numpy as np
from PIL import Image,ImageDraw
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
from nesframe import encode
from pcaudio import packets,AdpcmEncoder,FMT_PCM16
out=here/'video-load';out.mkdir(exist_ok=True)
source=Image.open(sys.argv[1]).convert('RGB')
fb=[];pal=[];attr=[];expected=[];original=[];timings=[];audio_times=[];prev=None
rate=32000;fps=30;count=180
t=np.arange(rate*6)/rate
audio=(0.22*np.sin(2*np.pi*(220*t+30*t*t))+0.09*np.sin(2*np.pi*660*t)).astype(np.float32)
for i in range(count):
 phase=i/fps
 w,h=source.size;cw,ch=w/1.08,h/1.08
 x=(w-cw)*(0.5+0.48*np.sin(phase*0.8));y=(h-ch)*(0.5+0.48*np.cos(phase*0.6))
 image=source.crop((round(x),round(y),round(x+cw),round(y+ch))).resize((256,240),Image.Resampling.LANCZOS)
 draw=ImageDraw.Draw(image);draw.rectangle((0,224,255,239),fill='black')
 draw.text((4,227),f'COLOR + AUDIO  {i:03} / 180',fill='white')
 draw.rectangle((210,228,210+round(40*(i%30)/29),234),fill=(255,128,64))
 start=time.perf_counter();frame=encode(image,'color',prev=prev,iters=2 if prev else 4)
 timings.append((time.perf_counter()-start)*1000);prev=frame
 a=audio[i*rate//fps:(i+1)*rate//fps]
 start=time.perf_counter();packets(a,FMT_PCM16,AdpcmEncoder());audio_times.append((time.perf_counter()-start)*1000)
 fb.append(np.frombuffer(frame.fb,dtype=np.uint8));pal.append(frame.pal)
 attr.append(np.frombuffer(frame.attr,dtype=np.uint8));expected.append(np.asarray(frame.preview));original.append(np.asarray(image))
 if i%30==0:print('Converted',i,'ms',round(timings[-1],2),flush=True)
np.savez_compressed(out/'sequence.npz',fb=np.array(fb),pal=np.array(pal,dtype=np.uint8),attr=np.array(attr),expected=np.array(expected),original=np.array(original))
with wave.open(str(out/'test-audio.wav'),'wb') as f:
 f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes((audio*32767).astype('<i2').tobytes())
(out/'empty-input.json').write_text('[]')
(out/'conversion-results.json').write_text(json.dumps({'frames':count,'fps_target':fps,'synthetic_source':True,'color_ms':{'mean':float(np.mean(timings)),'p95':float(np.percentile(timings,95)),'max':max(timings),'over_33_33ms':sum(x>1000/fps for x in timings)},'audio_pcm16_ms_mean':float(np.mean(audio_times)),'frame_timings_ms':timings},indent=2))
print('Mean color ms',round(float(np.mean(timings)),2),'p95',round(float(np.percentile(timings,95)),2),flush=True)
