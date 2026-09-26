"""R1 を裏面に付け替え、Q1 を下へ倒す場所をコートヤードにする(2026-09-26、ユーザー判断)。配線済みの基板に1回だけ実行する。
    E:\\KiCad\\bin\\python.exe move_r1.py
  ・R1(0Ω、CIRAM /CE ← /A13 = カセット 48番 ← 49番)は、パッドの位置も配線もそのままで本体だけ裏へ(build_pcb.py の BACK_PARTS)。
    表に残るのははんだ付けした足先だけなので、Q1 はその上に倒せる(1mm くらい浮く)。
    (R1 を右へずらす案は、J4 から上へ行く線の通り道に掛かり、3か所とも自動配線しきれなかった)
  ・Q1 のコートヤードを、下へ倒した本体の分(build_pcb.py の LAYDOWN_DOWN)まで広げ、シルクに本体の枠を描く。
  図形を足したり消したりすると SWIG の参照が壊れるので、読む処理を先に済ませる。
"""
import pcbnew

import build_pcb as B

board = pcbnew.LoadBoard(B.PCB)
for ref in B.BACK_PARTS:
    fp = board.FindFootprintByReference(ref)
    if not fp.IsFlipped():
        B.to_back(fp)
    print(ref, "裏面:", fp.IsFlipped(), [(p.GetNumber(), round(pcbnew.ToMM(p.GetPosition().x) - B.OX, 2),
                                          round(pcbnew.ToMM(p.GetPosition().y) - B.OY, 2), p.GetNetname()) for p in fp.Pads()])
for ref, length, width, x_min in B.LAYDOWN_DOWN:
    B.lay_down_below(board.FindFootprintByReference(ref), length, width, x_min)
pcbnew.SaveBoard(B.PCB, board)

