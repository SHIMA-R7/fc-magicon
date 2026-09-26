"""
FC-MAGICON 用のフットプリントを FC-MAGICON.pretty に作る。

  FC_Cart_Edge_60  ファミコン 60ピン カセット端子(金メッキ端子)
    寸法の出典(数値のみ参照、ファイルは流用していない):
      nesdev Famicom cartridge dimensions / Gumball2415 NES-Famicom-Cartridge-Dimensions(HVC-TGROM-01)
      / Keitark fc-rom-vomitter。3つともパッド位置は一致した。
    原点 = 差し込み部の付け根の中央。y=+10.7 が差し込む側の端。
    F.Cu(部品面、本体の手前を向く)= 1〜30番、B.Cu(奥)= 31〜60番。1番/31番 が -X 側(部品面から見て左)。
    (2026-09-26 実機で確認: 1〜30番の面が本体の手前。市販カセットはこちらがラベル面)
    1・30・31番(GND/+5V)は幅広、1・16・30・31番は差し込み側へ1mm長い(先に接触する)。
  PJ-324M          SHVC-SOUND-ESP32 と同じ 3.5mm ジャック(そのフォルダからコピー)
"""
import os
import shutil
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "FC-MAGICON.pretty")
os.makedirs(LIB, exist_ok=True)

TONGUE_W, TONGUE_L = 78.4, 10.7
PITCH = 2.54
MASK_Y0 = 2.4                  # レジスト開口の上端(パッド上端 3.0 の 0.6mm 上)


def u():
    return str(uuid.uuid4())


def edge():
    out = ['(footprint "FC_Cart_Edge_60"', '  (version 20240108)', '  (generator "gen_footprints")', '  (layer "F.Cu")',
           '  (descr "Famicom 60-pin cartridge edge, 2.54mm pitch, 1.2mm PCB. F.Cu=1-30 (console front), B.Cu=31-60, pin 1/31 at -X. '
           'Origin = tongue root centre, insertion edge at y=+10.7")',
           '  (attr smd exclude_from_pos_files exclude_from_bom)',
           f'  (property "Reference" "J1" (at 0 -2 0) (layer "F.SilkS") (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))',
           f'  (property "Value" "FC_Cart_Edge_60" (at 0 12 0) (layer "F.Fab") (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))']
    hw, L = TONGUE_W / 2, TONGUE_L
    for layer in ("F.Mask", "B.Mask"):    # 端子部はレジストなし(金メッキ)。端子の上端(y=3.0)より少し上から。付け根側の配線はレジストで覆う
        out.append(f'  (fp_rect (start {-hw} {MASK_Y0}) (end {hw} {L}) (stroke (width 0) (type solid)) (fill yes) (layer "{layer}") (uuid "{u()}"))')
    out.append(f'  (fp_rect (start {-hw} 0) (end {hw} {L}) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab") (uuid "{u()}"))')
    out.append(f'  (fp_rect (start {-hw - 0.25} -0.25) (end {hw + 0.25} {L + 0.25}) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{u()}"))')
    for k in range(30):
        x = -36.83 + PITCH * k          # k=0 が 1番/31番(左端)
        for layer, num in (("F.Cu", k + 1), ("B.Cu", k + 31)):
            w, h, cy = 1.6, 5.7, 5.85
            if num in (1, 30, 31):      # GND/+5V は幅広(外側へ0.5mm寄せて広げる)
                w, h, cy = 2.6, 6.7, 6.35
                x_ = x + 0.5 if x > 0 else x - 0.5
            else:
                x_ = x
            if num == 16:               # GND は先に接触させる
                h, cy = 6.7, 6.35
            out.append(f'  (pad "{num}" smd rect (at {x_:.2f} {cy}) (size {w} {h}) (layers "{layer}") (uuid "{u()}"))')
    for txt, x in (("1", -37.5), ("30", 37.5)):
        out.append(f'  (fp_text user "{txt}" (at {x} -1.2 0) (layer "F.SilkS") (uuid "{u()}") (effects (font (size 0.8 0.8) (thickness 0.12))))')
    for txt, x in (("31", -37.5), ("60", 37.5)):
        out.append(f'  (fp_text user "{txt}" (at {x} -1.2 0) (layer "B.SilkS") (uuid "{u()}") (effects (font (size 0.8 0.8) (thickness 0.12)) (justify mirror)))')
    out.append(")")
    open(os.path.join(LIB, "FC_Cart_Edge_60.kicad_mod"), "w", encoding="utf-8").write("\n".join(out) + "\n")


