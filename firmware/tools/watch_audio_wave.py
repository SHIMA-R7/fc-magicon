"""Record the one-shot passive GPIO44 probe after FC power-on."""
from pathlib import Path
import time,re
from remote_pc import Port
out=Path(__file__).resolve().parents[1]/'sim/audio-hardware-20261014'
out.mkdir(parents=True,exist_ok=True)
for attempt in range(30):
    try:port=Port('COM11');break
    except OSError:
        if attempt==29:raise
        time.sleep(1)
buffer=bytearray();lines=[]
deadline=time.monotonic()+300
print('READY: waiting for WAVE capture after FC power-on',flush=True)
while time.monotonic()<deadline:
    buffer+=port.read()
    while b'\n' in buffer:
        line,_,buffer=buffer.partition(b'\n')
        pos=line.find(b'WAVE ')
        if pos>=0:
            text=line[pos:].decode('ascii',errors='replace').strip();lines.append(text)
            print(text if 'duty_per_ms' not in text else 'WAVE duty data saved',flush=True)
            (out/'gpio44-wave.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
            if 'duty_per_ms' in text:raise SystemExit(0)
    if len(buffer)>8192:buffer=buffer[-4096:]
    time.sleep(.005)
raise TimeoutError('No WAVE report within 300s')
