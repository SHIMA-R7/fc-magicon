"""
FCマジコンカセット(Waveshare Core2350B + ファミコン60ピン)の回路図(KiCad 10形式)を生成する。

  J1  ファミコン カセット端子 60ピン(基板エッジ)
  P1-P4  Waveshare Core2350B(RP2350B)の 8x2 ヘッダー4列
  U2  74LVC245  PPU /RD・/WR・A13 を 5V→3.3V(5V非トレラントの GPIO40-42 へ)
  Q1  NPN(2SC1815等)  /IRQ をオープンコレクタで引く
  J2  3.5mm ライン出力 / J3 SWD

配線は各ピンにネット名のラベルを置く方式(同じ名前のラベル同士がつながる)。
実行: python gen_schematic.py → FC-MAGICON.kicad_sch
"""
import uuid

LIB = "FC-MAGICON"
PROJECT = "FC-MAGICON"
G = 2.54


def uid():
    return str(uuid.uuid4())


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


FONT = "(effects (font (size 1.27 1.27)))"
FONT_HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"


def ic(left, right, width=8):
    return {"left": left, "right": right, "width": width}


# ---- カセット端子 ---------------------------------------------------------------
# 信号線は ../../FC のダンパー(fc_uno / fc_nano / fc_chr328)で実機確認済みの対応。
# 1,16(GND) 30,31(+5V) 15(/IRQ) 18(CIRAM A10) 45,46(音声) 47(/WR) 48(CIRAM /CE) 49(/A13) は
# nesdev の資料による。基板発注前に麻雀カセット・本体で導通確認すること。
FC_PINS = {1: "GND", 2: "CPU_A11", 3: "CPU_A10", 4: "CPU_A9", 5: "CPU_A8", 6: "CPU_A7", 7: "CPU_A6",
           8: "CPU_A5", 9: "CPU_A4", 10: "CPU_A3", 11: "CPU_A2", 12: "CPU_A1", 13: "CPU_A0", 14: "CPU_R~{W}",
           15: "~{IRQ}", 16: "GND", 17: "PPU_~{RD}", 18: "CIRAM_A10", 19: "PPU_A6", 20: "PPU_A5", 21: "PPU_A4",
           22: "PPU_A3", 23: "PPU_A2", 24: "PPU_A1", 25: "PPU_A0", 26: "PPU_D0", 27: "PPU_D1", 28: "PPU_D2",
           29: "PPU_D3", 30: "+5V", 31: "+5V", 32: "M2", 33: "CPU_A12", 34: "CPU_A13", 35: "CPU_A14",
           36: "CPU_D7", 37: "CPU_D6", 38: "CPU_D5", 39: "CPU_D4", 40: "CPU_D3", 41: "CPU_D2", 42: "CPU_D1",
           43: "CPU_D0", 44: "~{ROMSEL}", 45: "SOUND_IN", 46: "SOUND_OUT", 47: "PPU_~{WR}", 48: "CIRAM_~{CE}",
           49: "PPU_~{A13}", 50: "PPU_A7", 51: "PPU_A8", 52: "PPU_A9", 53: "PPU_A10", 54: "PPU_A11",
           55: "PPU_A12", 56: "PPU_A13", 57: "PPU_D7", 58: "PPU_D6", 59: "PPU_D5", 60: "PPU_D4"}


def _fc_type(n):
    # ERC用: 本体から来る電源/GNDは「供給元」。同じネットに供給元が2つあるとエラーになるので1本ずつ
    return "power_out" if n in (1, 30) else "passive"


FC_LEFT = [(str(n), FC_PINS[n], _fc_type(n)) for n in range(1, 31)]
FC_RIGHT = [(str(n), FC_PINS[n], _fc_type(n)) for n in range(31, 61)]

# ---- Core2350B ヘッダー ---------------------------------------------------------
# Waveshare Core2350B 回路図(files.waveshare.com/wiki/Core2350B0/Core2350B.pdf)から読み取り。
# 奇数ピン=左列、偶数ピン=右列。物理的な列間隔・向きは基板設計時に実物で確認する。


