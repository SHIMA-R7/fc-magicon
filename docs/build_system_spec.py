"""
FC-MAGICON の総合仕様書(system_spec.pdf)を作る。本文は system_spec_body.md(手で書く)、表はデータから作る。
    python build_system_spec.py [--print]
  {{HW_DETAIL}}      ← hardware_spec_body.md の 2〜11 章(ハードウェアの詳しい所。同じことを 2 か所に書かない)
  {{FIRMWARE_TABLE}} ← firmware/out/*.uf2(大きさ)
  {{MAPPER_TABLE}}   ← tools/nes_pack.py の SUPPORTED(build_manual.py の表)
  {{KEY_TABLE}}      ← tools/remote_pc.py の割り当て(build_manual.py の表)
  {{REMOTE_OPTIONS}} ← tools/remote_pc.py の build_parser()
  {{FLASH_MAP}}      ← magicon/main.c・cart.h・tools/nes_pack.py の定数
  {{NSF_MAP}} {{REMOTE_MAP}} {{MENU_MAP}} ← gen_*_driver.py が作ったヘッダーの #define
  {{BOM}}            ← kicad/bom.csv
  {{PIN_TABLES}}     ← _tables.md(kicad/gen_spec_tables.py がネットリストから作る)
  {{CODE_SIZE}}      ← ソースの行数
目次とページ番号は md2pdf.py([[TOC]] と --page-numbers)。
"""
import csv
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FW = os.path.join(ROOT, "firmware")
sys.path.insert(0, os.path.join(FW, "tools"))
sys.path.insert(0, HERE)
import nes_pack                                          # noqa: E402
import remote_pc                                         # noqa: E402
from build_manual import key_table, mapper_table         # noqa: E402


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def hw_detail():
    """hardware_spec_body.md の「## 2.」〜「## 11.」を、この書類の 3 章の節(### 3.n)に直す"""
    src = read("docs", "hardware_spec_body.md")
    part = src[src.index("## 2. "):src.index("## 12. ")]
    out, n = [], 0
    for ln in part.splitlines():
        m = re.match(r"^## \d+\. (.*)", ln)
        if m:
            n += 1
            out.append(f"### 3.{n} {m.group(1)}")
            continue
        m = re.match(r"^### [\d.]+ (.*)", ln)
        if m:
            out.append(f"**{m.group(1)}**")               # 4 段目の見出しは太字の行にする
            continue
        # 元の書類の「(7章)」などは、この書類の 3 章の節(元の k 章 → 3.(k-1))に直す
        out.append(re.sub(r"(\d+)章", lambda mm: f"3.{int(mm.group(1)) - 1}", ln))
    return "\n".join(out), n


FIRMWARE_NOTE = {
    "bus_test": ("最初の動作確認 1", "CPU バスの読み書き。テスト ROM が 440Hz を鳴らし、$8000 への書き込みを数えて LED を点滅"),
    "chr_test": ("最初の動作確認 2", "PPU の読み出しに CHR を返す。4 色の縦縞と 8 ドットの格子が出れば下位アドレスの読み取りが正しい"),
    "magicon": ("ふだん使う", "ゲーム・NSF・画面転送・メニュー。USB はデバイス(PC 直結、USB シリアル、picotool の自動書き込み)"),
    "magicon_wifi": ("Wi-Fi の画面転送", "magicon と同じ。USB をホストにして J6 の ESP32-C6 とやりとりする。USB シリアル無し"),
    "usb_test": ("試験", "USB 直結の速さを測る(ファミコン無し)。受けた画面を捨て、FCIN を 60 回/秒返す"),
    "host_test": ("試験", "USB ホストで ESP32-C6 から受ける速さを測る(ファミコン無し)。UART0(GPIO0)にログ"),
}


def firmware_table():
    rows = ["| ファイル | 大きさ | 用途 | 中身 |", "|---|---:|---|---|"]
    for p in sorted(glob.glob(os.path.join(FW, "out", "*.uf2"))):
        name = os.path.splitext(os.path.basename(p))[0]
        use, what = FIRMWARE_NOTE.get(name, ("", ""))
        rows.append(f"| `{name}.uf2` | {os.path.getsize(p) // 1024}KB | {use} | {what} |")
    return "\n".join(rows)


