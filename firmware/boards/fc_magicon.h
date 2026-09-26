// FC-MAGICON 用のボード定義(Waveshare Core2350B2 を FC-MAGICON 基板に載せた状態)
// pico-sdk 2.3.1 の boards/waveshare_core2350b.h を元に、UART・I2C・SPI の既定ピンを外した。
// (公式の既定は UART0 = GPIO0/1 などで、この基板では CPU バスの D0/D1 に当たるため)

#ifndef _BOARDS_FC_MAGICON_H
#define _BOARDS_FC_MAGICON_H

pico_board_cmake_set(PICO_PLATFORM, rp2350)

#define FC_MAGICON
#define WAVESHARE_CORE2350B

// --- RP2350 VARIANT ---
#define PICO_RP2350A 0                 // RP2350B(QFN-80、GPIO 48本)

// --- LED ---(470Ω で GND へ。バスには使わない)
#ifndef PICO_DEFAULT_LED_PIN
#define PICO_DEFAULT_LED_PIN 39
#endif

// UART / I2C / SPI の既定ピンは定義しない(GPIO0-46 はすべて FC-MAGICON の配線で使用中)

// --- FLASH ---
#define PICO_BOOT_STAGE2_CHOOSE_W25Q080 1
#ifndef PICO_FLASH_SPI_CLKDIV
#define PICO_FLASH_SPI_CLKDIV 2
#endif
pico_board_cmake_set_default(PICO_FLASH_SIZE_BYTES, (16 * 1024 * 1024))
#ifndef PICO_FLASH_SIZE_BYTES
#define PICO_FLASH_SIZE_BYTES (16 * 1024 * 1024)
#endif

// --- PSRAM ---(Core2350B2 は 2MB)
#define WAVESHARE_CORE2350B_PSRAM_CS_PIN 47
#ifndef PICO_PSRAM_CS_PIN
#define PICO_PSRAM_CS_PIN WAVESHARE_CORE2350B_PSRAM_CS_PIN
#endif
#ifndef PICO_AUTO_DETECT_PSRAM_SIZE
#define PICO_AUTO_DETECT_PSRAM_SIZE 1
#endif

pico_board_cmake_set_default(PICO_RP2350_A2_SUPPORTED, 1)
#ifndef PICO_RP2350_A2_SUPPORTED
#define PICO_RP2350_A2_SUPPORTED 1
#endif

#endif
