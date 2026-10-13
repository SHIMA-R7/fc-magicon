"""Install a verified gh CLI in TEMP; prepare and publish an explicit source snapshot."""
from pathlib import Path
import urllib.request,json,hashlib,zipfile,os,subprocess,sys,shutil,ast,fnmatch,re
ROOT=Path(__file__).resolve().parent
TEMP=Path(os.environ['TEMP']);TOOLS=TEMP/'fc-gh-cli-20261013';TOOLS.mkdir(exist_ok=True)
def fetch(url):
 return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'FC-MAGICON-checkpoint'}),timeout=30).read()
if '--install-gh' in sys.argv:
 release=json.loads(fetch('https://api.github.com/repos/cli/cli/releases/latest'))
 assets=release['assets'];archive=next(a for a in assets if a['name'].endswith('windows_amd64.zip'))
 checksum=next(a for a in assets if a['name'].endswith('checksums.txt'))
 payload=fetch(archive['browser_download_url']);lines=fetch(checksum['browser_download_url']).decode().splitlines()
 expected=next(line.split()[0] for line in lines if line.split()[-1]==archive['name'])
 assert hashlib.sha256(payload).hexdigest()==expected,'official checksum mismatch'
 path=TOOLS/archive['name'];path.write_bytes(payload)
 with zipfile.ZipFile(path) as z:
  for name in z.namelist():
   if name.endswith('/gh.exe') or name=='bin/gh.exe':
    (TOOLS/'gh.exe').write_bytes(z.read(name));break
 assert (TOOLS/'gh.exe').exists()
 print('Verified GitHub CLI',release['tag_name'],flush=True)
 subprocess.run([str(TOOLS/'gh.exe'),'auth','status'],check=True)
if '--prepare' in sys.argv or '--push' in sys.argv:
 staging=TEMP/'fc-magicon-publish-20261013'
 git='C:/Users/Yugo/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
 assert (staging/'.git').is_dir()
 assignments={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse((ROOT/'upload_repo.py').read_text(encoding='utf-8')).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('INCLUDE','EXCLUDE')}
 patterns=assignments['INCLUDE']+['.gitignore','tools_publish_checkpoint.py','docs/*.md','firmware/power_guard.h','firmware/build_protected.ps1','firmware/tests/*.c','firmware/tests/*.py','firmware/tests/*.h','firmware/sim/THIRD_PARTY.md','firmware/sim/mmc3-sequence-20261013/*.py','firmware/sim/mmc3-sequence-20261013/*.c','firmware/sim/mmc3-sequence-20261013/*.patch','firmware/sim/mmc3-sequence-20261013/COPYING','firmware/sim/mmc3-sequence-20261013/upstream.json','firmware/sim/retroarch-remote-20261013/*.py','firmware/sim/retroarch-remote-20261013/*.ps1','firmware/out-direct-pio-diagnostic/magicon-mmc3-reload-generation.uf2','firmware/out-direct-pio-diagnostic/magicon-remote-full-smallcursor-chunked.uf2']
 excluded=assignments['EXCLUDE']+['ref/*','**/__pycache__/*','**/wifi_secrets.h','firmware/magicon/static_image.h']
 files=sorted({p for pattern in patterns for p in ROOT.glob(pattern) if p.is_file()})
 selected=[]
 for p in files:
  rel=p.relative_to(ROOT).as_posix()
  if any(fnmatch.fnmatch(rel,pattern) for pattern in excluded):continue
  if p.suffix in ('.nes','.srm','.nsf','.mp4','.wav','.dll','.exe','.npz','.rgb'):continue
  if p.suffix in ('.c','.h','.py','.ps1','.md','.txt','.json','.ino'):
   body=p.read_text(encoding='utf-8',errors='replace')
   if re.search(r'gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',body):
    raise RuntimeError('credential-like content in '+rel)
  target=staging/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target);selected.append(rel)
 # Source snapshot manifest contains paths and digests, never private input content.
 manifest={rel:hashlib.sha256((staging/rel).read_bytes()).hexdigest() for rel in selected}
 (staging/'checkpoint-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 subprocess.run([git,'-C',str(staging),'add','-f','--']+selected+['checkpoint-manifest.json'],check=True)
 subprocess.run([git,'-C',str(staging),'diff','--cached','--stat'],check=True)
 print('Prepared explicit checkpoint:',len(selected),'files',flush=True)
 if '--push' in sys.argv:
  subprocess.run([git,'-C',str(staging),'-c','user.name=SHIMA-R7','-c','user.email=SHIMA-R7@users.noreply.github.com','commit','-m','Record real-hardware progress and offline MMC3/video/audio validation'],check=True)
  helper='!"'+str(TOOLS/'gh.exe').replace('\\','/')+'" auth git-credential'
  subprocess.run([git,'-C',str(staging),'-c','credential.helper=','-c','credential.helper='+helper,'push','origin','HEAD:main'],check=True)
  head=subprocess.check_output([git,'-C',str(staging),'rev-parse','HEAD'],text=True).strip()
  (ROOT/'docs/github_checkpoint_20261013.json').write_text(json.dumps({'repository':'https://github.com/SHIMA-R7/fc-magicon','commit':head,'source_files':len(selected)},indent=2))
  print('Published https://github.com/SHIMA-R7/fc-magicon/commit/'+head,flush=True)
