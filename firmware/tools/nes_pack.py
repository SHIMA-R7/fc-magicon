"""
.nes を magicon のフラッシュの ROM 置き場(8MB 目)に書く形にする。
    python nes_pack.py game.nes out.bin
  形式: "FCMG" + 長さ + バイトの合計 + 予備(各4バイト、リトルエンディアン)の後ろに .nes をそのまま。
  ヘッダーを読んで、マッパー・大きさ・magicon で動くかを表示する(動かない時は終了コード 1)。
  書き込みは load_rom.ps1(picotool)から。

    python nes_pack.py --library out.bin [--add-remote] フォルダーやファイル...
  複数の ROM を 1 つにまとめる(ゲーム選択メニュー)。フォルダーなら中の .nes / .nsf を全部。動かない ROM は飛ばす。
  形式: "FCLB" + 項目の数 + 全体の長さ + 予備(16 バイト)、項目 64 バイト × 数(題名 48 + 位置 + 長さ + 合計 + 予備)、
        その後ろに中身(1 本だけの時と同じ .nes / .nsf / "FCRD")。位置は置き場の先頭から。8MB まで、127 本まで。
  題名はファイル名(大文字)、NSF は曲集の題名。同じフォルダーの titles.txt に「ファイル名=題名」と書くとそれを使う。
  --add-remote で「REMOTE DESKTOP」(画面転送モード)も項目に入れる。
"""
import os
import struct
import sys

SUPPORTED = {0: "NROM", 1: "MMC1", 2: "UxROM", 3: "CNROM", 4: "MMC3", 7: "AxROM", 87: "Jaleco J87", 184: "Sunsoft-1"}
ROM_MAX = 384 * 1024


EXP = ["VRC6", "VRC7", "FDS", "MMC5", "N163", "Sunsoft 5B", "VT02+"]


def nsf(src, data):
    """NSF の情報を表示して、magicon で鳴らせるかを返す"""
    s = lambda o: data[o:o + 32].split(b"\0")[0].decode("ascii", "replace")
    songs, start = data[6], data[7]
    load, init, play = (data[i] | data[i + 1] << 8 for i in (8, 10, 12))
    banks = data[0x70:0x78]
    exp = [n for i, n in enumerate(EXP) if data[0x7B] & (1 << i)]
    speed = data[0x6E] | data[0x6F] << 8
    print(f"{src}")
    print(f"  NSF 「{s(0x0E)}」 {s(0x2E)} / {s(0x4E)}")
    print(f"  {songs} 曲(最初は {start})  load ${load:04X} init ${init:04X} play ${play:04X}"
          f"{'  バンク切り替えあり' if any(banks) else ''}  {len(data) - 0x80} バイト")
    ok = True
    if not any(banks) and load < 0x8000:
        print("  ! load が $8000 より下(まだ対応していない)")
        ok = False
    if any(banks) and (load & 0xFFF) + len(data) - 0x80 > ROM_MAX:
        print(f"  ! {ROM_MAX // 1024}KB を超える")
        ok = False
    if exp:
        print(f"  (拡張音源 {', '.join(exp)} は、まだ鳴らない。本体の 2A03 の音だけ出る)")
    if speed and abs(speed - 16639) > 200:
        print(f"  (再生の間隔 {speed}us。magicon は VBlank(約 16639us)ごとに呼ぶので、テンポが変わる)")
    if data[0x7A] & 1 and not data[0x7A] & 2:
        print("  (PAL 用の NSF。日本のファミコンでは少し速く鳴る)")
    return ok


def check(src, data):
    """表示して、magicon で動くかを返す"""
    if data[:5] == b"NESM\x1a":
        return nsf(src, data)
    if data[:4] != b"NES\x1a":
        print(f"{src}\n  ! iNES / NSF ファイルではない")
        return False
    return nes(src, data)


LIB_SPACE, LIB_MAX, ENTRY = 8 * 1024 * 1024, 127, 64
TITLE_LEN = 28                           # メニューに出る長さ(gen_menu_driver.py)


def ascii_title(s):
    t = "".join(c if " " <= c < "\x7f" else "?" for c in s).strip()
    return t[:47] or "?"


