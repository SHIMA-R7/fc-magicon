"""Replay the saved 0..30s PV conversion through the actual USB receiver.

Preconverted source frames, not emulator-rendered screenshots. Report successful
host writes separately from display FPS (which is not measured here).
"""
import argparse,json,struct,time,wave
from pathlib import Path
import numpy as np
from remote_pc import Port,IoThread

def main():
    ap=argparse.ArgumentParser();ap.add_argument('folder',type=Path);ap.add_argument('--port',default='COM11')
    ap.add_argument('--fps',type=float,default=30);ap.add_argument('--source-fps',type=float,default=30)
    ap.add_argument('--audio-gain',type=float,default=1);args=ap.parse_args()
    if not np.isfinite(args.audio_gain) or args.audio_gain<0:ap.error('audio gain must be finite and nonnegative')
    with np.load(args.folder/'sequence.npz') as z:
        frames={k:z[k] for k in ('fb','pal','attr')}
    with wave.open(str(args.folder/'audio-32k.wav'),'rb') as w:
        assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,32000)
        audio=w.readframes(w.getnframes())
    samples=np.frombuffer(audio,dtype='<i2').astype(np.float64)*args.audio_gain
    clipped_samples=int(np.count_nonzero((samples>32767)|(samples<-32768)))
    audio=np.clip(np.rint(samples),-32768,32767).astype('<i2').tobytes()
    print(f'AUDIO gain={args.audio_gain:g}, peak={int(np.max(np.abs(samples))):d}, clipped_samples={clipped_samples}',flush=True)
    class MeteredPort(Port):
        completed=0;audio_packets=0;written=0
        def write(self,data):
            super().write(data);self.written+=len(data)
            if data[:4]==b'FCCH' and int.from_bytes(data[4:6],'little')==15360:self.completed+=1
            self.audio_packets+=data.count(b'FCAU') if data[:4]==b'FCAU' else 0
    raw=MeteredPort(args.port);io=IoThread(raw,chunked=True)
    diagnostic_buffer=bytearray();diagnostics=[]
    def receive():
        data=io.read();diagnostic_buffer.extend(data)
        while b'\n' in diagnostic_buffer:
            line,_,tail=diagnostic_buffer.partition(b'\n');diagnostic_buffer[:]=tail
            pos=line.find(b'AUDIO:')
            if pos>=0:
                text=line[pos:].decode('ascii',errors='replace').strip()
                diagnostics.append(text);print(text,flush=True)
                (args.folder/'hardware-audio-log.txt').write_text('\n'.join(diagnostics)+'\n',encoding='utf-8')
        if len(diagnostic_buffer)>8192:del diagnostic_buffer[:-4096]
        return data
    print('READY: waiting for FC remote driver frame counter; 30s clip starts automatically',flush=True)
    rx=bytearray();previous=None;deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        rx+=receive()
        while True:
            pos=rx.find(b'FCIN')
            if pos<0:
                if len(rx)>10000:del rx[:-3]
                break
            if len(rx)<pos+20:break
            counter=rx[pos+19];del rx[:pos+20]
            if previous is not None and counter!=previous:break
            previous=counter
        else:continue
        if previous is not None and 'counter' in locals() and counter!=previous:break
        time.sleep(.005)
    else:raise TimeoutError('FC driver did not start')
    print('PLAYING: saved Blue Archive 7th PV, first 30s, color + PCM16',flush=True)
    start=time.monotonic();next_audio=0;next_frame=0;offered=0
    while time.monotonic()-start<30:
        elapsed=time.monotonic()-start
        # 20ms PCM chunks. Catch up to source time without accumulating old video frames.
        while next_audio*0.02<=elapsed and next_audio*1280<len(audio):
            payload=audio[next_audio*1280:(next_audio+1)*1280]
            io.send_audio(b'FCAU'+struct.pack('<BH',0,len(payload)//2)+payload);next_audio+=1
        if elapsed>=next_frame/args.fps:
            i=min(int(elapsed*args.source_fps),len(frames['fb'])-1)
            pkt=b'FCFR'+frames['fb'][i].tobytes()+frames['pal'][i].tobytes()+frames['attr'][i].tobytes()+bytes(3)
            io.send(pkt);offered+=1;next_frame=int(elapsed*args.fps)+1
        receive();time.sleep(.001)
    # Silence the software DAC after this clip (the receiver also clears consumed samples).
    io.send_audio(b'FCAU'+struct.pack('<BH',0,640)+bytes(1280));time.sleep(.5);receive()
    result={'duration_s':30,'offered_frames':offered,'host_completed_frame_writes':raw.completed,
            'host_completed_frames_per_s':raw.completed/30,'host_written_bytes':raw.written,
            'display_fps_measured':False,'source':'U6Wlb18KLrI 0..30s', 'source_conversion_fps':args.source_fps,
            'audio_gain':args.audio_gain,'audio_clipped_samples':clipped_samples}
    (args.folder/'hardware-replay-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