def header(names):
    """names: ピン1..16 の名前"""
    left = [(str(i), names[i - 1], "passive") for i in range(1, 17, 2)]
    right = [(str(i), names[i - 1], "passive") for i in range(2, 17, 2)]
    return ic(left, right, 10)


def _gpio_header(base):
    # P1/P3/P4 共通の並び: 1=GND, 2=GPIO(base)。2行目以降は 奇数=base+2k, 偶数=base+2k-1
    out = ["GND", f"GPIO{base}"]
    for row in range(1, 8):
        out += [f"GPIO{base + 2 * row}", f"GPIO{base + 2 * row - 1}"]
    return out


P1_NAMES = _gpio_header(0)     # GPIO0-14
P3_NAMES = _gpio_header(15)    # GPIO15-29
P4_NAMES = _gpio_header(30)    # GPIO30-44
P2_NAMES = ["GND", "GPIO45", "GPIO47_PSRAM_CS", "GPIO46", "BOOTSEL", "SWD", "USBD_N", "GND",
            "USBD_P", "SWCLK", "RUN", "ADC_VREF", "3V3_EN", "GND", "VBUS", "3V3"]


def hdr_pin(names, gpio):
    return str(names.index(f"GPIO{gpio}") + 1)


LVC245_LEFT = [("1", "DIR", "input"), ("19", "~{OE}", "input"), None] + \
    [(str(n), f"A{n - 1}", "input") for n in range(2, 10)] + [None, ("20", "VCC", "power_in"), ("10", "GND", "power_in")]
LVC245_RIGHT = [None, None, None] + [(str(19 - k), f"B{k}", "output") for k in range(1, 9)]

SYMBOLS = {
    "FC_Cart_60": ("J", ic(FC_LEFT, FC_RIGHT, 14)),
    "Core2350B_P1": ("P", header(P1_NAMES)),
    "Core2350B_P2": ("P", ic([(str(i), P2_NAMES[i - 1], "power_out" if P2_NAMES[i - 1] == "3V3" else
                               "power_in" if P2_NAMES[i - 1] == "VBUS" else "passive") for i in range(1, 17, 2)],
                             [(str(i), P2_NAMES[i - 1], "power_out" if P2_NAMES[i - 1] == "3V3" else "passive")
                              for i in range(2, 17, 2)], 14)),
    "Core2350B_P3": ("P", header(P3_NAMES)),
    "Core2350B_P4": ("P", header(P4_NAMES)),
    "74LVC245": ("U", ic(LVC245_LEFT, LVC245_RIGHT, 8)),
    # TO-92。2SC1815(KEC/東芝)は平らな面から見て 1=E 2=C 3=B。別品種は足順を確認
    "NPN_ECB": ("Q", ic([("3", "B", "passive")], [("2", "C", "passive"), ("1", "E", "passive")], 4)),
    # PJ-324M(SHVC-SOUND-ESP32 と同じ): 1=スリーブ、4/5=チップと接点、2/3=リングと接点。モノラル信号を L/R 両方へ
    "PJ-324M": ("J", ic([("1", "SLEEVE", "passive"), ("4", "TIP", "passive"), ("5", "TIP_SW", "passive"),
                         ("2", "RING", "passive"), ("3", "RING_SW", "passive")], [], 6)),
    "TestPoint": ("TP", ic([("1", "TP", "passive")], [], 2)),
    # 半固定抵抗(1・3番が両端、2番が中点)
    "Trimmer": ("VR", ic([("1", "1", "passive"), ("2", "W", "passive"), ("3", "3", "passive")], [], 4)),
    "Conn_3": ("J", ic([("1", "1", "passive"), ("2", "2", "passive"), ("3", "3", "passive")], [], 4)),
    # USB の予備ランド(1x4)。並びは USB-A の 1〜4 番と同じ
    "USB_Land_4": ("J", ic([("1", "VBUS", "passive"), ("2", "D-", "passive"), ("3", "D+", "passive"), ("4", "GND", "passive")], [], 6)),
    # カセット60ピン全部のブレイクアウト(2x30 ヘッダー)。ヘッダーの 2k+1 番 = カセット k+1 番、2k+2 番 = カセット k+31 番
    # (基板上では各列がカセット端子の真上に来る)
    "Breakout_2x30": ("J", ic([(str(2 * k + 1), f"{k + 1}:{FC_PINS[k + 1]}", "passive") for k in range(30)],
                              [(str(2 * k + 2), f"{k + 31}:{FC_PINS[k + 31]}", "passive") for k in range(30)], 16)),
    "Conn_2x8": ("J", ic([(str(2 * k + 1), str(2 * k + 1), "passive") for k in range(8)],
                         [(str(2 * k + 2), str(2 * k + 2), "passive") for k in range(8)], 4)),
}