def library(dst, args):
    add_remote = "--add-remote" in args
    paths = []
    for p in (a for a in args if a != "--add-remote"):
        if os.path.isdir(p):
            paths += sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith((".nes", ".nsf")))
        else:
            paths.append(p)
    titles = {}
    for d in {os.path.dirname(os.path.abspath(p)) for p in paths}:
        tf = os.path.join(d, "titles.txt")
        if os.path.exists(tf):
            for line in open(tf, encoding="utf-8"):
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    titles[k.strip().lower()] = v.strip()
    items, skipped = [], []
    for p in paths:
        data = open(p, "rb").read()
        if not check(p, data):
            skipped.append(os.path.basename(p))
            continue
        name = os.path.basename(p)
        if name.lower() in titles:
            title = titles[name.lower()]
        elif data[:5] == b"NESM\x1a":
            title = data[0x0E:0x2E].split(b"\0")[0].decode("ascii", "replace") or os.path.splitext(name)[0]
        else:
            title = os.path.splitext(name)[0].replace("_", " ").upper()
        items.append((ascii_title(title), data))
    items.sort(key=lambda it: it[0].upper())
    if add_remote:
        items.append(("REMOTE DESKTOP", b"FCRD"))
    if not items:
        sys.exit("入れられる ROM が 1 本も無い")
    if len(items) > LIB_MAX:
        sys.exit(f"{len(items)} 本は多過ぎる({LIB_MAX} 本まで)")
    head = bytearray(16 + ENTRY * len(items))
    body = bytearray()
    off = (len(head) + 15) & ~15
    for i, (title, data) in enumerate(items):
        pos = off + len(body)
        struct.pack_into("<48sIIII", head, 16 + ENTRY * i, title.encode("ascii"), pos, len(data),
                         sum(data) & 0xFFFFFFFF, 0)
        body += data + bytes((-len(data)) % 16)
    total = off + len(body)
    if total > LIB_SPACE:
        sys.exit(f"合計 {total / 1048576:.1f}MB は大き過ぎる(8MB まで)")
    struct.pack_into("<4sIII", head, 0, b"FCLB", len(items), total, 0)
    open(dst, "wb").write(bytes(head) + bytes(off - len(head)) + bytes(body))
    print(f"\nライブラリ {len(items)} 本、{total / 1024:.0f}KB -> {dst}")
    for title, _ in items:
        cut = "" if len(title) <= TITLE_LEN else f"(メニューでは {TITLE_LEN} 文字まで)"
        print(f"  {title}{cut}")
    if skipped:
        print(f"入れなかった(動かない): {', '.join(skipped)}")


def main():
    src, dst = sys.argv[1], sys.argv[2]
    if src == "--library":
        library(dst, sys.argv[3:])
        return
    if src == "--remote":               # 画面転送(リモートデスクトップ)モードで起動する印
        data = b"FCRD"
        open(dst, "wb").write(struct.pack("<4sIII", b"FCMG", len(data), sum(data) & 0xFFFFFFFF, 0) + data)
        print(f"画面転送モード -> {dst}")
        return
    data = open(src, "rb").read()
    if not check(src, data):
        sys.exit(1)
    open(dst, "wb").write(struct.pack("<4sIII", b"FCMG", len(data), sum(data) & 0xFFFFFFFF, 0) + data)
    print(f"  -> {dst} ({len(data) + 16} バイト)")


def nes(src, data):
    """.nes の情報を表示して、magicon で動くかを返す"""
    nes2 = (data[7] & 0x0C) == 0x08
    prg_n, chr_n = data[4], data[5]
    if nes2:
        prg_n |= (data[9] & 0x0F) << 8
        chr_n |= (data[9] & 0xF0) << 4
    mapper = (data[6] >> 4) | (data[7] & 0xF0)
    prg, chr_ = prg_n * 0x4000, chr_n * 0x2000
    mir = "4画面" if data[6] & 8 else ("垂直" if data[6] & 1 else "水平")
    print(f"{src}")
    print(f"  マッパー {mapper} ({SUPPORTED.get(mapper, '未対応')})  PRG {prg // 1024}KB  "
          f"CHR {'RAM 8KB' if chr_ == 0 else f'{chr_ // 1024}KB'}  ミラー {mir}"
          f"{'  バッテリー' if data[6] & 2 else ''}{'  NES 2.0' if nes2 else ''}")
    ok = True
    if mapper not in SUPPORTED:
        print("  ! このマッパーはまだ対応していない")
        ok = False
    if prg + chr_ > ROM_MAX:
        print(f"  ! PRG + CHR が {ROM_MAX // 1024}KB を超える(SRAM に入らない)")
        ok = False
    if data[6] & 2:
        print("  (バッテリーバックアップのセーブは、まだ電源を切ると消える)")
    return ok


if __name__ == "__main__":
    main()

