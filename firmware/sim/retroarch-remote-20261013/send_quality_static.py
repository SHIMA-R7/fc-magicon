from pathlib import Path
import sys,time
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[1]/'tools'))
from remote_pc import Port,IoThread
packet=b'FCFR'+(here/'youtube-U6Wlb18KLrI/quality-frame-150.bin').read_bytes()
io=IoThread(Port('COM11'),chunked=True)
end=time.monotonic()+8;offered=0;received=0
while time.monotonic()<end:
    if io.ready():io.send(packet);offered+=1
    received+=len(io.read());time.sleep(.2)
time.sleep(1);received+=len(io.read())
print({'offered_frames':offered,'received_bytes':received,'display_acknowledged':False})
