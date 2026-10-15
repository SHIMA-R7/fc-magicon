"""Copy an explicit, media-free source checkpoint into an existing Git checkout.

Usage: python prepare_checkpoint.py PATH_TO_CHECKOUT
Does not commit, push, remove files, or modify the connected cartridge.
"""
import ast
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

root = Path(__file__).resolve().parent
stage = Path(sys.argv[1]).resolve()
assert (stage / '.git').is_dir(), 'An existing Git checkout is required'
values = {}
for node in ast.parse((root / 'upload_repo.py').read_text(encoding='utf-8')).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in ('INCLUDE', 'EXCLUDE'):
            values[node.targets[0].id] = ast.literal_eval(node.value)
patterns = values['INCLUDE'] + [
    '.gitignore', '.gitattributes', 'prepare_checkpoint.py', 'tools_publish_checkpoint.py',
    'docs/*.md', 'firmware/power_guard.h', 'firmware/build_protected.ps1',
    'firmware/tests/*.py', 'firmware/tests/*.c', 'firmware/tests/*.h',
    'firmware/standalone_video/**/*.c', 'firmware/standalone_video/**/*.h',
    'firmware/standalone_video/**/*.pio', 'firmware/standalone_video/*.py',
    'firmware/standalone_video/*.ps1', 'firmware/standalone_video/CMakeLists.txt',
    'firmware/sim/THIRD_PARTY.md',
]
for folder in ('mmc3-sequence-20261013', 'retroarch-remote-20261013',
               'mmc3-fast-20261013', 'mmc3-native-20261013', 'mmc3-retroarch-20261013',
               'audio-hardware-20261014', 'startup-20261013'):
    for extension in ('py', 'c', 'h', 'ps1', 'patch'):
        patterns.append(f'firmware/sim/{folder}/*.{extension}')
    patterns += [f'firmware/sim/{folder}/COPYING', f'firmware/sim/{folder}/upstream.json']
for prefix in ('nt-stress-', 'cpu-window-hardware-', 'pin-audit-hardware-',
               'palette-nt-log-hardware-', 'palette-nt-log-original-outlet-'):
    for extension in ('json', 'log'):
        patterns.append(f'firmware/sim/standalone-video-20261014/{prefix}*.{extension}')
excluded = values['EXCLUDE'] + ['ref/*', '**/__pycache__/*', '**/wifi_secrets.h',
                              'firmware/magicon/static_image.h']
blocked_suffixes = {'.nes', '.nsf', '.srm', '.mp4', '.wav', '.mp3', '.dll', '.exe',
                    '.npz', '.rgb', '.uf2', '.fcpv', '.bin'}
selected = []
for path in sorted({p for pattern in patterns for p in root.glob(pattern) if p.is_file()}):
    relative = path.relative_to(root).as_posix()
    if path.suffix.lower() in blocked_suffixes:
        continue
    if any(fnmatch.fnmatch(relative, pattern) for pattern in excluded):
        continue
    if path.suffix.lower() in {'.c', '.h', '.py', '.ps1', '.md', '.txt', '.json', '.ino', '.log'}:
        body = path.read_text(encoding='utf-8', errors='replace')
        if re.search(r'gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', body):
            raise RuntimeError('Credential-like content in ' + relative)
    target = stage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    selected.append(relative)
manifest = {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in selected}
(stage / 'checkpoint-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'files': len(selected), 'bytes': sum((stage / p).stat().st_size for p in selected),
                  'checkout': str(stage)}, ensure_ascii=False))
