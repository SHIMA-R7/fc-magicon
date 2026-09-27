// host_test の TinyUSB 設定(RP2350 の USB をホストにして、ESP32-C6 の USB Serial/JTAG = CDC ACM を開く)
#pragma once

// OS 無しで使う(pico-sdk は CFG_TUSB_OS=OPT_OS_PICO を渡してくるが、TinyUSB 0.21 と pico-sdk 2.3.1 の組み合わせでは
// CDC の受信 FIFO の mutex が初期化されないまま tuh_cdc_read が待ち続けた。2026-09-27、SWD で確認)。
// host_test はループ 1 本で回すので FIFO のロックは要らない
#undef CFG_TUSB_OS
#define CFG_TUSB_OS                OPT_OS_NONE
#include "pico.h"                  // __not_in_flash など(OS 無しだと osal_pico.h 経由で読み込まれなくなる)

#define CFG_TUH_ENABLED            1
#define CFG_TUSB_RHPORT0_MODE      OPT_MODE_HOST
#define BOARD_TUH_RHPORT           0
#define CFG_TUH_MAX_SPEED          OPT_MODE_FULL_SPEED
#define CFG_TUH_ENUMERATION_BUFSIZE 256
#define CFG_TUH_HUB                0
#define CFG_TUH_DEVICE_MAX         1
#define CFG_TUH_CDC                1

// 開いた時に DTR だけ立てる(C6 の USB Serial/JTAG は RTS でリセットがかかる。PC の Windows も DTR だけで動いた)
#define CFG_TUH_CDC_LINE_CONTROL_ON_ENUM  CDC_CONTROL_LINE_STATE_DTR
#define CFG_TUH_CDC_LINE_CODING_ON_ENUM   { 115200, CDC_LINE_CODING_STOP_BITS_1, CDC_LINE_CODING_PARITY_NONE, 8 }

// 受信のバッファを大きくする(1 枚 15463 バイトを 64 バイトずつ受けるので、読み出しが遅れても取りこぼさないように)
#define CFG_TUH_CDC_RX_BUFSIZE     4096
#define CFG_TUH_CDC_TX_BUFSIZE     256

#define CFG_TUSB_MEM_ALIGN         __attribute__((aligned(4)))

// TinyUSB のログを UART0(GPIO0 = P1 の 2 番)へ。debugprobe の GP5 で受けて PC の COM で読む。2 = 列挙と転送まで出す
#ifndef CFG_TUSB_DEBUG
#define CFG_TUSB_DEBUG             2
#endif