def options_table():
    rows = ["| オプション | 内容 |", "|---|---|"]
    for act in remote_pc.build_parser()._actions:
        if not act.option_strings or act.dest == "help":
            continue
        opt = act.option_strings[-1] + (f" {act.metavar}" if act.metavar else "")
        if act.choices:
            opt += " {" + " / ".join(act.choices) + "}"          # | は表の区切りと取り違えられるので使わない
        rows.append(f"| `{opt}` | {act.help or ''} |")
    return "\n".join(rows)


def const(path, name):
    m = re.search(rf"#define\s+{name}\s+\(?\s*(0x[0-9A-Fa-f]+|\d+)u?", read(*path))
    return int(m.group(1), 0)


def flash_map():
    slot = const(("firmware", "magicon", "main.c"), "ROM_SLOT")
    space = const(("firmware", "magicon", "main.c"), "LIB_SPACE")
    items = const(("firmware", "magicon", "cart.h"), "LIB_MAX_ITEMS")
    rom_max = 384 * 1024 if "384u * 1024u" in read("firmware", "magicon", "cart.h") else 0
    rows = ["| 番地(フラッシュの先頭から) | 大きさ | 中身 |", "|---|---:|---|",
            f"| 0x000000 | {slot // 1048576}MB | ファームウェア(uf2 で書く。magicon は約 200KB) |",
            f"| 0x{slot:06X} | {space // 1048576}MB | ROM 置き場: 1 本(`FCMG`)かライブラリ(`FCLB`、{items} 本まで) |",
            "", f"- XIP の番地では 0x{0x10000000 + slot:08X}。`load_rom.ps1` は picotool で `-o 0x{0x10000000 + slot:08X}` に書く。",
            f"- 1 本の大きさは PRG + CHR で {rom_max // 1024}KB まで(RP2350 の SRAM に写して返すため)。ライブラリ全体は {space // 1048576}MB まで。",
            f"- ライブラリの項目は {nes_pack.ENTRY} バイト(題名 48 + 位置 4 + 長さ 4 + 合計 4 + 予備 4)、題名はメニューで {nes_pack.TITLE_LEN} 文字まで。"]
    return "\n".join(rows)


def define_table(header, notes):
    src = read("firmware", "magicon", header)
    rows = ["| 名前 | 値 | 意味 |", "|---|---|---|"]
    for name, val in re.findall(r"#define\s+(\w+)\s+(0x[0-9A-Fa-f]+)", src):
        if name in notes:
            rows.append(f"| `{name}` | {val} | {notes[name]} |")
    return "\n".join(rows)


NSF_NOTES = {"NSFD_BASE": "ドライバーの先頭($5000-$5FFF はカセットの SRAM)", "NSFD_NT": "画面の土台(ドライバーの先頭から)",
             "NSFD_PARAM": "ファームが書く値: 曲数・最初の曲・バンクの初期値(先頭から)", "NSFD_RESET": "リセットベクターが指す番地",
             "NSFD_NMI": "NMI(PLAY を呼び、パッドを読む)", "NSFD_IRQ": "IRQ(何もしない)",
             "NSFD_INIT_OPERAND": "INIT への JMP の番地の置き場(ファームが書く)", "NSFD_PLAY_OPERAND": "PLAY への JMP の番地の置き場"}
REMOTE_NOTES = {"RD_PAL": "パレット 32 バイト(VBlank ごとに 6502 が PPU へ写す)", "RD_ATTR": "属性テーブル 64 バイト",
                "RD_OAM": "スプライト(カーソル)256 バイト。OAM DMA の元", "RD_IO": "6502 が書く入力: +0 パッド、+1〜+9 キーボード、+15 フレームの数"}