# J5 デバッグ用ヘッダー(2x8)。基板の中だけにある信号を出す
J5_NETS = ["PPU_~{RD}_3V3", "PPU_~{WR}_3V3", "PPU_A13_3V3", "CIRAM_A10_MCU", "EXP_AUDIO_PWM", "EXP_AUDIO_RC",
           "IRQ_DRV", "FC_5V_SENSE", "+3V3", "VBUS_MOD", "CIRAM_A10", "GND", "GND", "GND", "GND", "GND"]
# 12・13・14番は元は LOUT・Q1_B・LINE。J6(USB ランド)を足し配線を太くした時に2層で引けなくなったので GND にした。
# これらは J2・R10・R11・Q1 の足で測れる


def ic_geometry(spec):
    rows = max(len(spec["left"]), len(spec["right"]))
    w = spec["width"] * G / 2
    top = (rows - 1) * G / 2
    pins = []
    for i, p in enumerate(spec["left"]):
        if p:
            pins.append((*p, -w - G, top - i * G, 0))
    for i, p in enumerate(spec["right"]):
        if p:
            pins.append((*p, w + G, top - i * G, 180))
    return pins, w, top + G, -(top + G)


def lib_symbol_ic(name, ref, spec):
    pins, w, ytop, ybot = ic_geometry(spec)
    out = [f'(symbol "{LIB}:{name}" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
           f'(property "Reference" "{ref}" (at 0 {fmt(ytop + 1.27)} 0) {FONT})',
           f'(property "Value" "{name}" (at 0 {fmt(ybot - 1.27)} 0) {FONT})',
           f'(property "Footprint" "" (at 0 0 0) {FONT_HIDE})',
           f'(property "Datasheet" "" (at 0 0 0) {FONT_HIDE})',
           f'(symbol "{name}_0_1" (rectangle (start {fmt(-w)} {fmt(ytop)}) (end {fmt(w)} {fmt(ybot)}) '
           f'(stroke (width 0.254) (type default)) (fill (type background))))',
           f'(symbol "{name}_1_1"']
    for num, pname, ptype, x, y, ang in pins:
        out.append(f'(pin {ptype} line (at {fmt(x)} {fmt(y)} {ang}) (length {G}) '
                   f'(name "{pname}" {FONT}) (number "{num}" {FONT}))')
    out.append("))")
    return "\n".join(out), pins


