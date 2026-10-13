"""Deterministic input runner for RetroArch's installed Nestopia libretro core."""
import ctypes as C,sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
core,rom,out=sys.argv[1:4];frames=int(sys.argv[4]);events=json.loads(Path(sys.argv[5]).read_text())
out=Path(out);out.mkdir(parents=True,exist_ok=True)
lib=C.CDLL(core)
ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p);VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16);BATCH=C.CFUNCTYPE(C.c_size_t,C.c_void_p,C.c_size_t)
POLL=C.CFUNCTYPE(None);INPUT=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
LOG=C.CFUNCTYPE(None,C.c_int,C.c_char_p)
class Variable(C.Structure):_fields_=[('key',C.c_char_p),('value',C.c_char_p)]
class Game(C.Structure):_fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]
options={b'nestopia_blargg_ntsc_filter':b'disabled',b'nestopia_palette':b'custom',b'nestopia_overscan_v_top':b'0',b'nestopia_overscan_v_bottom':b'0',b'nestopia_overscan_h_left':b'0',b'nestopia_overscan_h_right':b'0'}
directory=str(Path(core).parent).encode();pixel_format=1;current=0;hashes=[];latest=None
@LOG
def log(level,msg):pass
@ENV
def env(cmd,data):
 global pixel_format
 cmd &= 0xffff
 if cmd in (9,31):C.cast(data,C.POINTER(C.c_char_p))[0]=directory;return True
 if cmd==10:pixel_format=C.cast(data,C.POINTER(C.c_int))[0];return pixel_format==1
 if cmd==15:
  v=C.cast(data,C.POINTER(Variable)).contents;v.value=options.get(v.key);return v.value is not None
 if cmd==16:
  p=C.cast(data,C.POINTER(Variable));i=0
  while p[i].key:
   if p[i].key not in options:options[p[i].key]=p[i].value.split(b'; ',1)[-1].split(b'|')[0]
   i+=1
  return True
 if cmd==17:C.cast(data,C.POINTER(C.c_bool))[0]=False;return True
 if cmd==27:C.cast(data,C.POINTER(C.c_void_p))[0]=C.cast(log,C.c_void_p).value;return True
 if cmd==52:C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
 if cmd==3:C.cast(data,C.POINTER(C.c_bool))[0]=True;return True
 if cmd in (1,6,11,18,35,36,51):return True
 return False
@VIDEO
def video(data,w,h,pitch):
 global latest
 if not data:return
 assert pixel_format==1
 a=np.frombuffer(C.string_at(data,pitch*h),dtype=np.uint8).reshape(h,pitch)[:,:w*4].reshape(h,w,4)
 latest=a[:,:,[2,1,0]].copy()
@AUDIO
def audio(l,r):pass
@BATCH
def batch(data,n):return n
@POLL
def poll():pass
input_nonzero=0
bits={'B':0,'S':2,'T':3,'U':4,'D':5,'L':6,'R':7,'A':8}
@INPUT
def inp(port,device,index,key):
 global input_nonzero
 if port:return 0
 mask=0
 for e in events:
  if e['frame']<=current<e['frame']+e['length']:
   for b in e['buttons']:mask |= 1<<bits[b]
 value=C.c_int16(mask).value if key==256 else int(bool(mask&(1<<key)))
 if value:input_nonzero+=1
 return value
for name,cb in [('environment',env),('video_refresh',video),('audio_sample',audio),('audio_sample_batch',batch),('input_poll',poll),('input_state',inp)]:
 f=getattr(lib,'retro_set_'+name);f.argtypes=[type(cb)];f(cb)
lib.retro_init();lib.retro_load_game.argtypes=[C.POINTER(Game)];lib.retro_load_game.restype=C.c_bool
content=Path(rom).read_bytes();buf=C.create_string_buffer(content);game=Game(str(Path(rom)).encode(),C.cast(buf,C.c_void_p),len(content),None)
assert lib.retro_load_game(C.byref(game)),'load failed'
lib.retro_set_controller_port_device(0,257)
stream=None;rendered=[];stream_index=-1;stream_results=[]
if len(sys.argv)>6 and sys.argv[6]=='--remote-sequence':
 with np.load(sys.argv[7]) as archive:stream={key:archive[key] for key in archive.files}
 assert hasattr(lib,'fc_remote_frame')
 lib.fc_remote_frame.argtypes=[C.c_void_p]
 lib.retro_get_memory_data.argtypes=[C.c_uint];lib.retro_get_memory_data.restype=C.c_void_p
 lib.retro_get_memory_size.argtypes=[C.c_uint];lib.retro_get_memory_size.restype=C.c_size_t
 ram=lib.retro_get_memory_data(0);assert ram and lib.retro_get_memory_size(0)>=8192
 C.memmove(ram,Path(rom).with_suffix('.srm').read_bytes(),8192)
 lib.fc_remote_frame(stream['fb'][0].ctypes.data)
for current in range(1,frames+1):
 if stream is not None and current>=120:
  next_index=min((current-120)//2,len(stream['fb'])-1)
  if next_index!=stream_index:
   stream_index=next_index
   lib.fc_remote_frame(stream['fb'][stream_index].ctypes.data)
   C.memmove(ram+0x400,stream['pal'][stream_index].ctypes.data,32)
   C.memmove(ram+0x420,stream['attr'][stream_index].ctypes.data,64)
 lib.retro_run()
 assert latest is not None
 hashes.append(f'{current} {hashlib.sha256(latest.tobytes()).hexdigest()}')
 if current%60==0:Image.fromarray(latest).save(out/f'frame{current:05}.png')
 if stream is not None and current>=120:
  error=int(np.any(latest!=stream['expected'][stream_index],axis=2).sum())
  stream_results.append({'emulator_frame':current,'source_frame':stream_index,'pixel_errors':error})
  if (current-120)%2==1:rendered.append(latest.copy())
if stream is not None:
 np.savez_compressed(out/'rendered.npz',rgb=np.array(rendered))
 (out/'stream-results.json').write_text(json.dumps(stream_results,indent=2))
if hasattr(lib,'fc_chr_read_errors'):
 lib.fc_chr_read_errors.restype=C.c_ulonglong
 (out/'chr-read-errors.json').write_text(json.dumps({'reads_returning_stale_bytes':int(lib.fc_chr_read_errors())}))
lib.retro_unload_game();lib.retro_deinit()
(out/'hashes.txt').write_text('\n'.join(hashes))
print('Nestopia deterministic input frames:',frames,'nonzero input reads:',input_nonzero)

