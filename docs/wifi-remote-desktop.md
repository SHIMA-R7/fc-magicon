# ESP32-C6無線リモートデスクトップ

PC → Wi-Fi (TCP 5000) → ESP32-C6 → USB CDC → RP2350B → ファミコン。RP2350B側はUSBホストとして動作し、C6のUSB Serial/JTAGに接続します。映像と音声の処理は直結版と共通です。

- C6のネイティブUSBはGPIO12 (D−)、GPIO13 (D+)。カセットの対応するUSB信号とGNDへ接続します。C6への書き込みには別系統のUSB-UARTを使います。
- RP2350BをPCのUSBで書き込む間はC6とのD+/D−を外します。PC直結USBを抜いてからC6側のD+/D−を戻します。
- C6は [wifi_bridge](../firmware/wifi_bridge/) を書き込み、同じLANに接続します。TCP 5000をインターネットへ公開せず、信頼できるLAN内で使用してください。
- RP2350BはPico SDK 2.3.1とTinyUSB 0.21.0を使い、以下のCMakeオプションでビルドします。成果物は `build-wifi/standalone_video/magicon_standalone_video.uf2` です。

```powershell
cmake -S firmware -B build-wifi -G Ninja -DCMAKE_BUILD_TYPE=Release -DPICO_TINYUSB_PATH=C:/path/to/tinyusb-0.21.0 -DFC_STANDALONE_VIDEO_ONLY=ON -DFC_TUSB021=ON -DFC_PLAYER_COLD_BOOT=ON -DFC_PLAYER_FAST_READS=ON -DFC_REMOTE_DESKTOP=ON -DFC_REMOTE_WIFI=ON
cmake --build build-wifi
```

Windowsで4:3全画面へ伸縮する送信例です。IPアドレスはC6のものに置き換えます。

```powershell
python firmware/tools/remote_pc.py --tcp 192.168.1.123 --color --stretch --fps 8 --audio pcm8 --solid --fit-tiles --software-cursor --stop-screen
```

ツインファミコン給電のみでの起動、カラーバー表示、入力パケットの返送、停止時の待機画面への復帰を確認済みです。PC画面・音声の転送試験では音声の取りこぼしが残っています。