def lib_symbol_2pin(name, ref, kind, types=("passive", "passive")):
    body = {"R": '(rectangle (start -1.016 2.286) (end 1.016 -2.286) (stroke (width 0.254) (type default)) (fill (type none)))',
            "C": '(polyline (pts (xy -2.032 0.762) (xy 2.032 0.762)) (stroke (width 0.508) (type default)) (fill (type none)))'
                 ' (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762)) (stroke (width 0.508) (type default)) (fill (type none)))',
            # ダイオード: 1番=カソード(上)、2番=アノード(下)
            "D": '(polyline (pts (xy -1.27 1.016) (xy 1.27 1.016)) (stroke (width 0.254) (type default)) (fill (type none)))'
                 ' (polyline (pts (xy 0 1.016) (xy -1.27 -1.016) (xy 1.27 -1.016) (xy 0 1.016)) (stroke (width 0.254) (type default)) (fill (type none)))',
            # ソルダージャンパー / スイッチ: 半円2つ(簡略)
            "JP": '(polyline (pts (xy -1.016 0.508) (xy 1.016 0.508)) (stroke (width 0.254) (type default)) (fill (type none)))'
                  ' (polyline (pts (xy -1.016 -0.508) (xy 1.016 -0.508)) (stroke (width 0.254) (type default)) (fill (type none)))',
            "SW": '(polyline (pts (xy 0 -1.27) (xy 1.27 1.016)) (stroke (width 0.254) (type default)) (fill (type none)))'}[kind]
    pins = [("1", "1", types[0], 0, 3.81, 270), ("2", "2", types[1], 0, -3.81, 90)]
    out = [f'(symbol "{LIB}:{name}" (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
           f'(property "Reference" "{ref}" (at 2.54 1.27 0) (effects (font (size 1.27 1.27)) (justify left)))',
           f'(property "Value" "{name}" (at 2.54 -1.27 0) (effects (font (size 1.27 1.27)) (justify left)))',
           f'(property "Footprint" "" (at 0 0 0) {FONT_HIDE})',
           f'(property "Datasheet" "" (at 0 0 0) {FONT_HIDE})',
           f'(symbol "{name}_0_1" {body})',
           f'(symbol "{name}_1_1"']
    for num, pname, ptype, x, y, ang in pins:
        out.append(f'(pin {ptype} line (at {fmt(x)} {fmt(y)} {ang}) (length 1.27) (name "{pname}" {FONT}) (number "{num}" {FONT}))')
    out.append("))")
    return "\n".join(out), pins


# ---- 回路 ------------------------------------------------------------------
ROOT = uid()
lib_defs, pin_table = {}, {}
for n, (ref, spec) in SYMBOLS.items():
    lib_defs[n], pin_table[n] = lib_symbol_ic(n, ref, spec)
for n, ref, kind in (("R", "R", "R"), ("C", "C", "C"), ("SolderJumper", "JP", "JP"), ("SW_Push", "SW", "SW")):
    lib_defs[n], pin_table[n] = lib_symbol_2pin(n, ref, kind)
# 逆流防止ダイオード。ERCで VBUS_MOD の供給元と見なせるようカソードを power_out にする
lib_defs["D_Schottky"], pin_table["D_Schottky"] = lib_symbol_2pin("D_Schottky", "D", "D", ("power_out", "power_in"))

items, labels, texts, noconn = [], [], [], []

FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D3.0mm_W1.6mm_P2.50mm"
# Core2350B を載せる穴。実物は 2x8 ピンソケットを付けるが、ピン番号の並びはモジュール側(ピンヘッダー)を
# 上から見た並びと同じにしたいので、フットプリントは PinHeader を使う(PinSocket は番号が左右反転している)
FP_HDR = "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical"
FP_JP = "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"
FOOTPRINTS = {
    "J1": "FC-MAGICON:FC_Cart_Edge_60",       # gen_footprints.py で生成(厚み1.2mm、ピッチ2.54mm)
    "P1": FP_HDR, "P2": FP_HDR, "P3": FP_HDR, "P4": FP_HDR,
    "U2": "Package_DIP:DIP-20_W7.62mm",       # SN74LVC245AN(DIP)。手はんだ・ソケット用
    "Q1": "Package_TO_SOT_THT:TO-92_Inline_Wide",   # 足の間隔2.54mm(手はんだ向け)
    "D1": "Diode_THT:D_DO-41_SOD81_P7.62mm_Horizontal",
    "J2": "FC-MAGICON:PJ-324M",
    "J3": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "J4": "Connector_PinHeader_2.54mm:PinHeader_2x30_P2.54mm_Vertical",
    "J5": "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical",
    "J6": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "SW1": "Button_Switch_THT:SW_PUSH_6mm", "SW2": "Button_Switch_THT:SW_PUSH_6mm",
    "JP1": FP_JP, "JP2": FP_JP, "JP3": FP_JP,
    "C1": "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm", "C4": "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
}
FOOTPRINTS.update({f"TP{i}": "TestPoint:TestPoint_THTPad_D1.5mm_Drill0.7mm" for i in range(1, 6)})
FOOTPRINTS["VR1"] = "FC-MAGICON:KOA_SF6_637A"   # KOA KVSF637AC104(100kΩ、上面調整)。gen_footprints.py で生成


