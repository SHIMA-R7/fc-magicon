# FC-MAGICON ファームウェア(pico-sdk 2.3.1、RP2350B = Waveshare Core2350B2)
# ビルドは build.ps1 から(日本語を含むパスを避けるため、C:\Users\Yugo\pico\work にコピーしてビルドする)
cmake_minimum_required(VERSION 3.13)

set(PICO_PLATFORM rp2350-arm-s)
if (NOT PICO_BOARD)
    set(PICO_BOARD fc_magicon)                     # boards/fc_magicon.h(RP2350B、16MB フラッシュ)
endif()
set(PICO_BOARD_HEADER_DIRS ${CMAKE_CURRENT_LIST_DIR}/boards)

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(fc_magicon C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

# host_test(RP2350 を USB ホストにする試験)は TinyUSB 0.21 が要る(0.18 の RP2350 ホストはバルク転送が 64KB/秒止まり)。
# build.ps1 が PICO_TINYUSB_PATH を 0.21 にして -DFC_HOST_TEST=ON で別にビルドする。ほかは pico-sdk 付属の 0.18 のまま。
if (FC_HOST_TEST)
    add_subdirectory(host_test)
else()
    add_subdirectory(bus_test)
    add_subdirectory(chr_test)
    add_subdirectory(magicon)
    add_subdirectory(usb_test)
endif()
