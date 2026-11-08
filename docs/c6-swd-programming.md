# ESP32-C6によるRP2350BのSWD書き込み

C6 GPIO7をRP2350BのSWCLK、GPIO6をSWDIOへ接続し、GNDを共有します。両方に給電し、ファミコンはOFFにして書き込みます。C6とRP2350BのUSB D+/D−は未接続でも使えます。

C6側は既存のwifi_bridgeにSWDサーバーを追加しています。TCP 5001を使用し、映像転送用の5000と共存します。OLEDの上下反転設定も含まれます。SWD接続中は映像転送を止め、SWDを優先します。SWD端子は切断後または15秒の通信途絶で入力に戻ります。

## 書き込み手順

Pico SDKで生成したRP2350用ELFを指定します。

    pwsh -File firmware/tools/flash_via_c6.ps1 -Elf C:/path/to/magicon_standalone_video.elf -C6Host fc-magicon.local

Python 3とRP2350対応OpenOCDが必要です。標準パスは開発PC向けです。別PCでは-Python、-OpenOcd、-Scriptsでツールの場所を指定してください。接続試験だけなら-ProbeOnlyを追加します。

中継スクリプトがSWD読み取りをC6側でまとめて実行するため、Wi-Fiの往復回数を減らせます。OpenOCDが書き込み、読み戻し照合、リセットを実行します。BOOTSEL操作は不要です。

C6を書き込む際はArduinoライブラリU8g2をインストールし、firmware/wifi_bridge/build_bridge.ps1 -Port COM12を実行します。ポート番号は接続に合わせて指定してください。

SWDサーバーには認証がないため、信頼できるLAN内で使い、TCP 5001を外部へ公開しないでください。書き込み途中で通信や電源が切れた場合は、再書き込みが必要です。