def place(sym, ref, value, x, y, nets, footprint=""):
    """nets: {ピン番号: ネット名}。ピン番号が無いピンは未接続扱い(×印)。"""
    footprint = footprint or FOOTPRINTS.get(ref, FP_R if sym == "R" else FP_C if sym == "C" else "")
    pins = pin_table[sym]
    # 基板の一部でしかない物(カセット端子・ソルダージャンパー・テストポイント)は部品表に入れない
    bom = "no" if ref == "J1" or ref.startswith(("JP", "TP")) else "yes"
    inst = [f'(symbol (lib_id "{LIB}:{sym}") (at {fmt(x)} {fmt(y)} 0) (unit 1) (exclude_from_sim no) '
            f'(in_bom {bom}) (on_board yes) (dnp no) (uuid "{uid()}")',
            f'(property "Reference" "{ref}" (at {fmt(x)} {fmt(y - 2)} 0) {FONT})',
            f'(property "Value" "{value}" (at {fmt(x)} {fmt(y + 2)} 0) {FONT})',
            f'(property "Footprint" "{footprint}" (at {fmt(x)} {fmt(y)} 0) {FONT_HIDE})',
            f'(property "Datasheet" "" (at {fmt(x)} {fmt(y)} 0) {FONT_HIDE})']
    if sym in SYMBOLS:
        _, _, ytop, ybot = ic_geometry(SYMBOLS[sym][1])
        inst[1] = f'(property "Reference" "{ref}" (at {fmt(x)} {fmt(y - ytop - 1.27)} 0) {FONT})'
        inst[2] = f'(property "Value" "{value}" (at {fmt(x)} {fmt(y - ybot + 1.9)} 0) {FONT})'
    else:
        inst[1] = f'(property "Reference" "{ref}" (at {fmt(x + 2.54)} {fmt(y - 1.27)} 0) (effects (font (size 1.27 1.27)) (justify left)))'
        inst[2] = f'(property "Value" "{value}" (at {fmt(x + 2.54)} {fmt(y + 1.27)} 0) (effects (font (size 1.27 1.27)) (justify left)))'
    for num, *_ in pins:
        inst.append(f'(pin "{num}" (uuid "{uid()}"))')
    inst.append(f'(instances (project "{PROJECT}" (path "/{ROOT}" (reference "{ref}") (unit 1)))))')
    items.append("\n".join(inst))
    for num, pname, ptype, px, py, ang in pins:
        ax, ay = x + px, y - py
        if num in nets and nets[num]:
            net = nets[num]
            lab_ang, just = {0: (180, "right"), 180: (0, "left"), 270: (90, "left")}.get(ang, (270, "right"))
            labels.append(f'(label "{net}" (at {fmt(ax)} {fmt(ay)} {lab_ang}) (fields_autoplaced yes) '
                          f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid "{uid()}"))')
        else:
            noconn.append(f'(no_connect (at {fmt(ax)} {fmt(ay)}) (uuid "{uid()}"))')


def text(s, x, y, size=1.8):
    texts.append(f'(text "{s}" (exclude_from_sim no) (at {fmt(x)} {fmt(y)} 0) '
                 f'(effects (font (size {size} {size})) (justify left bottom)) (uuid "{uid()}"))')


# ---- ピン割り当て(GPIO → ネット) ----------------------------------------------
# PIO の 32本窓: CPU用ブロックは GPIO0-31、PPU用ブロックは GPIO16-47 を使う。
GPIO = {}
for i in range(8):
    GPIO[i] = f"CPU_D{i}"            # GPIO0-7
