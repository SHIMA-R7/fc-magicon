"""Real requested footage, converted by the actual remote color/audio encoders."""
from pathlib import Path
import os,sys,json,time,subprocess,wave,ctypes as C
import numpy as np
here=Path(__file__).resolve().parent;out=here/'youtube-U6Wlb18KLrI'
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
sys.path.insert(0,str(here.parents[1]/'tools'))
from imageio_ffmpeg import get_ffmpeg_exe
from nesframe import encode
from pcaudio import packets,AdpcmEncoder,FMT_PCM16
from PIL import Image
ffmpeg=get_ffmpeg_exe();source=next(out.glob('source-30s.*'))
subprocess.run([ffmpeg,'-y','-v','error','-i',str(source),'-t','30','-vf','fps=30,scale=256:240:flags=lanczos','-frames:v','900','-f','rawvideo','-pix_fmt','rgb24',str(out/'source.rgb')],check=True)
subprocess.run([ffmpeg,'-y','-v','error','-i',str(source),'-t','30','-ac','1','-ar','32000','-c:a','pcm_s16le',str(out/'audio-32k.wav')],check=True)
original=np.fromfile(out/'source.rgb',dtype=np.uint8).reshape(-1,240,256,3)
assert len(original)==900,len(original)
fb=[];pal=[];attr=[];expected=[];timings=[];prev=None
for i,image in enumerate(original):
 start=time.perf_counter();frame=encode(Image.fromarray(image),'color',prev=prev,iters=2 if prev else 4)
 timings.append((time.perf_counter()-start)*1000);prev=frame
 fb.append(np.frombuffer(frame.fb,dtype=np.uint8));pal.append(frame.pal);attr.append(np.frombuffer(frame.attr,dtype=np.uint8));expected.append(np.asarray(frame.preview))
 if i%150==0:print('Converted',i,'/',len(original),flush=True)
np.savez_compressed(out/'sequence.npz',fb=np.array(fb),pal=np.array(pal,dtype=np.uint8),attr=np.array(attr),expected=np.array(expected),original=original)
rom=here/'video-load/video.nes';sram=here/'video-load/video.srm'
(out/'video.nes').write_bytes(rom.read_bytes());(out/'video.srm').write_bytes(sram.read_bytes());(out/'empty-input.json').write_text('[]')
with wave.open(str(out/'audio-32k.wav'),'rb') as w:samples=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
codec=C.CDLL(str(here/'audio-codec.dll'));codec.decode.argtypes=[C.c_uint8,C.c_uint16,C.c_void_p,C.c_void_p];codec.decode.restype=C.c_uint
decoded=[];packet_count=0
for packet in packets(samples.astype(np.float32)/32767,FMT_PCM16,AdpcmEncoder()):
 fmt,n=__import__('struct').unpack_from('<BH',packet,4);payload=C.create_string_buffer(packet[7:]);a=np.empty(n,dtype=np.int16)
 assert codec.decode(fmt,n,payload,a.ctypes.data)==n
 # Actual audio.c's 10-bit PWM quantization, represented as signed PCM for preview.
 pwm=(a.astype(np.int32)+32768)>>6;decoded.append(((pwm-512)*64).astype('<i2'));packet_count+=1
audio=np.concatenate(decoded)
with wave.open(str(out/'audio-transferred.wav'),'wb') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(32000);w.writeframes(audio.tobytes())
result={'frames':len(original),'source_fps':30,'duration_seconds':30,'color_ms_mean':float(np.mean(timings)),'color_ms_p95':float(np.percentile(timings,95)),'color_ms_max':max(timings),'frames_over_33_33ms':sum(t>1000/30 for t in timings),'audio_packets':packet_count,'audio_samples':len(audio),'audio_rate':32000,'pwm_bits':10}
(out/'conversion-results.json').write_text(json.dumps(result,indent=2))
print(result,flush=True)
