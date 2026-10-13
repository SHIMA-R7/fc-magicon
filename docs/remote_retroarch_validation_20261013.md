# RetroArchを使った画面転送検証（2026-10-13）

実機の書込みは行っていない。改良版は `firmware/out-direct-pio-diagnostic/magicon-remote-dma-full-stabletiles-colorready.uf2` に保存した。

## 実施結果

- RetroArch 1.22.2 と公式Nestopiaコアで、実際の全画面6502ドライバーから作った検証用NESを120フレーム実行した。特殊なカセット内レジスター $5D00/$5E00/$5F00 は、通常のNROMのSRAMで扱える $6400/$6500/$6600 へ移した。それ以外の表示処理は同じ。実機のPIO・DMA・電気的タイミングは再現していない。
- 文字画像：変換前後の画素誤差0、RetroArchと変換後の画像の画素誤差0。
- 提供されたYouTubeスクリーンショット：変換時に2738/61440画素（約4.46%）が変化。RetroArchと変換後の画像の画素誤差0。動画の時間変化や実機の画面崩れを直接再現した結果ではない。
- カラーバー：既存nesframeのカラー変換を使用し、属性64バイトを反映。カスタムパレットをそろえたRetroArchと変換画像の画素誤差0。
- 音声：既存PCエンコーダーが作ったPCM16/PCM8/ADPCM各35パケットを、audio.cから抽出した実際の復号部分と照合し全サンプル一致。DMAリング・PWM・RC・ファミコンへのアナログ音声経路は未検証。Windows WASAPIループバック初期化成功（48kHz、2ch、32bit float）。初回サンプル0で、録音品質の確認ではない。

## 修正

`remote_full.h` に実際のタイル変換を分離し、出現頻度だけで同じ絵柄のタイル番号が変わらないようにした。既存絵柄の予約を先に済ませてから、新しい絵柄を空きスロットへ入れる。共有実装を使った `audit_remote_full.c` で、順序・頻度が変わる2フレーム間の番号維持と200絵柄の完全再構成を確認した。静止画像の変換出力は、RetroArchで確認した修正前スナップショットとバイト単位で同じだった。

全画面版の属性固定を外し、最後のNT更新区間からカラー属性を転送するようにした。PC送信に `--stretch` を追加し、256×240を使い切る表示を選べるようにした。縦長のPC画面でもfitが240行をはみ出さない計算へ修正した。取り込みのみのdry-run成功（stretch fit gray約26.5fps）。RP2350改良版のビルド成功。

## 残る問題・帰宅後の順番

1. 同じ絵柄の番号は安定するが、新しい絵柄が古いスロットを置き換えると、8フレームかけるNT更新との不一致が起こり得る。更新途中の完全な原子性はまだない。対策の本命はCHRとネームテーブルを二重化し、VBlankで組として切り替える設計。
2. 256絵柄を超える画像の代用は残る。カラー化やstretchで絵柄数が増えることもある。細字の忠実度は別途改善が必要。
3. 帰宅後はまず白黒・低fpsで改良版を実機確認し、次に `--color --fps 5 --no-audio`、その後 `--audio pcm16` で音声を足す。画面更新が長く止まると、audio_pollの「256ms以内に呼ぶ」前提を破る可能性があるため、同時転送の遅延を実測する。

## 成果物

- `firmware/sim/retroarch-remote-20261013/text-retroarch.png`
- `firmware/sim/retroarch-remote-20261013/youtube-retroarch.png`
- `firmware/sim/retroarch-remote-20261013/color-retroarch.png`
- 同フォルダーの `results.json`, `audio-results.json`, `wasapi-results.json`, ROM/SRAM/ログ。
- `run_retroarch.ps1` でインストール済みRetroArchと検証フォルダーのコアを使ってスナップショット試験を再実行できる。

参考： [RetroArch CLI](https://docs.libretro.com/guides/cli-intro/)、[Nestopiaコア設定](https://docs.libretro.com/library/nestopia/)。NESコアは公式buildbotから検証フォルダーにのみ追加した。初回RetroArch実行では通常の履歴・Nestopia設定ファイルが作られた。後続の検証は専用設定と保存先を使用している。
