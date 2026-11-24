# 2コンマイクの録音と本体DAC再生（2026-11-24）

ツインファミコンの2コンマイクをESP32-C6で取り込み、Aで録音開始／停止、Bで直近の録音をファミコン本体から再生する。リレーを戻した最終構成で、ユーザーが録音・再生の成功を確認した。

## 構成と操作

- RP2350：専用のCPU応答ファーム。2コンのA/BをC6へ渡し、再生中は2A03の7ビットDAC `$4011` を更新する。
- C6：GPIO0のADCを16 ksample/sで取得。UARTでPCへ送り、PCからの再生データをUSBでRP2350へ渡す。
- PC：原本WAV・ADC値・検査JSONと、13本のノッチフィルターによる `-clean.wav` を保存する。再生には正常終了した最新の録音を使う。
- 音声経路：R7の代わりにリレーCOMをカセット45番、NCを46番へ接続。GPIO1 LOWの待機・再生時は接続し、HIGHの録音時だけ切断する。

PCへの保存を使う方式で、単独録音機やWi-Fi通話の実装ではない。C6のUARTはPCへ、C6のネイティブUSBはRP2350へ接続する。2コンのマイク音量を上げる。

```powershell
python -m pip install -r firmware/tools/requirements-microphone.txt
python firmware/tools/record_fc_mic.py --port COM12 --outdir recordings
```

COM番号は環境に合わせる。Aで赤（録音）、再度Aで青（停止）。Bで緑（再生）、再度Bで停止。終了はPCでCtrl+C。録音中のBは停止・保存してから再生する。

## ビルド

RP2350は `firmware/mic_controller/build.ps1`。pico-sdk 2.3.1、TinyUSB 0.21と既存のCPU PIOを使い、ROMヘッダーは `gen_rom.py` が生成する。PSRAMやゲームROMは不要。スクリプトのツール配置は開発PC用なので、他のPCではパスを合わせる。

C6はArduino-ESP32 3.3.12、U8g2ライブラリを使い、`firmware/wifi_bridge/build_bridge.ps1 -CheckOnly` でビルドする。`wifi_secrets.example.h` を `wifi_secrets.h` にコピーして設定する。既存Web表示のフォントも依存するため、Pillowを導入し、使用許諾のある手元のフォントから次を実行する。

```powershell
python -m pip install Pillow
python firmware/web_browser/make_device_font.py firmware/wifi_bridge/web_font.h --font C:/Windows/Fonts/meiryo.ttc
```

生成フォントとWi-Fi情報入りC6バイナリは公開しない。ファーム書き換え中はFCをOFFにする。

## 確認したこと

- 6502側のDAC更新はボタン読取りを含め224 CPUサイクル間隔（NTSCで約7,990回／秒）。
- 3秒の440 Hzで実際の `$4011` 書込み24,000回、不一致0件。ユーザーも連続音を確認。
- 声の再生でも55,296回の実書込みを確認。既定4倍ゲイン＋ソフトリミッターで「十分聞こえる・音割れも気にならない」と確認した。録音原本は変更しない。
- 固定ノッチフィルターは測定した静音区間でRMSを約6 dB低減した。別個体では再測定が必要で、音声成分の完全保存や全雑音の除去を保証しない。
- GPIO1は優先初期化でLOWへ設定。2回のENリセットで起動ログと読み戻し0を確認した。アプリ起動前の状態をソフトだけで保証できないため、ベースのプルダウンも使う。
- リレーの2秒ON／2秒OFFを3回実行し、読み戻し1／0と最終LOW、試験中のC6再起動なしを確認。LED極性修正後に作動音、最後にリレー付きの録音・再生をユーザーが確認した。

初期のコイル接続では低電圧リセットが発生した。その後、配線修正と220 µF追加などを行っており、コンデンサー単独の効果とは断定しない。最終トランジスタの実装型番・コイル直列抵抗は確定していない。

## 配線の注意点

ADC入力はカセット45番からAC結合・抵抗・1.65 V付近のバイアスを介す。GPIO0へ5 Vを直結しない。試作ではバイアスの上下に8.2 kΩ、AC結合100 nF、ADC側10 nFを使用し、実測DCは1.59 Vだった。直列抵抗の最終実装値は未確認。

SRD-03VDC-SL-CのコイルはGPIOから直接駆動せず、NPNで駆動する。GPIO1→220 Ω→ベース、ベース→8.2 kΩまたは10 kΩ→GND、エミッター→GND、コレクター→コイル−、コイル＋→適切な3 V系電源。使用するトランジスタの実物の足順・電流余裕を確認する。

逆起電力対策にはコイル電流に適した整流ダイオードを逆並列にする（カソードをコイル＋、アノードをコイル−）。ユーザー試作は3 mm LEDを使い、その極性修正で作動したが、LEDのサージ定格や長期保護性能は検証しておらず、推奨回路とは扱わない。

[操作・実装の詳細](../firmware/mic_controller/README.md) ／ [初期ADC診断](fc-microphone-diagnostic-20261124.md) ／ [ノイズ低減の測定](fc-microphone-noise-reduction-20261124.md)
