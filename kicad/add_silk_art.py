"""裏面シルクにロゴ・MADE BY SHIMA-R7・小さなスペック表を置く(配線済みの基板に後から足す)。
    python make_silk_logo.py → E:\\KiCad\\bin\\python.exe add_silk_art.py
  置いた物は PCB_GROUP "SILK_ART" にまとめる。もう一度実行すると前の分を消してから置き直す。
  場所は find_free_silk.py で調べた空き(座標は部品面から見た基板座標、左上が原点):
    ロゴ + MADE BY : モジュールの下、x 23〜58.5 / y 34〜43.5(パッド無し。ビアはテンティングなのでシルクを載せてよい)
    スペック表     : モジュールのソケットの内側、x 37.3〜52.5 / y 13〜28.4
  裏面なので左右反転して置く(裏から見て正しく読める)。
"""
import json
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "FC-MAGICON.kicad_pcb")
OX = OY = 100.0
MM = pcbnew.FromMM
V = lambda x, y: pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))

LOGO_CX, LOGO_Y = 40.75, 34.4        # ロゴの中心 x と上端 y
MADE_Y = 40.3
SPEC_R, SPEC_Y, SPEC_P = 52.2, 13.8, 1.5   # 表の右端(裏から見ると左端)、1行目の中心 y、行の間隔
SPEC = [
    "SPEC",
    "MCU  RP2350B",
    "RAM  2MB PSRAM",
    "CPU  A0-14 D0-7",
    "PPU  AD0-7 A8-13",
    "MIR  JP1-3",
    "SND  EXP -> 46",
    "USB  FPC / J6",
    "DBG  SWD J3",
    "PCB  1.2t 2L",
]

board = pcbnew.LoadBoard(PCB)
for g in list(board.Groups()):
    if g.GetName() == "SILK_ART":
        for it in list(g.GetItems()):
            board.Remove(it)
        board.Remove(g)
grp = pcbnew.PCB_GROUP(board)
grp.SetName("SILK_ART")
board.Add(grp)


def add(item):
    board.Add(item)
    grp.AddItem(item)


# ロゴ(裏から見て正しく読めるよう、左右反転: 画像の左端が基板座標では右)
logo = json.load(open(os.path.join(HERE, "silk_logo.json")))
for x0, y0, x1, y1 in logo["rects"]:
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(V(LOGO_CX + logo["w"] / 2 - x1, LOGO_Y + y0))
    s.SetEnd(V(LOGO_CX + logo["w"] / 2 - x0, LOGO_Y + y1))
    s.SetFilled(True)
    s.SetWidth(0)
    s.SetLayer(pcbnew.B_SilkS)
    add(s)


def text(s, x, y, h, w, thick, just):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(pcbnew.B_SilkS)
    t.SetMirrored(True)
    t.SetTextSize(pcbnew.VECTOR2I(MM(w), MM(h)))
    t.SetTextThickness(MM(thick))
    t.SetHorizJustify(just)
    t.SetPosition(V(x, y))
    add(t)
    return t


text("MADE BY SHIMA-R7", LOGO_CX, MADE_Y, 1.3, 1.2, 0.2, pcbnew.GR_TEXT_H_ALIGN_CENTER)
# 反転した文字の「左寄せ」は、基板座標では右端が起点になり左へ伸びる
for i, s in enumerate(SPEC):
    text(s, SPEC_R, SPEC_Y + i * SPEC_P, 1.0, 0.8, 0.15, pcbnew.GR_TEXT_H_ALIGN_LEFT)

board.Save(PCB)
bb = grp.GetBoundingBox()
print("SILK_ART", len(logo["rects"]), "rects,", len(SPEC) + 1, "texts")
for t in grp.GetItems():
    if t.GetClass() == "PCB_TEXT":
        b = t.GetBoundingBox()
        print(f"  {t.GetText():18} x {pcbnew.ToMM(b.GetLeft()) - OX:6.2f}..{pcbnew.ToMM(b.GetRight()) - OX:6.2f}  "
              f"y {pcbnew.ToMM(b.GetTop()) - OY:6.2f}..{pcbnew.ToMM(b.GetBottom()) - OY:6.2f}")


