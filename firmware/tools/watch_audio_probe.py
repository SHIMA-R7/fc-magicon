"""Wait for running FC, send an audio-only probe, save diagnostic lines."""
from pathlib import Path
import json,re,struct,time
import numpy as np
from remote_pc import Port,IoThread
out=Path(__file__).resolve().parents[1]/'sim/audio-hardware-20261014'
out.mkdir(parents=True,exist_ok=True)
for attempt in range(30):
    try:port=Port('COM11');break
    except OSError:
        if attempt==29:raise
        time.sleep(1)
io=IoThread(port,chunked=True)
buffer=bytearray();lines=[];previous=None
def poll():
    global buffer
    buffer+=io.read()
    for match in re.finditer(rb'AUDIO: [^\r\n]*[\r\n]',buffer):
        line=match.group().decode('ascii',errors='replace').strip()
        print(line,flush=True);lines.append(line)
    counters=[buffer[p+19] for p in range(max(0,len(buffer)-19)) if buffer[p:p+4]==b'FCIN']
    buffer=buffer[-19:]
    return counters
print('READY: awaiting FC power and advancing driver counter',flush=True)
deadline=time.monotonic()+180
while time.monotonic()<deadline:
    counters=poll()
    if counters:
        if previous is not None and any(c!=previous for c in counters):break
        previous=counters[-1]
    time.sleep(.01)
else:raise TimeoutError('No advancing FC counter')
print('PROBE: 440Hz for 5 seconds; video not sent',flush=True)
start=time.monotonic()
for k in range(250):
    samples=(12000*np.sin(2*np.pi*440*(np.arange(640)+k*640)/32000)).astype('<i2')
    io.send_audio(b'FCAU'+struct.pack('<BH',0,640)+samples.tobytes())
    poll()
    remaining=start+(k+1)*.02-time.monotonic()
    if remaining>0:time.sleep(remaining)
io.send_audio(b'FCAU'+struct.pack('<BH',0,640)+bytes(1280))
end=time.monotonic()+3
while time.monotonic()<end:poll();time.sleep(.01)
(out/'audio-probe.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('DONE: diagnostic log saved',flush=True)
