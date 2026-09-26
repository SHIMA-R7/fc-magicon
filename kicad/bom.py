"""ネットリスト(FC-MAGICON.net)から部品表を作る → bom.csv(ふつうのpythonで実行)。
回路図に無い物(モジュール本体、ソケット類)も最後に足す。
"""
import csv
import os
import re
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
net = open(os.path.join(HERE, "FC-MAGICON.net"), encoding="utf-8").read()

# 部品ごとの説明(型番・買うときの注意)
PART = {
    "U2": ("74LVC245 DIP-20", "SN74LVC245AN。5V入力を3.3Vへ。74HC/HCT245 では代用不可(5V入力に耐えない)"),
    "Q1": ("2SC1815", "TO-92 NPN。足は平らな面から E-C-B。他の小信号NPNでも可(足順に注意)"),
    "D1": ("1N4001〜1N4007(ショットキー 1A があればそちら)", "本体5V→モジュール。USB給電時の逆流防止。省略不可"),
    "J2": ("PJ-324M", "3.5mm ステレオジャック(SHVC-SOUND-ESP32 と同じ)"),
    "SW1": ("タクトスイッチ 6mm", "BOOTSEL"), "SW2": ("タクトスイッチ 6mm", "RESET(RP2350のRUN)"),
    "J3": ("ピンヘッダー 1x3", "SWD(debugprobe の Pico 用)"),
    "J4": ("ピンヘッダー or ピンソケット 2x30", "カセット60ピンのブレイクアウト。必要な時だけでもよい"),
    "J5": ("ピンヘッダー 2x8", "デバッグ用(内部信号)"),
    "C1": ("10µF 電解", "16V以上、φ5 ピッチ2mm"), "C4": ("10µF 電解", "φ5 ピッチ2mm。+側=SOUND_OUT(四角パッド)。ライン出力の直流カット。1µFフィルムでも可"),
    "C2": ("100nF セラミック", "U2 のパスコン"), "C3": ("10nF セラミック", "PWM の RC フィルタ"),
    "R1": ("0Ω(ジャンパー線でも可)", "CIRAM /CE ← /A13"), "R7": ("0Ω(ジャンパー線でも可)", "音声 45→46番の素通し"),
    "R6": ("10kΩ(未実装)", "本体に /IRQ のプルアップが無い時だけ付ける"),
    "R8": ("47kΩ", "拡張音源を46番に混ぜる抵抗(VR1 の中点から)"),
    "VR1": ("半固定抵抗 100kΩ KOA KVSF637AC104", "拡張音源の音量。上面調整、足 ①③ 5.0mm・② は 5.0mm 上"),
    "J6": ("ピンヘッダー 1x4(任意)", "USB の予備ランド(5V/D-/D+/GND)。FPC 側と同時に機器をつながない"),
}
rows = OrderedDict()
for ref, value, fp in re.findall(r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)', net):
    if ref == "J1" or ref.startswith(("P", "JP", "TP")):
        continue                     # 基板そのもの(端子・ジャンパー・テストポイント)と、モジュール用の穴
    name, note = PART.get(ref, (value if not ref.startswith("R") else value + "Ω", ""))
    if ref.startswith("R") and ref not in PART:
        name = f"{value}Ω 1/4W"
    key = (name, fp.split(":")[-1], note)
    rows.setdefault(key, []).append(ref)

extra = [
    ("Waveshare Core2350B2", 1, "U1", "RP2350B、2MB PSRAM。付属のFPC-USBアダプターで PC とつなぐ"),
    ("ピンソケット 2x8(2.54mm)", 4, "P1-P4", "Core2350B を載せる。モジュール側には 2x8 ピンヘッダー4個"),
    ("ピンヘッダー 2x8(2.54mm)", 4, "(モジュール側)", "Core2350B の裏に付ける"),
    ("ICソケット DIP-20", 1, "(U2)", "任意"),
    ("PCB 90x65.8mm 2層 1.2mm", 1, "", "金メッキ端子(Gold fingers)、差し込み側 45°面取り"),
]


def refsort(r):
    m = re.match(r"([A-Z]+)(\d+)", r)
    return (m.group(1), int(m.group(2))) if m else (r, 0)


out = [("部品", "数", "記号", "フットプリント", "メモ")]
for (name, fp, note), refs in sorted(rows.items(), key=lambda kv: refsort(sorted(kv[1], key=refsort)[0])):
    refs = sorted(refs, key=refsort)
    out.append((name, len(refs), ",".join(refs), fp, note))
for name, n, refs, note in extra:
    out.append((name, n, refs, "", note))
with open(os.path.join(HERE, "bom.csv"), "w", encoding="utf-8-sig", newline="") as f:
    csv.writer(f).writerows(out)
for r in out:
    print(" | ".join(str(c) for c in r))