for i in range(15):
    GPIO[8 + i] = f"CPU_A{i}"        # GPIO8-22(A0から連続 = アドレスをそのまま添字にできる)
GPIO[23] = "~{ROMSEL}"
GPIO[24] = "CPU_R~{W}"
GPIO[25] = "M2"
for i in range(8):
    GPIO[26 + i] = f"PPU_D{i}"       # GPIO26-33: PPU AD0-7(/RD直前はアドレス下位、その後データ)
for i in range(5):
    GPIO[34 + i] = f"PPU_A{8 + i}"   # GPIO34-38: 26-38 で13ビットのアドレスが連続する
# GPIO39 = 基板上LED(470Ω)。バス信号には使わない
GPIO[40] = "PPU_~{RD}_3V3"           # GPIO40-44 は5V非トレラント → 74LVC245 経由の入力か出力専用
GPIO[41] = "PPU_~{WR}_3V3"
GPIO[42] = "PPU_A13_3V3"
GPIO[43] = "CIRAM_A10_MCU"
GPIO[44] = "EXP_AUDIO_PWM"
GPIO[45] = "IRQ_DRV"
GPIO[46] = "FC_5V_SENSE"

# J1 カセット端子(ラベル名は FC_PINS と同じ。電源だけ名前を合わせる)
# PPU A0-A7(ラッチ出力)は RP2350 では使わない(AD0-7から読む)が、J4 のブレイクアウトには出す
j1 = {str(n): name for n, name in FC_PINS.items()}
place("FC_Cart_60", "J1", "Famicom cart edge 60p", G * 28, G * 50, j1)
place("Breakout_2x30", "J4", "Cart breakout 2x30", G * 185, G * 60,
      {**{str(2 * k + 1): FC_PINS[k + 1] for k in range(30)}, **{str(2 * k + 2): FC_PINS[k + 31] for k in range(30)}})
place("Conn_2x8", "J5", "Debug 2x8", G * 185, G * 120, {str(i + 1): n for i, n in enumerate(J5_NETS)})
place("USB_Land_4", "J6", "USB spare land", G * 185, G * 140, {"1": "VBUS_MOD", "2": "USBD_N", "3": "USBD_P", "4": "GND"})

for sym, ref, names, x, y in (("Core2350B_P1", "P1", P1_NAMES, G * 80, G * 24),
                              ("Core2350B_P3", "P3", P3_NAMES, G * 80, G * 50),
                              ("Core2350B_P4", "P4", P4_NAMES, G * 80, G * 76)):
    nets = {}
    for pin, name in enumerate(names, 1):
        if name == "GND":
            nets[str(pin)] = "GND"
        else:
            g = int(name[4:])
            if g in GPIO:
                nets[str(pin)] = GPIO[g]
            elif g == 39:
                nets[str(pin)] = ""      # LED
    place(sym, ref, f"Core2350B {ref}", x, y, nets)

p2 = {"1": "GND", "8": "GND", "14": "GND", "2": GPIO[45], "4": GPIO[46], "5": "BOOTSEL", "11": "RUN",
      "6": "SWD", "10": "SWCLK", "15": "VBUS_MOD", "16": "+3V3",
      "7": "USBD_N", "9": "USBD_P"}   # USB はモジュールの FPC でも使っている。J6 は予備のランド(同時に機器をつながない)
place("Core2350B_P2", "P2", "Core2350B P2", G * 128, G * 24, p2)

# U2 74LVC245: DIR=H(A→B)、/OE=L 常時有効。A側 5V入力、B側 3.3V出力
u2 = {"1": "+3V3", "19": "GND", "20": "+3V3", "10": "GND",
      "2": "PPU_~{RD}", "3": "PPU_~{WR}", "4": "PPU_A13",
      "5": "GND", "6": "GND", "7": "GND", "8": "GND", "9": "GND",
      "18": GPIO[40], "17": GPIO[41], "16": GPIO[42]}
place("74LVC245", "U2", "74LVC245 (5V->3.3V)", G * 110, G * 58, u2)
place("C", "C2", "100n", G * 120, G * 52, {"1": "+3V3", "2": "GND"})

