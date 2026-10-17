# PicoなしでNanoのUSBからSFCマウスを使う

従来のNanoスキャナーに、Windows用のUSBシリアル出力を追加したオプション。Pico向けSoftwareSerial（D2/D3・57600bps）、既存のキーボード・光線銃・SFCパッド・マウスの処理と配線は維持する。Picoの `code.py` は変更不要。Picoを戻したら従来のUSB HIDとして使用できる。

USBシリアル出力は115200bps。PCから `FCNM?` と改行を受信した間だけ有効になり、要求が3秒途切れると停止する。Pico向けの通信はその間も従来どおり継続する。PicoとPCブリッジの両方から同時に同じPCへ入力すると二重操作になるので、Picoを使うときはPCブリッジを停止する。

## 接続とファーム

Nanoは従来どおりUSBでWindowsへ接続し、SFCマウスを1Pまたは2Pポートへ挿す。CLOCK=A5、LATCH=A0、1P DATA=A1、2P DATA=A3。USBのD0/D1はUSBシリアル用なので外部回路を足さない。既存のSFCポート配線を変更する必要はない。

`firmware/nano/famicom_scanner.ino` と隣の `usb_mouse_bridge.h` を同じArduinoスケッチフォルダに置いて書き込む。Arduino Nano / ATmega328P、手元のCOM6個体はOld Bootloader（57600bps）で書込み・照合済み。ビルド時はフォルダ名を `famicom_scanner` にそろえる。ほかのNanoはブートローダーに合う設定を使う。

## Windows

FC-MAGICON送信アプリr2.2では、Nano専用COMと感度を選び「Nanoのマウスを使う」をONにする。RP2350とは別のCOMを指定する。初めは「Nanoマウスのみ」で移動と左右クリックを試し、その後に映像転送と併用する。Nano使用時はFCパッドのマウス移動・クリックを止め、SELECT/STARTの表示切替とFCキーボードは維持する。

アダプター単体でも、Python 3 + `python -m pip install pyserial` の後、以下で使用できる。

```powershell
python tools/nano-usb-mouse/windows_mouse_bridge.py --list
python tools/nano-usb-mouse/windows_mouse_bridge.py --port COM6 --gain 6
```

左右クリックと相対移動に対応。ホイールはSFCマウスに存在しない。既定感度6倍、デスクトップで遅ければ12、エミュレーターのSFCマウス入力用途なら1を目安に調整する。2台のマウスはOSの同じポインターを共有する。PCブリッジでのキーボード・パッド・光線銃変換は今回追加していないが、これらのPico向け処理は残っている。

識別応答前やCRC不一致のデータでは操作しない。マウスの報告が0.5秒途切れたポートのボタンを解放し、切断・停止時も解放する。OS入力権限の制約は通常のSendInputと同じで、ゲーム側での受理は別途確認が必要。Windowsのデスクトップ入力でも、USB HIDデバイスとして列挙されるわけではない。

## USBプロトコル

12バイト固定：`FNM1`、種別、連番、ポート、ボタン、dx、dy、CRC16 little endian。CRCは先頭10バイトにCRC-16/CCITT-FALSE（初期値FFFF、多項式1021）。種別0=識別応答（ポート0）、1=マウス（ポート1/2）、2=マウス未接続/標準パッド。ボタンbit0=左、bit1=右、dx/dyは符号付き8ビット（-127～127）。連番は全ポート共通、256で循環する。

従来のPico向け1バイトイベント／4バイトマウス報告を、この形式へ変更したものではない。USBだけの別形式である。

## 検査

AVRビルド：フラッシュ5742バイト、RAM626バイト。実コードのホスト検査でPico向けマウスのバイト列が従来どおりであること、USB識別前に出力しないこと、反転デコード、CRC、分割受信、破損後の再同期、感度の端数、2ポートのボタン共有、切断時の解放を確認した。

2026-10-18、COM6への書込み・照合と実機USB応答を確認。マウス未接続の状態で未接続報告41件、CRCエラー0。実マウスの移動・クリック、Picoを戻した実機での同時機能は未確認。
