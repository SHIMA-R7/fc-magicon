"""Five seconds of moderate 440Hz PCM16, without video traffic."""
import argparse,time,struct
import numpy as np
from remote_pc import Port,IoThread
ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=float,default=5)
ap.add_argument('--amplitude',type=int,default=6000)
args=ap.parse_args()
if not 0<=args.amplitude<=30000:ap.error('amplitude must be 0..30000')
io=IoThread(Port('COM11'),chunked=True)
start=time.monotonic()
for k in range(round(args.seconds*50)):
    samples=(args.amplitude*np.sin(2*np.pi*440*(np.arange(640)+k*640)/32000)).astype('<i2')
    io.send_audio(b'FCAU'+struct.pack('<BH',0,640)+samples.tobytes())
    io.read()
    remaining=start+(k+1)*.02-time.monotonic()
    if remaining>0:time.sleep(remaining)
io.send_audio(b'FCAU'+struct.pack('<BH',0,640)+bytes(1280))
time.sleep(.5);io.read()
print(f'Audio-only probe sent: 440Hz, {args.seconds:g}s; no device audio ACK')
