// magicon_wifi の TinyUSB 設定(RP2350 の USB をホストにして、J6 の ESP32-C6 の USB Serial/JTAG = CDC ACM を開く)
// host_test/tusb_config.h と同じ中身(ログだけ無し)。TinyUSB 0.21.0 で使う
#pragma once

// OS 無しで使う(pico-sdk は CFG_TUSB_OS=OPT_OS_PICO を渡してくるが、TinyUSB 0.21 と pico-sdk 2.3.1 の組み合わせでは
// CDC の受信 FIFO の mutex が初期化されないまま tuh_cdc_read が待ち続けた)。USB はコア 0 のループ 1 本で回す
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

// 開いた時に DTR だけ立てる(C6 の USB Serial/JTAG は RTS でリセットがかかる)
#define CFG_TUH_CDC_LINE_CONTROL_ON_ENUM  CDC_CONTROL_LINE_STATE_DTR
#define CFG_TUH_CDC_LINE_CODING_ON_ENUM   { 115200, CDC_LINE_CODING_STOP_BITS_1, CDC_LINE_CODING_PARITY_NONE, 8 }

#define CFG_TUH_CDC_RX_BUFSIZE     4096
#define CFG_TUH_CDC_TX_BUFSIZE     256

#define CFG_TUSB_MEM_ALIGN         __attribute__((aligned(4)))
