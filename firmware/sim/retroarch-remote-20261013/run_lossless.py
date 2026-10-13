from pathlib import Path
import os,shutil,subprocess,json
import numpy as np
from PIL import Image
here=Path(__file__).resolve().parent
out=here/'latest-preview'
qa=Path(os.environ['TEMP'])/'fc-ra-remote-latest-20261013'
core=here.parent/'mmc3-sequence-20261013/nestopia-build/nestopia_fc_counter.dll'
shutil.copyfile(core,qa/'nestopia_lossless_validation.dll')
results={}
for expected in sorted(out.glob('*-lossless-expected.png')):
 name=expected.name.removesuffix('-expected.png')
 for ext in ('nes','srm','fb'):shutil.copyfile(out/f'{name}.{ext}',qa/f'{name}.{ext}')
 # Set framebuffer path only in this child process; don't alter the shell environment.
 env=os.environ.copy();env['FC_REMOTE_FB']=str(qa/f'{name}.fb')
 cmd=['C:/RetroArch-Win64/retroarch.exe','--log-file',str(qa/f'{name}-log.txt'),'-c',str(qa/'qa.cfg'),'-L',str(qa/'nestopia_lossless_validation.dll'),'--sram-mode=load-nosave','--max-frames=120','--max-frames-ss','--max-frames-ss-path='+str(qa/f'{name}-retroarch.png'),str(qa/f'{name}.nes')]
 subprocess.run(cmd,env=env,check=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 shot=Image.open(qa/f'{name}-retroarch.png').convert('RGB')
 shot.save(out/f'{name}-retroarch.png')
 shot.resize((768,720),Image.Resampling.NEAREST).save(out/f'{name}-retroarch-3x.png')
 diff=np.any(np.asarray(shot)!=np.asarray(Image.open(expected).convert('RGB')),axis=2)
 diff[110:126,120:136]=False
 results[name]={'background_pixel_errors':int(diff.sum())}
 print(name,results[name],flush=True)
(out/'lossless-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
assert all(r['background_pixel_errors']==0 for r in results.values())
