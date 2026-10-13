from pathlib import Path
import subprocess,concurrent.futures,re,time
repo=Path('FC-MAGICON/ref/nestopia-timing/nestopia-master').resolve();out=Path('FC-MAGICON/firmware/sim/mmc3-sequence-20261013/nestopia-build').resolve();out.mkdir(exist_ok=True)
zig='C:/Users/Yugo/pico/zig/zig-x86_64-windows-0.16.0/zig.exe'
make=(repo/'libretro/Makefile.common').read_text();sources=[]
for kind,path in re.findall(r'SOURCES_(CXX|C)\s*\+=\s*(.+)',make):
 path=path.strip().replace('$(CORE_DIR)',str(repo)).replace('$(LIBRETRO_COMM_DIR)',str(repo/'libretro/libretro-common'))
 sources.append((kind,Path(path)))
base=['-O1','-D__LIBRETRO__','-DNST_NO_ZLIB','-DNDEBUG','-D_CRT_SECURE_NO_DEPRECATE','-I'+str(repo),'-I'+str(repo/'libretro'),'-I'+str(repo/'libretro/libretro-common/include')]
def build(entry):
 i,(kind,p)=entry;obj=out/f'{i:04}.o'
 if obj.exists() and obj.stat().st_mtime>=p.stat().st_mtime:return obj
 cmd=[zig,'c++' if kind=='CXX' else 'cc','-c']+base+(['-std=c++98','-fno-rtti'] if kind=='CXX' else ['-std=c99'])+[str(p),'-o',str(obj)]
 r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
 if r.returncode:raise RuntimeError(str(p)+'\n'+r.stderr[-5000:])
 return obj
objs=[];start=time.time();print('Building',len(sources),'source files',flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for n,obj in enumerate(pool.map(build,enumerate(sources)),1):
  objs.append(obj)
  if n%40==0:print('Compiled',n,'elapsed',round(time.time()-start),flush=True)
bridge=out/'bridge.o';r=subprocess.run([zig,'cc','-c','-O2','-std=gnu11','-I'+str(Path('FC-MAGICON/firmware/sim').resolve()),'-I'+str(Path('FC-MAGICON/firmware/chr_test').resolve()),str(Path('FC-MAGICON/firmware/sim/mmc3-sequence-20261013/nestopia_counter_bridge.c').resolve()),'-o',str(bridge)],capture_output=True,text=True,encoding='utf-8',errors='replace')
if r.returncode:raise RuntimeError(r.stderr)
objs.append(bridge)
response=out/'link.rsp';response.write_text('\n'.join('"'+str(p)+'"' for p in objs),encoding='utf-8')
r=subprocess.run([zig,'c++','-shared','@'+str(response),'-o',str(out/'nestopia_fc_counter.dll'),'-lwinmm','-lole32','-lshell32','-lshlwapi','-lws2_32','-ladvapi32'],capture_output=True,text=True)
if r.returncode:raise RuntimeError(r.stderr[-6000:])
print('DONE',out/'nestopia_fc_counter.dll','elapsed',round(time.time()-start),flush=True)
