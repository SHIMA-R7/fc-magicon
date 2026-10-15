# パレット不一致の値をUSBログへ保存する診断

対応性検査は実機でLED1回、青・緑の切り替え成功。通常フレームの不一致を非対応PPUだけでは説明できないため、比較値そのものを採取する。

同じ12枚のNT・パレット比較を行い、FCが取得したactual16色と、FCがCPU $5D00から読んだexpected16色を$5F30〜$5F4Fへ保存する。MCUは判定後にスナップショットを取り、それからUSBを初期化する。検査中はUSB未初期化。通常転送中の負荷を再現するものではない。

USBにはstatus、停止フレーム番号、palette_errorsと、各エントリーのtarget（保存元）・expected（FCが読んだ期待値）・actual（PPUの色RAM読み戻し）を毎秒出す。expectedとtargetも比較することで、MCUからFCへの期待値転送の食い違いを区別する。USB初期化は検査後なので、その後の表示変化は検査前と区別する。

LEDは従来同様、1回=全枚一致、2回=NT不一致、3回=パレット不一致。エラーで停止したフレームの画像を残す。画面の色だけで判定しない。

実C/6502で12フレームの正常例と、各フレームの16色を意図的に変更する例を検証。保存actual/expectedがそれぞれPPUモデル/元データと一致することを検査。最大NMI1800サイクル。ファームと結合UF2からのデータ再構成も検証済み。

生成：`gen_video_driver.py baseline/palette_log_driver.h --palette-log`

ビルド：`build.ps1 -ColdBoot -PaletteLog`

UF2：`firmware/out-standalone-video/palette-log-cold-20261014.uf2`

SHA256：`908a171e70f9f394474afee8d626e464c056fabdaf2ad99493852f785f8934b7`

ホスト取得：`read_palette_log.py --port COM11 --output <capture.json>`。MCUへコマンドは送らない。COM番号は再列挙で変わる場合がある。

この版は診断後にUSB CDCが有効になる。従来のUSB完全無効版とは区別し、結合manifestにもpost_diagnostic_usb=trueを記録した。実機への書き込み・USB取得はまだ行っていない。

## 初回実機ログ

ユーザーのOFF/BOOTSEL確認後に書き込み、照合・再起動を実施。FC ON後、LED3回の報告。COM11から `palette-log-hardware-20261014.json` と `.log` を取得した（`firmware/sim/standalone-video-20261014/`）。最初の受信待ちは時間切れとなったため、FC ON後に再接続して完了した16色レコードを取得。

status=4、frame=0、palette_errors=10。targetとexpectedの不一致は8/16、targetとactualの不一致は6/16。palette_errorsはexpectedとactualの差なので10であり、targetとの差の数ではない。

| 色番号 | 保存元target | FC期待値expected | PPU報告actual |
|---|---|---|---|
| 0 | 36 | 7F | 3F |
| 2 | 0F | 5F | 0F |
| 3 | 08 | 5D | 1D |
| 6 | 20 | 7D | 20 |
| 11 | 0C | 5D | 0C |
| 12 | 36 | 7F | 3F |
| 13 | 00 | 5D | 00 |
| 14 | 18 | 5D | 1D |

数値は16進。expectedが化けた全8色で `expected == target | 0x5D`。$5Dxxを読むLDA命令のアドレス上位バイトが残った形と整合し、CPUデータ応答の遅れ/バスの残留を優先して調べる。物理波形は未観測なので電気的原因まで断定しない。expectedも読み戻し報告も同じFC/MCUバスを通るため、従来の「一致」だけで全経路が独立して正しかったと拡張しない。