# CIRAM /CE は /A13 に直結(標準的なカセットと同じ)
place("R", "R1", "0", G * 50, G * 74, {"1": "PPU_~{A13}", "2": "CIRAM_~{CE}"})

# ミラーリング(CIRAM A10 の供給元)。どれか1つだけ閉じる
#   JP1: MCU(マッパーエミュ用)  JP2: PPU A10 = 垂直ミラー  JP3: PPU A11 = 水平ミラー
place("SolderJumper", "JP1", "MCU", G * 142, G * 80, {"1": "CIRAM_A10_MCU", "2": "CIRAM_A10"})
place("SolderJumper", "JP2", "V (A10)", G * 148, G * 80, {"1": "PPU_A10", "2": "CIRAM_A10"})
place("SolderJumper", "JP3", "H (A11)", G * 154, G * 80, {"1": "PPU_A11", "2": "CIRAM_A10"})

# 電源: 本体 +5V → D1 → モジュール VBUS(→ 内蔵LDO 3.3V)。USB給電時に本体側へ逆流させない
place("D_Schottky", "D1", "1N4001", G * 110, G * 100, {"1": "VBUS_MOD", "2": "+5V"})
place("C", "C1", "10u", G * 116, G * 100, {"1": "VBUS_MOD", "2": "GND"})
# 本体電源の検出: USBだけで動いているとき、本体の無電源バスへ出力しないためファームが見る
place("R", "R2", "15k", G * 122, G * 100, {"1": "+5V", "2": "FC_5V_SENSE"})
place("R", "R3", "22k", G * 128, G * 100, {"1": "FC_5V_SENSE", "2": "GND"})

# /IRQ: GPIO45=H で Q1 がONし /IRQ を Low に引く(オープンコレクタ)
place("R", "R4", "4.7k", G * 146, G * 14, {"1": "IRQ_DRV", "2": "Q1_B"})
place("R", "R5", "100k", G * 151, G * 14, {"1": "Q1_B", "2": "GND"})
place("NPN_ECB", "Q1", "2SC1815", G * 151, G * 28, {"3": "Q1_B", "2": "~{IRQ}", "1": "GND"})
place("R", "R6", "10k DNP", G * 156, G * 14, {"1": "+5V", "2": "~{IRQ}"})   # 本体側にプルアップが無ければ実装

# 音声: 45(本体の2A03音声)→ 0Ω → 46(本体へ戻る)。拡張音源は PWM→RC→R8 で46に混ぜる
place("R", "R7", "0", G * 130, G * 44, {"1": "SOUND_IN", "2": "SOUND_OUT"})
place("R", "R9", "1k", G * 136, G * 44, {"1": "EXP_AUDIO_PWM", "2": "EXP_AUDIO_RC"})
place("C", "C3", "10n", G * 142, G * 44, {"1": "EXP_AUDIO_RC", "2": "GND"})
# 拡張音源の音量: VR1(100k)で分圧してから R8(47k)で46番に混ぜる。つまみをどこに回しても、本体の音声ラインには 47k 以上が付く
place("Trimmer", "VR1", "KVSF637AC104", G * 148, G * 36, {"1": "EXP_AUDIO_RC", "2": "EXP_AUDIO_VR", "3": "GND"})
place("R", "R8", "47k", G * 148, G * 44, {"1": "EXP_AUDIO_VR", "2": "SOUND_OUT"})
# ライン出力: 46 → 10µF → 47kで0V基準 → 100Ω → 3.5mmジャック(L/R同じ)
place("C", "C4", "10u (+ to SOUND_OUT)", G * 130, G * 60, {"1": "SOUND_OUT", "2": "LOUT"})
place("R", "R10", "47k", G * 136, G * 60, {"1": "LOUT", "2": "GND"})
place("R", "R11", "100", G * 142, G * 60, {"1": "LINE", "2": "LOUT"})   # 足の向きは基板の配線の都合(抵抗なので無関係)
place("PJ-324M", "J2", "LINE OUT 3.5mm", G * 152, G * 62, {"1": "GND", "4": "LINE", "2": "LINE"})

