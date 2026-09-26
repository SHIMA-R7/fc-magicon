"""
FC-MAGICON.dsn に線幅クラスを足して Freerouting で自動配線する(ふつうのpythonで実行)。
Freerouting は SHVC-SOUND/tools/freerouting のものを使う。

  ・+5V 0.8mm、VBUS_MOD 0.6mm、GND 0.5mm(両面ベタあり)、+3V3 0.4mm、音声 0.4mm、その他の信号は 0.25mm
    (2026-09-26 ユーザーの指示で電源・音声を太くした)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DSN = os.path.join(HERE, "FC-MAGICON.dsn")
SES = os.path.join(HERE, "FC-MAGICON.ses")
TOOLS = os.path.join(HERE, "..", "..", "SHVC-SOUND", "tools", "freerouting")

CLASSES = [   # (名前, 線幅um, クリアランスum, ネット)
    ("power8", 800, 200, ["/+5V"]),            # 本体→D1
    ("power6", 600, 200, ["/VBUS_MOD"]),       # モジュールの電源
    ("gnd5", 500, 200, ["/GND"]),              # GND は両面ベタもある
    ("power4", 400, 200, ["/+3V3"]),           # U2 と J5
    ("audio4", 400, 200, ["/SOUND_IN", "/SOUND_OUT", "/EXP_AUDIO_RC", "/EXP_AUDIO_VR", "/LOUT", "/LINE"]),
]


def klass(name, width, clearance, nets):
    return (f"(class {name} " + " ".join(f'"{n}"' if re.search(r"[^\w+]", n) else n for n in nets) +
            "\n      (circuit\n        (use_via \"Via[0-1]_600:300_um\")\n      )\n"
            f"      (rule\n        (width {width})\n        (clearance {clearance})\n      )\n    )")


text = open(DSN, encoding="utf-8").read()
m = re.search(r"\(class kicad_default(.*?)\(circuit", text, re.S)
nets = re.findall(r'"[^"]*"|\S+', m.group(1))
plain = [n.strip('"') for n in nets]
special = {n for _, _, _, ns in CLASSES for n in ns}
rest = [n for n in plain if n not in special]
blocks = [klass("kicad_default", 250, 200, rest)]
for name, w, c, ns in CLASSES:
    present = [n for n in ns if n in plain]
    if present:
        blocks.append(klass(name, w, c, present))
end = text.index(")\n    )", text.index("(rule", m.end())) + len(")\n    )")
text = text[:m.start()] + "\n    ".join(blocks) + text[end:]
open(DSN, "w", encoding="utf-8").write(text)

java = next(os.path.join(TOOLS, d, "bin", "java.exe") for d in os.listdir(TOOLS) if d.startswith("jdk"))
jar = os.path.join(TOOLS, "freerouting-2.4.1.jar")
cmd = [java, "-jar", jar, "-de", DSN, "-do", SES, "-mp", "40", "--gui.enabled=false"] + sys.argv[1:]
print(" ".join(cmd), flush=True)
sys.exit(subprocess.call(cmd))
