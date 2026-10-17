# ブルアカ入力と音声ハードの追加調査（2026-10-17）

ユーザーは「マウスが一時的に止まるのではなくブルアカ側のマウス実装が特殊」と訂正し、その実装調査をファーム書込みより先に行うよう指示。r2ファームはまだ書き込まない。

## 確認できた事実

- こちらの旧マウス移動は `SetCursorPos`、クリックは `SendInput`。Windows上の位置指定と入力イベント送信を混在させている。
- このPCに残る日本版 `AppData/LocalLow/YostarJP/BlueArchive/Player.log` には `Initialize engine version: 2021.3.56f2`、`New input system (experimental) initialized`、`Using XInput` がある。FMVの版・設定を直接確認した結果ではない。
- ローカルのゲームメタデータにMouse/VirtualMouse/InputSystem関連の名前が含まれる。ただし同梱ライブラリの未使用部分も含み得るため、これだけでゲームの使用APIや独自カーソルの更新方法を特定したと扱わない。ゲームファイルを改変したり、保護機構を回避したりしていない。
- 日本版の操作説明から内部の入力APIを特定できる公開資料は確認できなかった。「Raw Input専用」と断定しない。

[SetCursorPos公式資料](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setcursorpos) は画面座標の移動を説明し、[SendInput公式資料](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) はマウス動作等を入力ストリームへ挿入するAPIと説明する。r2では比較用に相対移動のSendInputを追加したが、ブルアカ対応を実証したという意味ではない。通常位置指定も残す。

[Unity Mouse資料](https://docs.unity3d.com/Packages/com.unity.inputsystem@1.0/manual/Mouse.html) ではOSカーソル移動、内部の位置、カーソルロックを区別する。ゲームがどれを利用するかは追加確認が必要。PC側で重ね描きするカーソルとゲーム自身のカーソルが二重になる可能性も、実画面で確認すべき事項。

[Nexon公式Steam版操作ガイド](https://forum.nexon.com/bluearchive-en/board_view?board=3222&thread=3014083) はコントローラー接続時の入力優先やマウス・キーボードとの切替を説明する。ただし海外Steam版の説明を、日本版Yostarクライアントにそのまま適用したと断定しない。現RP2350ファームのUSBはCDCシリアルで、USBゲームパッドとしては列挙しない。

## 音声の聞こえ方と試験候補

ユーザーはノイズについて「どちらかというとジー／シャー、バリバリもゼロではない」と回答。原因がアナログだけと確定したわけではない。PC側再サンプリングの分割不具合は別途再現・修正・検査済み。

現行設計はGPIO44→R9 1kΩ→RCノード（C3 10nFでGND）→VR1→R8→本体音声ノード。J2はC4 10µF、R10 47kΩ、R11 100Ωを介した無増幅ライン出力。実装済みR8の実抵抗値は依然未確認で、イヤホン負荷を含めた実効特性は不明。

最小の比較候補は、すべて無給電の状態でC3の両端へ10nF（103、無極性）を並列に追加すること。R9=1kΩ・軽い負荷の近似なら総容量20nF、遮断周波数は15.9kHz→7.96kHz。十分高い周波数成分の抑制は約6dB増えるが、音楽の高域も減る。可聴帯域全体のノイズが6dB減るという予測ではない。低周波のハムやデジタルの欠落音はこれでは解決しない。既存C3が実際に10nFかも確認が必要。

[TI PWM DAC資料](https://www.ti.com/lit/an/slaa497a/slaa497a.pdf) は遮断周波数・フィルター次数とPWMリップル／帯域のトレードオフを説明する。GPIO44へ直接大容量を追加するのではなく、R9の後ろのC3に追加する。

C4増量は主に低域の通過特性を変えるので、今回のジー／シャー低減の第一候補とはしない。USB給電のGND・電源ノイズ、配線、イヤホン負荷は別途評価が必要。ヘッドホンを十分駆動するには出力バッファ／ヘッドホンアンプが必要になる可能性がある。未測定の電源ノードに無差別に大容量を追加する提案はしない。

## r2成果物

PC側配布：`output/FC-MAGICON-USB-Win11-20261017-r2.zip`（リポジトリの上の作業フォルダ）。SHA256 `fbc15a9324a1da68ed014370c5f865ec68d10159b220663dd627382a51601336`。

受信UF2：`firmware/out-standalone-video/remote-desktop-usb-a9-gpio39-20261017-r2.uf2`。SHA256 `b1ac91f8fe38e5bb7406e3142dd5018dbcc4c2f1d5cb3a70755d24e9cff540e3`。ビルド・ホスト検査済み、実機未書込み。

配布EXEは模擬受信先へ画質優先モードで映像3フレーム、音声36パケット、最終FCST停止要求を送信し終了コード0。分割された音声診断受信も検査した。PC側の音声修正・3段階ズーム・相対マウス比較はr1受信ファームでも利用できる。キーボード走査、待機画面、受信側のバッファ変更と音声統計にはr2受信ファームが必要。


## 2026-10-18 入力症状の追加確認

ユーザー確認：FCパッド、Nano SFCマウスの両方とも通常のWindowsで操作できるが、ブルアカでは移動・クリックが両方効かない。キーボードはOKとの報告。両経路の共通部分であるSendInputとゲームの受付・権限差を優先して調べる。相対移動はクリックの送信方法を変えないため、相対移動を選ぶだけで権限差などは解消しない。

手元F:/BlueArchive/YostarGames/BlueArchive_JP/BlueArchive.exeのPE manifestはrequestedExecutionLevel=asInvoker、uiAccess=false。手元ではゲームは起動しておらず、FMVのプロセストークンは未測定。asInvokerはランチャーから継承した高い権限を排除しない。管理者として送信アプリを起動する比較はユーザーがまだ試せないため保留。

診断モジュールwin_input_diagnostics.pyを追加。実トークンの整合性レベルを読み、前面の入力先・ゲームプロセスと比較する。自動昇格やゲーム改変はしない。クリック／キーボードにもSendInput戻り値の検査を追加した。送信先権限が高い場合に警告を記録する。失敗だけではUIPIを確定せず、成功だけでもゲームの受理を確定しない。

参照： https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput

## 解決確認（2026-10-18）

ユーザーが送信アプリの管理者実行でブルアカのマウス操作に成功したと確認。権限差が主因という説明を支持する。FMVの具体的トークン値は未採取であり、Raw Input専用や保護機構による拒否は確定事項ではない。
