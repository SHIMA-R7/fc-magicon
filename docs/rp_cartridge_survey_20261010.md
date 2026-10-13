# RP系カートリッジ調査 — 国内ファミコン／NES優先

調査日: 2026-10-10。twifork（twikitによるX検索）、GitHub公開リポジトリ、作者のNESdev投稿、Redditを横断。完成品だけでなく実機試作、基板のみ、実装未確認の計画も収録する。作者の説明と、こちらがソースから確認できた範囲を区別する。

## 最も参考になる国内3系統

| 開発者・系統 | RP・構成 | 到達点／制約 | 一次資料 |
|---|---|---|---|
| ゆのみファクトリー @yunomifactory／名称未確認の自作カセット | RP2350B×2、CPUバス用とPPUバス用を分離 | 実機デモあり。mapper 0・30・独自拡張。汎用マッパー網羅ではない。回路・ファーム公開先は今回未確認 | [方式の説明](https://x.com/yunomifactory/status/2108593567061151812)、[USBからNES書込み](https://x.com/yunomifactory/status/2107668156538143223) |
| IMPACT SOFT @HD64180／FC PICO | RP2350、現行公開版はPPU側へ描画結果を供給。CPU側は別の6502起動ROM | 販売・サンプルソースあり。通常NES ROM用の汎用マジコンとは設計目的が違う | [公開コード](https://github.com/impact-soft/fc-pico)、[作者配布ページ](https://impactsoft.booth.pm/items/7736698) |
| bitcores／one_chip_pico | RP2040×1、PRG-ROM応答。CHRは本体CIRAMの一部を転用 | 2023-04-20にMagic Floor実機動作報告。C／PIOとPCB公開。通常の市販ゲームは対象外 | [コード・PCB](https://github.com/bitcores/one_chip_pico)、[作者の実機報告・所在地Japan](https://forums.nesdev.org/viewtopic.php?start=90&t=9342) |

### ゆのみファクトリー：SHIMAの設計に最も近い比較対象

作者は、入手しづらい5VパラレルNOR FLASHとSRAMを廃止するためにRP2350Bを二つ使うと説明。PRG 512KBを内部RAMに置くと残りがスクラッチパッド4KB×2だけになるという、容量上の制約も具体的に投稿している。[部品とRAMの説明](https://x.com/yunomifactory/status/2108362044517081214)

独自拡張はCIRAMを無効化し、PPU側RPがネームテーブルも応答する構成。8×8ごとのパレット、960種類の背景パターン、4面の仮想ネームテーブルを説明している。6502がWRAMの特定アドレスにコマンドを書き、描画／画像読込みを指示する。ゲーム処理の主体は6502。動画、レース、格闘、弾幕の投稿は、別々のカートリッジではなく同じ基板系統のデモとして数える。[デモと構成](https://x.com/yunomifactory/status/2108593281613647965)

電源投入前の5V入力を避けるため全信号をレベル変換している。旧FCでは起動に間に合うがツインFCでは間に合わず、CPU側をRP2354Bに変更する案と、リセットを促す音声を説明している。変更案は完成した対策と扱わない。[レベル変換](https://x.com/yunomifactory/status/2108707249254432882)、[起動遅延](https://x.com/yunomifactory/status/2108708933989011506)

現試作のmapper 0対応の説明と、将来の書換え版をmapper 30・独自拡張に制限する意向は時点が違う。両者を混同しない。[今後の方針](https://x.com/yunomifactory/status/2108787260196044916)。投稿中の法律判断は技術仕様として採用していない。

### FC PICO：現行公開版と次期試作を分ける

公開版のRPはPPUのCHR読出しに応答し、読出し順序を数えて画像を流す。全アドレスを解読する通常のCHRメモリとは異なる。PPU経由で6502とコマンドをやり取りする。[README](https://github.com/impact-soft/fc-pico)

ソースには起動ROM、PIO、描画、音楽、書込み手順がある。特に[PIO実装](https://github.com/impact-soft/fc-pico/blob/main/tutorial_project/tuto1_hw/sys/pio/fcppu.pio)と[ハード資料](https://github.com/impact-soft/fc-pico/blob/main/docs/pages/hardware.md)が参考になる。ただし配布ソースの電圧処理の説明だけでは、基板の完全な回路を再現できない。

作者は次期版についてCPU側の通信・DPCM領域などを試作している。現行版の仕様へ合算しない。[CPU側の領域案](https://x.com/HD64180/status/2105110439705387375)、[CPU書込みの試験](https://x.com/HD64180/status/2108355949614514262)

### one_chip_pico：国内にいる作者による古い実動先例

作者のNESdevプロフィールはLocation: Japan。国籍は確認していない。CとPIOの実装はPicoCart64由来。PRGだけを代替し、CIRAMをCHR用にも使うため、全CPU・PPUバスを応答するSHIMA案より対象が狭い。[README](https://github.com/bitcores/one_chip_pico)

初期版はレベル変換あり。後に一部を省く試験を議論しているが、それを安全性の保証として使わない。コード公開、実機動作、カスタムPCBまで進んでおり、単なる構想ではない。[開発経緯](https://forums.nesdev.org/viewtopic.php?start=105&t=9342)

## 国内の関連ソフト・未完の周辺試作

| 名前 | 確認できたもの | 判定・リンク |
|---|---|---|
| axsann/FC_PICO_GB | FC PICO用Game Boyエミュレーター。Peanut-GB、FC音源への変換、明示操作によるセーブ保存 | 別のマジコン基板ではなくFC PICO用アプリ。[コード](https://github.com/axsann/FC_PICO_GB)、[日本語実機投稿](https://x.com/retrobitdev/status/2004055878950080694)。投稿者とGitHub作者の同一性は未確定 |
| axsann/FC_PICO_WASM4 | WASM-4ゲームをFC PPUで表示。WASMをCへ変換するツール、ゲーム選択GUI、セーブ | FC PICO用実装。全ゲーム動作保証はない。[コード・説明](https://github.com/axsann/FC_PICO_WASM4) |
| kuran-kuran/FCPicoSample | READMEの「FC Picoでなんか作ってみたい」のみ | 未着手に近い公開記録。実装済みと数えない。[リポジトリ](https://github.com/kuran-kuran/FCPicoSample)、[FC PICO利用投稿](https://x.com/kuran_kuran/status/2045678829998653499) |
| TOMMY FAMICOM PICO DUMPER／@tomiyasu16 | Pico H使用予定の基板到着、部品入手 | カセット吸出し器。マジコンではない。投稿時点で読出し成功未確認。[基板](https://x.com/tomiyasu16/status/2093295823958479341)、[部品](https://x.com/tomiyasu16/status/2093439202033827848) |

## NES／FC向け：国内以外・所在地未確認も回収

| 名前 | RP・方式 | 現時点の根拠と状態 |
|---|---|---|
| nikita600/picoCart_NES | RP2040 NES／FC／Dendyカートリッジ | 公開ツリーにhardwareと短いREADME。今回確認できた公開範囲ではファーム／実機動作の説明なし。基板候補として残す。[リポジトリ](https://github.com/nikita600/picoCart_NES) |
| khari05/rusty-cartridge | PicoによるROM代替 | GitHub検索APIの説明がWIP NES cartridge。既定ブランチの内容取得は404で失敗。実装・動作・現存状況を断定しない。[候補](https://github.com/khari05/rusty-cartridge) |
| kilrath81／NEX ROM Cart | RP2350A＋Cyclone IV FPGA＋PRG/CHR用PSRAM各8MB、SD | バス応答はFPGA、RPはROMロードや設定。2026-09-27時点はRPとSDの試験基板でディレクトリ読込みまで。完成したEverDrive相当ではない。[作者の設計](https://forums.nesdev.org/viewtopic.php?p=310696)、[進捗](https://forums.nesdev.org/viewtopic.php?p=310489) |
| nikita600/picoFDS | Raspberry Pi PicoによるFDSドライブエミュレーター | カートリッジROM代替とは別。READMEは用途のみで、今回実動証拠未確認。[コード](https://github.com/nikita600/picoFDS) |
| RedditのNES Pico flashcart案 | RP2040にPRG／CHRを応答させる構想 | 2025-01のアイデア相談。配線数と二つのバスが論点。製作済み事例に数えない。[スレッド](https://www.reddit.com/r/nes/comments/1i99icb/) |

## 他機種：移植の材料になる公開RPカートリッジ

以下は各リポジトリの公開README／メタデータを確認した一覧。全ソースの監査、ビルド、全ゲーム検証はしていない。NES対応とは扱わない。

| 対象 | プロジェクト | RP・参考になる点 |
|---|---|---|
| GB/GBC | [CrocoCart V1](https://github.com/shilga/rp2040-gameboy-cartridge-firmware) | RP2040、PIO＋DMA、ROM選択、セーブ。GBC高速動作に制約 |
| GB/GBC | [CrocoCart V2](https://github.com/shilga/rp2350-gameboy-cartridge-firmware) | RP2350B、Rust、SD・HyperRAM・RTC。PIO／DMAとセーブ処理の比較材料 |
| GB | [DBGC](https://github.com/deltabeard/DBGC) | RP2040、FRAM、RTC。古いPCBには重大な問題の注意書きあり |
| GB/GBC | [PicoGBCart](https://github.com/Nedemai/PicoGBCart) | RP2040。QSPI性能とGBC高速モードの制約 |
| GBA | [pico-gba-cart](https://github.com/Daft-Freak/pico-gba-cart) | Picoカートリッジの公開実装。READMEが少なく対応範囲は未確定 |
| N64 | [PicoCart64](https://github.com/kbeckmann/PicoCart64) | RP2040。v1と複数MCUのv2計画を分けて読む。one_chip_picoの元実装 |
| N64 | [N64cart](https://github.com/pdaxrom/N64cart) | RP2040、ROMストレージとセーブ。古いReddit記事の仕様を最新へ流用しない |
| DS | [DSPico hardware](https://github.com/LNH-team/dspico-hardware)・[firmware](https://github.com/LNH-team/dspico-firmware) | RP2040、microSD、USBと本体電源の処理。NESとはバス構成が異なる |
| MSX | [PicoVerse](https://github.com/cristianoag/msx-picoverse-public) | RP2040／RP2350、ソフトマッパー。48GPIO版の利用例 |
| MSX | [MSXPico](https://github.com/jeroentaverne/msxpico) | RP2040、ROMとマッパーの実装 |
| Atari 8bit | [A8PicoCart](https://github.com/robinhedwards/A8PicoCart) | RP2040、USB MSC。USBと本体の同時接続に関する注意も参考 |
| Atari 2600/7800 | [PicoA10400](https://github.com/aotta/PicoA10400) | RP2040、複数バンク方式。一部方式・本体条件の制限あり |
| Atari 2600 | [PlusCart-Pico](https://github.com/gtortone/PlusCart-Pico) | Pico＋ESP-AT。通信つきカートリッジ |
| SG-1000等 | [sg1000-multicart](https://github.com/xrip/sg1000-multicart) | RP2040、SG-1000／SC-3000／SMS／Mark III |
| Pokémon mini | [PM2040](https://github.com/zwenergy/PM2040) | RP2040-Zero、UF2を利用するROM書換え、基板データ |
| ROM代替ツール | [PicoROM](https://github.com/wickerwaka/PicoROM) | RP2040、DIP ROM代替。5V側バッファと起動時の待機。FCのPRG試験に応用を検討できるが完成FCマジコンではない |
| Atari ST | [SidecarT](https://github.com/sidecartridge/atarist-sidecart-raspberry-pico) | Pico W、ROMエミュレーションと周辺機能 |
| SNES | [DOOM新版のRP2350採用](https://www.raspberrypi.com/news/play-a-new-version-of-doom-on-snes-with-the-help-of-rp2350/) | 専用ゲームの補助処理。汎用マジコンとは別 |

国内の別機種では、[CT-ARK2／@Harumakkin](https://x.com/Harumakkin/status/2063439896858243397)、[@goripon_twのRP2350B ROM試作](https://x.com/goripon_tw/status/2072357785401184717)、[@tsuruma_hyonilのRP2040 MSX ROM](https://x.com/tsuruma_hyonil/status/2051919473297567810)も拾った。5Vバス応答の比較材料として保存し、NES完成例には加算しない。

## Redditから得た補足

[GBカートリッジの作者AMA](https://www.reddit.com/r/raspberry_pi/comments/11yysa2/rp2040_powered_gameboy_cartridge_video_and_ama_in/)は実装の話がある。QSPIやGBC高速モードの性能問題を読む材料になる。[自作GBCの不具合相談](https://www.reddit.com/r/embedded/comments/1shfry2/problem_with_custom_rp2040_gbc_cartridge/)も回収したが、不具合相談を成功例には数えない。NESでは今回見つかったReddit資料は構想相談が中心で、具体的なコードと実機の根拠はGitHub／NESdev側が強かった。

## SHIMAのrev0.2へ持ち帰れる点

1. ゆのみ方式は二つのRPへCPU／PPUを分ける。単一RP2350Bで双方を応答させるSHIMA方式の、直接の完成証明にはならない。
2. mapper 0からROM応答、次に書込みとCHR-RAM、次にバンク切替の順に動作を確かめる。描画デモが動くことと、通常ROMの互換性は別に検証する。
3. CPU用ROMを内部RAMへ置く容量と、PPU用RAM・DMA・スタックを含む余裕を計算する。外部PSRAMを時間厳守の応答へ直結できるとは先例から断定できない。
4. 電源投入から最初のROMアクセスまでの時間を実機別に測る。ゆのみのツインFC問題は、自動的にSHIMA基板でも起きるという証明ではないが重要な試験項目。
5. 読出し終了時のデータバス解放、電源OFF時の入力条件、USBとFCの電源経路を個別に確認する。作者の「壊れていない」と絶対定格内は同じ証拠ではない。

## 検索範囲・保存物・限界

Xは広域9クエリで279件、国内NES優先10クエリで394件の重複除去済み投稿を取得した。両集合間には重複があるため合計を独立件数としない。検索語と件数はJSON内のqueriesに保存。Latest検索のページ数に上限があり、完全な全履歴ではない。

- `twifork-tools/output/rp_cart_survey_20261010.json`
- `twifork-tools/output/rp_nes_domestic_survey_20261010.json`
- `twifork-tools/output/nes_github_search_20261010.json`
- `twifork-tools/output/rp_cart_github/` にREADME・メタデータ・一部公開ソース

GitHub APIが途中で制限に達したため、公開raw／codeloadへ切替えた。READMEだけ・取得不能・未完のものは表で明記。検索で見つからないことを不存在とはしない。InfoNES系の本体エミュレーター、USBコントローラー、Picofly、一般的なFPGAマジコンをRP製NESカートリッジとして混ぜていない。`komoriyuta/NEST2-rp2040`はセンサー／モーター系ファイルで、名前一致の誤検出として除外した。
