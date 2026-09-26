# FC-MAGICON ファームウェア

pico-sdk 2.3.1、RP2350B(Waveshare Core2350B2)。ボード定義は `boards/fc_magicon.h`
(SDK の `waveshare_core2350b.h` から、UART・I2C・SPI の既定ピンを外したもの。GPIO0/1 などはバスに使っているため)。

## ビルド

```
pwsh -File build.ps1
```

- 道具は `C:\Users\Yugo\pico` に置いてある(2026-09-26 に GitHub の公式リリースから取得):
  xPack arm-none-eabi-gcc 15.2.1、CMake 4.4.3、Ninja 1.13.2、pico-sdk 2.3.1 + TinyUSB、picotool / pioasm 2.3.1。
- パスに日本語が入るとビルドできないので、`C:\Users\Yugo\pico\work\fc-magicon` にコピーしてからビルドする。
- できた `.uf2` は `out/` に入る。

## 書き込み

1. Core2350B を USB(FPC アダプター)で PC につなぐ。
2. 基板の **BOOTSEL** を押したまま **RESET** を押して離す → PC に「RP2350」ドライブが出る。
3. `out/bus_test.uf2` をそのドライブにコピーする。

## bus_test(基板が届いて最初に試す)

CPU バスの読み出し・書き込みが正しく動くかを確かめる。PPU 側(CHR)はまだ返さない(画面は出ない)。

| 動作 | 内容 |
|---|---|
| 起動直後 | バスのピンをすべて入力(プル無し)にする。本体の 5V(GPIO46)が来るまで、LED が速く点滅し、USB シリアルに `waiting for Famicom 5V` を出す |
| 本体の電源が入ったら | 250MHz で動かし、$8000-$FFFF にテスト ROM(16KB、`gen_test_rom.py`)を返す |
| テスト ROM | 矩形波 1ch で約 440Hz を鳴らし続け、ループのたびに $8000 へ書き込む |
| RP2350B | その書き込みを数え、65536 回ごとに LED を反転(約 0.5 秒ごと)。USB シリアルに毎秒の読み出し・書き込みの回数を出す |

### 立ち上げの手順

1. **モジュールを載せる前に**、テスターで +5V(J4 の 30/60 列など)と GND の間がショートしていないか確かめる。
2. モジュールを載せ、**本体に挿さずに** USB だけつなぐ。LED が速く点滅し、シリアルに `waiting for Famicom 5V` が出れば、
   RP2350B は動いていて、バスには何も出力していない。
3. 本体の電源を切った状態で挿し、電源を入れる。
   - **ピーという音が出て、LED が約 0.5 秒ごとに点滅**すれば、CPU バスの読み出しと書き込みが動いている。
   - シリアルの `writes/s` はおよそ 12 万(1 ループ 15 サイクル、CPU 1.79MHz)。
   - 音が出ない時は、本体のリセットボタンを押す(RP2350B の起動が本体の CPU に間に合わなかった可能性)。
4. うまくいかない時は、TP3(M2)・TP4(/ROMSEL)をオシロで見て、/ROMSEL が動いているか確かめる。

### 次に作るもの

- `chr_test`: PPU の /RD に応答して CHR を返し、画面を出す。TP1(/RD)と TP2(D0)で、/RD が下がってからデータが出るまでの時間を測る。
- NSF プレイヤー、マッパー(NROM → CNROM → UNROM → MMC1 → MMC3)、画面転送。