def koa_sf6_637a():
    """KOA KVSF637A(SF6 上面調整形、例: KVSF637AC104)。データシート(秋月 SF6.pdf)の推奨取付穴:
    ①③ は 5.0mm 間隔、② は中央から 5.0mm 上、穴 φ1.2。本体 6.4 x 7.3mm(①③ の線から下へ 1.1、上へ 6.2)"""
    out = ['(footprint "KOA_SF6_637A"', '  (version 20240108)', '  (generator "gen_footprints")', '  (layer "F.Cu")',
           '  (descr "KOA KVSF637A trimmer (SF6, top adjust). Holes per datasheet: 1-3 5.0mm, 2 at 5.0mm above centre, D1.2")',
           '  (attr through_hole)',
           f'  (property "Reference" "VR1" (at 2.5 2.4 0) (layer "F.SilkS") (uuid "{u()}") (effects (font (size 0.8 0.8) (thickness 0.12))))',
           f'  (property "Value" "KVSF637AC104" (at 2.5 -7.2 0) (layer "F.Fab") (uuid "{u()}") (effects (font (size 0.8 0.8) (thickness 0.12))))']
    x0, x1, y0, y1 = -0.7, 5.7, -6.2, 1.1
    # パッド(φ2.2)は本体の幅より外へはみ出すので、シルクとコートヤードはパッドの外側まで広げる
    for layer, xa, xb, ya, yb, w in (("F.SilkS", -1.5, 6.5, y0 - 0.1, 1.6, 0.12), ("F.Fab", x0, x1, y0, y1, 0.1),
                                     ("F.CrtYd", -1.75, 6.75, y0 - 0.35, 1.85, 0.05)):
        out.append(f'  (fp_rect (start {xa:.2f} {ya:.2f}) (end {xb:.2f} {yb:.2f}) (stroke (width {w}) (type solid)) (fill no) (layer "{layer}") (uuid "{u()}"))')
    out.append(f'  (fp_circle (center 2.5 -3.0) (end 4.5 -3.0) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab") (uuid "{u()}"))')
    for num, x, y in (("1", 0, 0), ("3", 5.0, 0), ("2", 2.5, -5.0)):
        shape = "rect" if num == "1" else "circle"
        out.append(f'  (pad "{num}" thru_hole {shape} (at {x} {y}) (size 2.2 2.2) (drill 1.2) (layers "*.Cu" "*.Mask") (uuid "{u()}"))')
    out.append(")")
    open(os.path.join(LIB, "KOA_SF6_637A.kicad_mod"), "w", encoding="utf-8").write("\n".join(out) + "\n")


edge()
koa_sf6_637a()
shutil.copy(os.path.join(HERE, "..", "..", "SHVC-SOUND", "SHVC-SOUND-Player", "SHVC-SOUND-ESP32-KiCad", "SHVC-ESP32.pretty",
                         "PJ-324M.kicad_mod"), LIB)
with open(os.path.join(HERE, "fp-lib-table"), "w", encoding="utf-8") as f:
    f.write('(fp_lib_table (version 7)\n  (lib (name "FC-MAGICON") (type "KiCad") (uri "${KIPRJMOD}/FC-MAGICON.pretty") '
            '(options "") (descr ""))\n)\n')
print("->", LIB, sorted(os.listdir(LIB)))
