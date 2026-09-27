"""
使い方の手順書(user_manual.pdf)を作る。本文は user_manual_body.md、表はプログラムの割り当てから作る(手で書き写さない)。
    python build_manual.py [--print]
  {{MAPPER_TABLE}} ← firmware/tools/nes_pack.py の SUPPORTED
  {{KEY_TABLE}}    ← firmware/tools/remote_pc.py の KB_NAMES・SC・KeyboardBridge.TOGGLES
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware", "tools"))
import nes_pack    # noqa: E402
import remote_pc   # noqa: E402

# マッパーの説明(対応の有無は SUPPORTED が決める。ここは説明を添えるだけ)
MAPPER_NOTE = {
    0: "バンク切り替え無し", 1: "CHR-RAM も可。ミラーリング切り替え(JP1)", 2: "CHR-RAM",
    3: "CHR 8KB 切り替え", 4: "スキャンライン割り込み(/IRQ)。ミラーリング切り替え(JP1)", 7: "1 画面ミラー(JP1)",
    87: "$6000-$7FFF の書き込みで CHR 切り替え", 184: "$6000-$7FFF の書き込みで CHR 4KB × 2",
}

# PC のスキャンコード → キーの名前(JIS 配列)
SC_NAME = {
    0x01: "Esc", 0x0E: "BackSpace", 0x1C: "Enter", 0x39: "Space", 0x1D: "Ctrl", 0x2A: "Shift", 0x36: "Shift(右)",
    0x38: "Alt", 0x29: "半角/全角", 0x0C: "-", 0x0D: "^", 0x7D: "¥", 0x1A: "@", 0x1B: "[", 0x27: ";", 0x28: ":",
    0x2B: "]", 0x33: ",", 0x34: ".", 0x35: "/", 0x73: "ろ(バックスラッシュ)", 0xE052: "Insert", 0xE047: "Home", 0xE048: "↑",
    0xE050: "↓", 0xE04B: "←", 0xE04D: "→",
}
FC_NAME = {"YEN": "¥", "KANA": "カナ", "CTR": "CTR", "GRPH": "GRPH", "LSHIFT": "SHIFT(左)", "RSHIFT": "SHIFT(右)",
           "CLRHOME": "CLR HOME", "UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→", "RETURN": "RETURN"}


def pc_key(k):
    if k in remote_pc.KeyboardBridge.TOGGLES:
        name, code = remote_pc.KeyboardBridge.TOGGLES[k]
        return f"{SC_NAME[code]}(トグル)"
    code = remote_pc.SC[k]
    if code in SC_NAME:
        return SC_NAME[code]
    for n in range(1, 9):
        if code == 0x3A + n:
            return f"F{n}"
    return k                                               # 英字・数字はそのまま


def mapper_table():
    rows = ["| 番号 | マッパー | 特徴 |", "|---|---|---|"]
    for n, name in sorted(nes_pack.SUPPORTED.items()):
        rows.append(f"| {n} | {name} | {MAPPER_NOTE.get(n, '')} |")
    return "\n".join(rows)


def key_table():
    """英字・数字は刻印どおりなので省き、それ以外(記号・特殊キー)だけを 2 列に並べる"""
    keys = [k for row in remote_pc.KB_NAMES for k in row if not (len(k) == 1 and k.isalnum())]
    keys.sort(key=lambda k: (not k.startswith("F") or len(k) != 2, k))
    pairs = [(FC_NAME.get(k, k), pc_key(k)) for k in keys]
    half = (len(pairs) + 1) // 2
    rows = ["| ファミコンのキー | PC で押されるキー | ファミコンのキー | PC で押されるキー |", "|---|---|---|---|"]
    for i in range(half):
        a = pairs[i]
        b = pairs[i + half] if i + half < len(pairs) else ("", "")
        rows.append(f"| {a[0]} | {a[1]} | {b[0]} | {b[1]} |")
    return "英字・数字(A〜Z、0〜9)は刻印どおり。それ以外:\n\n" + "\n".join(rows)


def main():
    body = open(os.path.join(HERE, "user_manual_body.md"), encoding="utf-8").read()
    md = body.replace("{{MAPPER_TABLE}}", mapper_table()).replace("{{KEY_TABLE}}", key_table())
    out_md = os.path.join(HERE, "user_manual.md")
    open(out_md, "w", encoding="utf-8", newline="\n").write(md)
    cmd = [sys.executable, os.path.join(HERE, "..", "..", "md2pdf.py"), out_md, os.path.join(HERE, "user_manual.pdf")]
    if "--print" in sys.argv:
        cmd.append("--print")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":             # build_system_spec.py が表の関数だけ使うので、読み込んだだけでは作らない
    main()
