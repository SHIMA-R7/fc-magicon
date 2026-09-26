"""基板の STEP を2つ書き出す(部品あり / 基板だけ)。
    python make_models.py  (先に一度)
    E:\\KiCad\\bin\\python.exe export_step.py
  設計ファイルは書き換えず、コピー(../kicad/_step_tmp.kicad_pcb)の 3D モデルだけ差し替えて書き出す:
  ・P1〜P4: 実物はピンソケット(高さ 8.5mm)なので PinSocket_2x08 のモデルにする(列の向きが逆なので x を 2.54mm ずらす)
            その上に Core2350B 側のピンヘッダー(樹脂 2.54mm、短い側が上)を裏返して載せる
  ・Core2350B の基板をソケット + ヘッダーの上(基板面から 11.04mm)に置く(core2350b_board.step)
  ・VR1: koa_sf6.step
  原点は基板の左上(KiCad 上の 100, 100mm)。
"""
import os
import shutil
import subprocess

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KI = os.path.normpath(os.path.join(HERE, "..", "kicad"))
SRC = os.path.join(KI, "FC-MAGICON.kicad_pcb")
TMP = os.path.join(KI, "_step_tmp.kicad_pcb")
CLI = r"E:\KiCad\bin\kicad-cli.exe"
REV = "r0.2"
SOCKET_H = 8.5
HEADER_T = 2.54
MOD_X, MOD_Y = 32.3, 8.0   # Core2350B の左上(基板座標)。build_pcb.py の MOD_X, MOD_Y(5.0 + SHIFT)
V = pcbnew.VECTOR3D


def model(path, offset=(0, 0, 0), rot=(0, 0, 0)):
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = path
    m.m_Offset = V(*offset)
    m.m_Rotation = V(*rot)
    m.m_Scale = V(1, 1, 1)
    return m


shutil.copy(SRC, TMP)
board = pcbnew.LoadBoard(TMP)
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
for ref in ("P1", "P2", "P3", "P4"):
    fp = fps[ref]
    fp.Models().clear()
    fp.Models().push_back(model("${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_2x08_P2.54mm_Vertical.step",
                                (2.54, 0, 0)))
    # ヘッダーを y 軸まわりに 180° 回す -> 列が -x 側へ、樹脂が z<0 へ。x を 2.54、z を ソケット + 樹脂 だけ戻す
    fp.Models().push_back(model("${KICAD10_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_2x08_P2.54mm_Vertical.step",
                                (2.54, 0, SOCKET_H + HEADER_T), (0, 180, 0)))
fps["VR1"].Models().clear()
fps["VR1"].Models().push_back(model(os.path.join(KI, "3d", "koa_sf6.step")))

# Core2350B の基板は、部品を持たない足跡を1つ足してそこに置く
mod = pcbnew.FOOTPRINT(board)
mod.SetReference("MOD1")
mod.SetValue("Core2350B")
mod.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(100 + MOD_X + 12.7), pcbnew.FromMM(100 + MOD_Y + 12.7)))
mod.Models().push_back(model(os.path.join(KI, "3d", "core2350b_board.step"), (0, 0, SOCKET_H + HEADER_T)))
board.Add(mod)
board.Save(TMP)

outs = {
    "parts": ["--subst-models", "--include-pads", "--include-silkscreen"],
    "board": ["--board-only"],
}
for tag, opt in outs.items():
    out = os.path.join(HERE, f"FC-MAGICON_{REV}_{tag}.step")
    r = subprocess.run([CLI, "pcb", "export", "step", "--force", "--user-origin", "100x100mm", *opt, "-o", out, TMP],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(tag, "->", out)
    for line in (r.stdout + r.stderr).splitlines():
        if "Could not" in line or "not found" in line or "rror" in line:
            print("   ", line)
os.remove(TMP)
for ext in (".kicad_prl", ".kicad_pro"):
    p = TMP.replace(".kicad_pcb", ext)
    if os.path.exists(p):
        os.remove(p)
