"""Actual audio.c ring logic; only the DMA consumer is simulated."""
import ctypes as C
from pathlib import Path
import subprocess,sys
here=Path(__file__).resolve().parents[1]/'sim/retroarch-remote-20261013'
subprocess.run([sys.executable,str(here/'build_audio_ring_host.py')],check=True)
d=C.CDLL(str(here/'audio-ring-host.dll'))
d.audio_local_space.restype=C.c_uint
d.audio_local_write.argtypes=[C.POINTER(C.c_int16),C.c_uint]
d.host_advance.argtypes=[C.c_uint,C.POINTER(C.c_uint16)]
d.host_lead.restype=C.c_uint
d.host_reset()
assert d.audio_local_space()==64 # 2ms initial lead; 4ms maximum total
samples=(C.c_int16*64)(*([6400]*64));d.audio_local_write(samples,64)
assert d.host_lead()==128 and not d.audio_local_space()
out=(C.c_uint16*128)();d.host_advance(128,out)
assert list(out[:64])==[512]*64 and list(out[64:])==[612]*64
assert d.audio_local_space()==64 # after underrun, short lead again
for _ in range(1000):
 d.audio_local_write(samples,64)
 buf=(C.c_uint16*32)();d.host_advance(32,buf);d.audio_poll()
 assert d.host_lead()<=128
print('PASS: actual local audio ring: 2ms lead, 4ms bound, sample values and underrun recovery')
