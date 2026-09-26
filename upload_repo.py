"""FC-MAGICON を GitHub(SHIMA-R7/fc-magicon)へ 1 コミットで上げる。git 本体は使わず gh CLI の Git Data API だけ使う。
    python upload_repo.py "コミットメッセージ"
公開するファイルは INCLUDE / EXCLUDE で決める(第三者のデータ ref/、途中のバックアップ、ログ、古いガーバーは上げない)。
"""
import base64
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = "SHIMA-R7/fc-magicon"
ROOT = Path(__file__).parent
MESSAGE = sys.argv[1] if len(sys.argv) > 1 else "Update FC-MAGICON"

INCLUDE = [
    "README.md", "LICENSE", "upload_repo.py",
    "docs/build_spec.py", "docs/hardware_spec_body.md", "docs/hardware_spec.md", "docs/hardware_spec.pdf", "docs/_tables.md",
    "kicad/*.py", "kicad/*.ps1", "kicad/bom.csv", "kicad/fp-lib-table", "kicad/sym-lib-table",
    "kicad/FC-MAGICON.kicad_pro", "kicad/FC-MAGICON.kicad_sch", "kicad/FC-MAGICON.kicad_sym", "kicad/FC-MAGICON.kicad_pcb",
    "kicad/FC-MAGICON.net", "kicad/FC-MAGICON.pdf", "kicad/FC-MAGICON.pretty/*",
    "kicad/FC-MAGICON_gerber_r0.2.zip", "images/*.png",
    "firmware/README.md", "firmware/CMakeLists.txt", "firmware/build.ps1", "firmware/boards/*.h",
    "firmware/bus_test/*", "firmware/chr_test/*", "firmware/tools/*.py", "firmware/out/*.uf2",
    "3d/*.py", "3d/*.step", "kicad/3d/*.step",
    "case/*.py", "case/parts.json", "case/label/*.py", "case/label/*.ps1", "case/label/label.png",
]
# case/inspect/ はシェル(printables 860420)の断面図なので上げない。シェルの STEP 自体もリポジトリに無い
EXCLUDE = ["kicad/*.pass*.kicad_pcb", "kicad/*.before_*.kicad_pcb", "kicad/__pycache__/*", "kicad/_step_tmp*"]


def api(path, method="GET", body=None, repo_path=True):
    cmd = [GH, "api", (f"repos/{REPO}/{path}" if repo_path else path), "-X", method]
    tmp = None
    if body is not None:
        tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8")
        json.dump(body, tmp)
        tmp.close()
        cmd += ["--input", tmp.name]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if tmp:
        os.unlink(tmp.name)
    if r.returncode:
        raise SystemExit(f"{method} {path}: {r.stderr or r.stdout}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


files = sorted({p for pat in INCLUDE for p in ROOT.glob(pat) if p.is_file()})
files = [p for p in files if not any(fnmatch.fnmatch(p.relative_to(ROOT).as_posix(), e) for e in EXCLUDE)]

head = api("git/ref/heads/main")["object"]["sha"]
base_tree = api(f"git/commits/{head}")["tree"]["sha"]
tree = []
for f in files:
    rel = f.relative_to(ROOT).as_posix()
    blob = api("git/blobs", "POST", {"content": base64.b64encode(f.read_bytes()).decode(), "encoding": "base64"})
    tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    print("blob", rel)
new_tree = api("git/trees", "POST", {"base_tree": base_tree, "tree": tree})["sha"]
commit = api("git/commits", "POST", {"message": MESSAGE + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
                                     "tree": new_tree, "parents": [head]})["sha"]
api("git/refs/heads/main", "PATCH", {"sha": commit})
print("pushed", commit, len(files), "files")