# テストポイント: /RD からデータを返すまでの時間をオシロで測る(試作を兼ねる)
for i, (net, x) in enumerate((("PPU_~{RD}", 104), ("PPU_D0", 108), ("M2", 112), ("~{ROMSEL}", 116), ("GND", 120)), 1):
    place("TestPoint", f"TP{i}", net.replace("~{", "/").replace("}", ""), G * x, G * 94, {"1": net})

# 書き込み・デバッグ: BOOTSEL / RUN ボタン、SWD(debugprobe の Pico 用)
place("SW_Push", "SW1", "BOOTSEL", G * 128, G * 80, {"1": "BOOTSEL", "2": "GND"})
place("SW_Push", "SW2", "RESET", G * 134, G * 80, {"1": "RUN", "2": "GND"})
place("Conn_3", "J3", "SWD", G * 132, G * 94, {"1": "SWCLK", "2": "GND", "3": "SWD"})

text("FC-MAGICON: Waveshare Core2350B (RP2350B) Famicom cartridge - PRG/CHR emulation, NSF, screen streaming",
     G * 8, G * 8, 2.5)
notes = [
    "GPIO0-38 are 5V tolerant (IOVDD must be powered). GPIO40-47 are ADC pins: NOT 5V tolerant -> via U2 or output only.",
    "PPU A0-A7 (cart 19-25, 50) are NOT used: low address is sampled on PPU_D0-7 (=PPU AD0-7) just before /RD falls.",
    "GPIO39 has the on-board LED (470R) - keep it off the bus. GPIO47 = on-board PSRAM CS.",
    "RP2350 erratum E9: do not enable internal pull-downs on bus pins.",
    "Close exactly one of JP1/JP2/JP3 (CIRAM A10 source).",
    "Firmware must keep all bus pins as inputs until FC_5V_SENSE is high (USB-only power must not back-power the console).",
    "Cart pins 1,16,30,31,15,18,45,46,47,48,49: nesdev docs, cross-checked with fc-rom-vomitter (51 signal pins verified on real carts).",
    "Q1 2SC1815 pin order E-C-B (flat face). R6 is DNP unless the console has no /IRQ pull-up.",
    "R8 (mix level) and R7 (pass-through) values are to be tuned on real hardware.",
    "Core2350B header pinout: Waveshare schematic, checked against module silk on 2026-09-26. Module USB uses its own FPC adapter.",
]
for i, n in enumerate(notes):
    text(n, G * 8, G * 86 + i * 5.08, 1.5)

sch = [f'(kicad_sch (version 20260306) (generator "eeschema") (generator_version "10.0") (uuid "{ROOT}") (paper "A2")',
       f'(title_block (title "FC-MAGICON (Core2350B)") (rev "0.1"))',
       "(lib_symbols"] + list(lib_defs.values()) + [")"] + items + labels + noconn + texts + \
      ['(sheet_instances (path "/" (page "1")))', ")"]

with open(f"{PROJECT}.kicad_sch", "w", encoding="utf-8") as f:
    f.write("\n".join(sch) + "\n")
lib = ["(kicad_symbol_lib (version 20251024) (generator \"gen_schematic\") (generator_version \"10.0\")"]
lib += [d.replace(f'(symbol "{LIB}:', '(symbol "', 1) for d in lib_defs.values()] + [")"]
with open(f"{LIB}.kicad_sym", "w", encoding="utf-8") as f:
    f.write("\n".join(lib) + "\n")
with open("sym-lib-table", "w", encoding="utf-8") as f:
    f.write(f'(sym_lib_table (version 7)\n  (lib (name "{LIB}") (type "KiCad") '
            f'(uri "${{KIPRJMOD}}/{LIB}.kicad_sym") (options "") (descr ""))\n)\n')
print(f"部品 {len(items)} / ラベル {len(labels)} / 未接続 {len(noconn)} -> {PROJECT}.kicad_sch")
