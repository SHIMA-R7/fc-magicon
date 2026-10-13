# 固定CHRでも崩れる画面のネット調査

調査日: 2026-10-12。NESdevの仕様と開発者の実測、Raspberry Pi/TIの一次資料、FC PICO公開ソースを確認。今回と同じ回路・配線・症状を再現して修理した記事は見つかっていない。以下は症状に合う根拠と、検証すべき仮説。今回は調査記録のみで、実機のファームは書き換えていない。

## 最も重要な仮説: CHRデータが読出しの瞬間に届いていない

[NESdev Open bus behavior](https://www.nesdev.org/wiki/Open_bus_behavior)は、PPUの外部ビデオメモリバスがアドレス下位と多重化されているため、メモリが応答しない読出しでは通常アドレス下位が返ると説明している。

固定FFの2つのパターン面が正しくPPUへ届けば、タイル内部は色番号3で塗りつぶされ、ネームテーブルが乱れても文字形状にはならない。ただしパレット属性で領域の色は変わる。固定FFなのに文字状の細かい模様が残る今回の表示は、オープンバス読出しと整合する。画像だけで確定はできず、A13による選択誤り、配線/接触不良、GPIO出力方向、出力レベル、開始/解除の時間も候補。

CPU側の連番不一致もあるため、PPUだけ正常化すれば直るという保証もない。連番不一致は書込み捕捉の誤りだけでなく、CPUのROM読出しが時々違う命令/データになった場合にも起き得る。

関連する一次事例: [NES CHR glitching](https://forums.nesdev.org/viewtopic.php?t=13431)。回答者が表示を不安定なオープンバスとして指摘した例。最終原因は別型番に偽装されたEPROMと空のアドレス領域だった。今回にその部品原因を当てはめるのではなく、「似た表示がCHR未応答でも起きる」点が参考になる。

## 同種のRP2350実装ではデータを先に用意する

[FC PICO作者のPIO](https://github.com/impact-soft/fc-pico/blob/main/tutorial_project/tuto1_hw/sys/pio/fcppu.pio)では、読出しストローブ後にchip selectを確認し、PIO内部IRQで方向制御SMと連携してOUTする。[DMA実装](https://github.com/impact-soft/fc-pico/blob/main/tutorial_project/tuto1_hw/sys/rp_dma.cpp)はPIO TX FIFOへDREQでデータを先行供給する。ARM CPUが1回の読出しごとにデータを計算して返す構成ではない。

こちらの方式はストローブ検出→RX FIFO→ARM割込みまたはポーリング→データ作成→TX FIFO→PIO出力と往復する。handler_cycles=24などはIRQに入った後の一部処理で、IRQ受付・FIFO待ち・PIO OUT・パッドの立上りを含む総応答時間ではない。短いhandler値でも期限を満たす証明にはならない。

FC PICOは独立PRG ROMと事前描画したCHRストリームを使い、通常マッパーの任意アドレスROM供給とは違う。DMAストリーム方式をそのまま移植すれば全ゲーム対応になるわけではない。

## 次に行う診断（最優先）

固定FFをARMやFIFO返答待ちを通さず、PIOだけで生成する。

1. /RDがLowになり、A13がLow（パターン領域）ならFFをデータ線へ出す。
2. /RDがHighになれば8本を入力へ戻す。
3. A13がHighなら本体CIRAMと競合しないよう出さない。
4. この試験でも文字状の模様が残るなら、配線・A13選択・GPIO出力・レベル・バス解放を優先して確認。
5. 固定パターンが正しくなるなら、ARM/FIFO往復と応答期限を優先して見直す。

これは切り分けの提案で、まだ実装/実機確認していない。信号のサンプリング、GPIOの同期と立上りも残るので、PIOだけなら必ず正常という断定はしない。固定テストの成功も通常ROMのアドレス捕捉の正しさまでは証明しない。

## レベルシフタの遅延

[TI SN74LVC245A仕様書](https://www.ti.com/lit/ds/symlink/sn74lvc245a.pdf)は3.3Vの規定条件で最大tpd=6.3ns。部品・負荷・温度の条件付き数値であり、実装配線の実測値ではない。

総読出し時間に対しては数%程度でも、今回のAD0–7直結と/RDのU2経由の差は無視できない。PIOのアドレス監視は2命令=8ns単位なので、数nsの差がアドレス/データ切替境界で採用サンプルを変える。ただし固定FFも崩れたことから、このアドレス誤読だけでは全症状を説明しにくい。/RDを遅く検出することは出力開始も遅くし、立上り解除側の遅れも別に評価が必要。

AD線の「同期段を含めた過去サンプル」を使う案はアドレス捕捉対策。単に現在の/RD後にnopを足してADを読むと、さらに遅い値を拾い得る。レベルシフタのバイパス/取り外しは電圧条件を別に確認し、現段階では行わない。

## CPU書込みとM2のタイミング

[2A03書込みの実測](https://forums.nesdev.org/viewtopic.php?p=244126)では、ある実機のデータ確定はM2立上り後約100ns、M2とR/Wの切替にもずれがあった。[FPGAカートリッジ開発例](https://forums.nesdev.org/viewtopic.php?start=30&t=23078)には、M2立下り後40ns遅らせた捕捉で長時間動作した報告がある。個々の実機・回路での結果で、40nsを一般解として採用しない。

[PRG RAM circuit](https://www.nesdev.org/wiki/PRG_RAM_circuit)によればM2→ROMSELのデコードにも最大約33nsのずれがある。現在の80ns待ちはこの問題を避ける意図だが、データ確定や書込み時の返答待ちとは別。

現在のCPU PIOはARMからのACKを受けてからM2立下りでデータを取る。ACKが遅ければ意図したエッジの近傍を外す可能性がある。立下り基準の前後を比較し、できれば書込みデータの捕捉をARM返答待ちから独立させるのが次の候補。連番の取得誤りと実行誤りを分けるため、既知データのPPUレジスタ書込みを捕捉してチェックすることも必要。

## SRAM配置とGPIO同期

[bitcoresのSingle Chip Cartridge開発記録](https://forums.nesdev.org/viewtopic.php?start=120&t=9342)では、copy-to-RAM指定だけでは必要なコード全体がRAMへ入らず、ビルド方式/配置で応答が変わった。対象はRP2040のPRG主体実装で、87KBという作者のしきい値は今回へ流用しない。こちらもヘルパー、IRQベクタ、関数配置、データと命令のSRAM競合をELFで確認する価値がある。

[RP2350入力遅延に対するRaspberry Piエンジニアの回答](https://forums.raspberrypi.com/viewtopic.php?t=377693)は入力同期の遅延を指摘し、E9とは別と説明。[RP2350仕様書](https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf)のPIO同期段は2クロック。250MHzなら同期段部分だけで8ns。フォーラムの30ns等の測定を今回の条件へそのまま加算しない。非同期入力の同期バイパスには別の問題があり、全GPIOを一括で外すことは最初の対策にしない。

picotoolで今回のチップはA4と確認済み。[メーカーのA4変更通知](https://pip-assets.raspberrypi.com/categories/1263-pcn/documents/RP-008771-CC/RP235x-A4-stepping-PCN)ではE9修正を示す。古いA2のGPIOラッチングを今回の主因と決めつけない。

## 起動時のバス駆動とD1（追加依頼）

[CPU_ALL](https://www.nesdev.org/wiki/CPU_ALL)はCPUのリセット中のHi-Z状態を説明する一方、[PPU power up state](https://www.nesdev.org/wiki/PPU_power_up_state)ではファミコンのPPUはCPUと同時にはリセットされず、起動が先行するとされる。[NES power-up/resetの議論](https://forums.nesdev.org/viewtopic.php?p=224664)ではPPUアドレスバスの駆動とCPUリセット時のHi-Zを区別する。

したがって「起動時に全バスが一斉に駆動される」とは言えないが、「CPUがリセット中だからカセット端子の全信号がHi-Z」とも言えない。NEWファミコンの[機種資料](https://www.nesdev.org/wiki/Family_Computer)も本体RESETはCPUだけをリセットすると説明する。個々の端子の電源立上り中の電圧・駆動開始時刻は今回測っていない。

D1の再実装可否は、このバスの説明だけでは決まらない。現在の回路ではFC5V→D1→VBUS_MOD→FPC USB VBUSという電源経路があり、USB側への逆流/二電源の接続を別に評価する必要がある。RP2350の5V入力許容もIOVDDが成立している条件付きで、電源の立上り順を無条件に許すものではない。[メーカー資料の条件を議論する公式フォーラム](https://forums.raspberrypi.com/viewtopic.php?p=2377163)。現時点ではD1実装を安全と判断していない。
