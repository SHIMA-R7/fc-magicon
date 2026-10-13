"""Actual PC sender + actual C audio ring, with an assumed-bandwidth fake link.
No hardware, no desktop capture, no WASAPI capture. Frame parsing is a host model.
"""
from pathlib import Path
import ctypes as C,json,sys,time,threading,struct,wave
import numpy as np
from PIL import Image
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
from remote_pc import IoThread,frame_packet
from nesframe import encode
from pcaudio import packets,AdpcmEncoder,FMT_PCM16,RATE
out=here/'video-load'
with np.load(out/'sequence.npz') as z:source=z['original'].copy()
with wave.open(str(out/'test-audio.wav'),'rb') as w:tone=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32767
ring=C.CDLL(str(here/'audio-ring-host.dll'))
ring.audio_push.argtypes=[C.c_uint8,C.c_uint16,C.c_void_p]
ring.host_advance.argtypes=[C.c_uint,C.c_void_p]
ring.host_puts.restype=ring.host_resets.restype=C.c_uint64

class Link:
 def __init__(self,bandwidth):
  self.bandwidth=bandwidth;self.start=time.perf_counter();self.samples=0;self.pwm=[]
  self.bytes=0;self.buf=bytearray();self.frames=[];self.audio_packets=0;self.audio_samples=0
  self.audio_gaps=[];self.last_audio=None;self.closed=False;self.chunk_frame=bytearray()
  ring.host_reset()
 def clock(self):
  target=int((time.perf_counter()-self.start)*RATE)
  while target>self.samples:
   n=min(320,target-self.samples);a=np.empty(n,dtype=np.uint16)
   ring.host_advance(n,a.ctypes.data);ring.audio_poll();self.pwm.append(a);self.samples+=n
 def write(self,data):
  if self.closed:raise OSError('test link closed')
  for k in range(0,len(data),1024):
   part=data[k:k+1024];time.sleep(len(part)/self.bandwidth)
   self.clock();self.bytes+=len(part);self.buf.extend(part)
   while len(self.buf)>=4:
    tag=self.buf[:4]
    if tag==b'FCFR':size=15463
    elif tag==b'FCCH':
     if len(self.buf)<8:break
     offset,length=struct.unpack_from('<HH',self.buf,4)
     assert 0<length<=1024 and offset+length<=15459
     size=8+length
    elif tag==b'FCAU':
     if len(self.buf)<7:break
     fmt,n=struct.unpack_from('<BH',self.buf,4)
     assert fmt==FMT_PCM16 and 0<n<=1024
     size=7+n*2
    else:raise AssertionError('packet boundary corrupted')
    if len(self.buf)<size:break
    packet=bytes(self.buf[:size]);del self.buf[:size]
    if tag==b'FCCH':
     if offset==0:self.chunk_frame.clear()
     assert offset==len(self.chunk_frame),'chunk ordering corrupted'
     self.chunk_frame.extend(packet[8:])
     if len(self.chunk_frame)<15459:continue
     packet=b'FCFR'+bytes(self.chunk_frame);tag=b'FCFR'
    if tag==b'FCFR':
     # Assume atomic display exchange at the next 60Hz frame boundary.
     elapsed=time.perf_counter()-self.start
     time.sleep(max(0,(int(elapsed*60)+1)/60-elapsed))
     self.clock();self.frames.append({'time':time.perf_counter()-self.start,'packet':packet[4:]})
    else:
     p=C.create_string_buffer(packet[7:]);ring.audio_push(fmt,n,p)
     self.audio_samples+=n;self.audio_packets+=1
     now=time.perf_counter()-self.start
     if self.last_audio is not None:self.audio_gaps.append(now-self.last_audio)
     self.last_audio=now
 def read(self):
  if self.closed:raise OSError('test link closed')
  self.clock();return b''

results=[];chunked='--chunked' in sys.argv
configs=[(650000,30),(120000,30),(120000,3)] if chunked else [(650000,30),(300000,15),(120000,30)]
for bandwidth,fps in configs:
 link=Link(bandwidth);sender=IoThread(link,chunked=chunked);stop=threading.Event()
 def audio_producer():
  enc=AdpcmEncoder();i=0
  while i<300 and not stop.is_set():
   until=link.start+i*0.02;stop.wait(max(0,until-time.perf_counter()))
   if stop.is_set():break
   for pkt in packets(tone[i*640:(i+1)*640],FMT_PCM16,enc):sender.send_audio(pkt)
   i+=1
 thread=threading.Thread(target=audio_producer);thread.start()
 converted=0;prev=None;next_t=link.start
 while time.perf_counter()-link.start<6:
  now=time.perf_counter()
  if now>=next_t and sender.ready():
   i=min(179,int((now-link.start)*30))
   prev=encode(Image.fromarray(source[i]),'color',prev=prev,iters=2 if prev else 4)
   sender.send(frame_packet(prev,(0,0,False)));converted+=1;next_t=now+1/fps
  else:time.sleep(0.001)
 stop.set();thread.join()
 # Let queued audio finish; close by an explicit fake-port error, never touch real ports.
 until=time.perf_counter()+2
 while time.perf_counter()<until:
  with sender.lock:queued=bool(sender.audio) or sender.pending is not None
  if not queued:time.sleep(0.25);break
  time.sleep(0.01)
 link.closed=True;sender.wake.set();sender.join(2)
 pwm=np.concatenate(link.pwm);pcm=((pwm.astype(np.int32)-512)*64).astype('<i2')
 name=f'{bandwidth}Bps-{fps}fps'+('-chunked' if chunked else '')
 np.savez_compressed(out/f'link-{name}.npz',times=np.array([f['time'] for f in link.frames]),packets=np.array([np.frombuffer(f['packet'],dtype=np.uint8) for f in link.frames]))
 with wave.open(str(out/f'audio-{name}.wav'),'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(pcm.tobytes())
 # Long runs of the exact silence PWM level indicate gaps, excluding startup/tail.
 core=pwm[min(len(pwm),6400):min(len(pwm),6*RATE)]
 silence=core==512;edges=np.diff(np.r_[False,silence,False].astype(np.int8));runs=np.flatnonzero(edges==-1)-np.flatnonzero(edges==1)
 long=runs[runs>=320]
 result={'chunked':chunked,'assumed_bytes_per_second':bandwidth,'requested_fps':fps,'converted_frames':converted,'received_frames':len(link.frames),'frame_gaps_ms_max':max(np.diff([f['time'] for f in link.frames]))*1000 if len(link.frames)>1 else None,'received_audio_packets':link.audio_packets,'received_audio_samples':link.audio_samples,'ring_written_samples':int(ring.host_puts()),'ring_restarts':int(ring.host_resets()),'ring_discarded_samples':link.audio_samples-int(ring.host_puts()),'audio_arrival_gap_ms_max':max(link.audio_gaps)*1000 if link.audio_gaps else 0,'silence_runs_at_least_10ms':len(long),'silence_ms_max':int(max(long,default=0))*1000/RATE,'bytes_received':link.bytes}
 results.append(result);print(json.dumps(result),flush=True)
 assert not link.buf,'partial packet left behind'
(out/('transport-chunked-results.json' if chunked else 'transport-results.json')).write_text(json.dumps(results,indent=2))