MENU_NOTES = {"MENUD_COUNT": "項目の数(PRG の先頭から)", "MENUD_PTR_LO": "題名の番地の下位の表", "MENUD_PTR_HI": "同じく上位",
              "MENUD_TITLES": "題名(28 文字ずつ)", "MENUD_NT": "画面の土台 1024 バイト", "MENUD_CODE": "メニューのプログラム($C000)",
              "MENUD_SELECT": "選んだ番号を 6502 が書く番地(ファームが見て再起動)", "MENUD_MAX_ITEMS": "項目の上限"}


def bom():
    rows = list(csv.reader(open(os.path.join(ROOT, "kicad", "bom.csv"), encoding="utf-8-sig")))
    out = ["| 部品 | 数 | 記号 | フットプリント | メモ |", "|---|---:|---|---|---|"]
    out += ["| " + " | ".join(c.replace("|", "/") for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)


CODE_GROUPS = [
    ("カセット(RP2350、C)", ["firmware/magicon/*.c", "firmware/magicon/*.pio", "firmware/bus_test/*.c", "firmware/chr_test/*.c",
                             "firmware/*/*.pio", "firmware/usb_test/*.c", "firmware/host_test/*.c"]),
    ("6502 プログラムを作る Python", ["firmware/magicon/gen_*.py", "firmware/bus_test/*.py", "firmware/chr_test/*.py",
                                      "firmware/tools/asm6502.py"]),
    ("Wi-Fi ブリッジ(ESP32-C6)", ["firmware/wifi_bridge/*.ino"]),
    ("PC のアプリ・道具(Python / PowerShell)", ["firmware/tools/*.py", "firmware/*.ps1"]),
    ("PC の試験台(C、agnes を除く)", ["firmware/sim/sim.c", "firmware/sim/apu.c", "firmware/sim/*.py"]),
    ("基板(KiCad を動かす Python)", ["kicad/*.py", "kicad/*.ps1"]),
    ("書類を作るスクリプト", ["docs/*.py"]),
]


def code_size():
    rows = ["| まとまり | ファイル | 行 |", "|---|---:|---:|"]
    seen = set()
    for label, pats in CODE_GROUPS:
        files = {os.path.normpath(f) for p in pats for f in glob.glob(os.path.join(ROOT, p))} - seen   # 先のまとまりで数えたものは除く
        seen |= files
        lines = sum(len(open(f, encoding="utf-8", errors="replace").read().splitlines()) for f in files)
        rows.append(f"| {label} | {len(files)} | {lines:,} |")
    return "\n".join(rows) + "\n\n(生成したヘッダー(`*_driver.h` など)、agnes、ビルド済みのファイルは数えていない)"


def main():
    body = read("docs", "system_spec_body.md")
    hw, _ = hw_detail()
    rep = {
        "{{HW_DETAIL}}": hw, "{{FIRMWARE_TABLE}}": firmware_table(), "{{MAPPER_TABLE}}": mapper_table(),
        "{{KEY_TABLE}}": key_table(), "{{REMOTE_OPTIONS}}": options_table(), "{{FLASH_MAP}}": flash_map(),
        "{{NSF_MAP}}": define_table("nsf_driver.h", NSF_NOTES), "{{REMOTE_MAP}}": define_table("remote_driver.h", REMOTE_NOTES),
        "{{MENU_MAP}}": define_table("menu_driver.h", MENU_NOTES), "{{BOM}}": bom(),
        "{{PIN_TABLES}}": read("docs", "_tables.md"), "{{CODE_SIZE}}": code_size(),
    }
    for k, v in rep.items():
        if k not in body:
            print("本文に無い:", k)
        body = body.replace(k, v)
    left = re.findall(r"\{\{\w+\}\}", body)
    if left:
        sys.exit(f"置き換えていない: {left}")
    out_md = os.path.join(HERE, "system_spec.md")
    open(out_md, "w", encoding="utf-8", newline="\n").write(body)
    cmd = [sys.executable, os.path.join(ROOT, "..", "md2pdf.py"), out_md, os.path.join(HERE, "system_spec.pdf"), "--page-numbers"]
    if "--print" in sys.argv:
        cmd.append("--print")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
