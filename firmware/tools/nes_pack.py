"""
.nes を magicon のフラッシュの ROM 置き場(8MB 目)に書く形にする。
    python nes_pack.py game.nes out.bin
  形式: "FCMG" + 長さ + バイトの合計 + 予備(各4バイト、リトルエンディアン)の後ろに .nes をそのまま。
  ヘッダーを読んで、マッパー・大きさ・magicon で動くかを表示する(動かない時は終了コード 1)。
  書き込みは load_rom.ps1(picotool)から。
"""
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


def main():
    src, dst = sys.argv[1], sys.argv[2]
    if src == "--remote":               # 画面転送(リモートデスクトップ)モードで起動する印
        data = b"FCRD"
        open(dst, "wb").write(struct.pack("<4sIII", b"FCMG", len(data), sum(data) & 0xFFFFFFFF, 0) + data)
        print(f"画面転送モード -> {dst}")
        return
    data = open(src, "rb").read()
    if data[:5] == b"NESM\x1a":
        if not nsf(src, data):
            sys.exit(1)
        open(dst, "wb").write(struct.pack("<4sIII", b"FCMG", len(data), sum(data) & 0xFFFFFFFF, 0) + data)
        print(f"  -> {dst} ({len(data) + 16} バイト)")
        return
    if data[:4] != b"NES\x1a":
        sys.exit(f"{src}: iNES / NSF ファイルではない")
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
    if not ok:
        sys.exit(1)
    open(dst, "wb").write(struct.pack("<4sIII", b"FCMG", len(data), sum(data) & 0xFFFFFFFF, 0) + data)
    print(f"  -> {dst} ({len(data) + 16} バイト)")


if __name__ == "__main__":
    main()

