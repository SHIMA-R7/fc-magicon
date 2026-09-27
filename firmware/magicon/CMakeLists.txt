# magicon(USB デバイス = PC 直結)と magicon_wifi(USB ホスト = J6 の ESP32-C6 経由で Wi-Fi)を同じソースから作る。
# magicon_wifi は TinyUSB 0.21 が要るので、build.ps1 の 2 回目のビルド(FC_TUSB021)で作る
function(magicon_target name)
    add_executable(${name} ${CMAKE_CURRENT_LIST_DIR}/main.c ${CMAKE_CURRENT_LIST_DIR}/cart.c)
    pico_generate_pio_header(${name} ${CMAKE_CURRENT_LIST_DIR}/cpu_m2.pio)
    pico_generate_pio_header(${name} ${CMAKE_CURRENT_LIST_DIR}/../chr_test/ppu_chr.pio)
    pico_generate_pio_header(${name} ${CMAKE_CURRENT_LIST_DIR}/mirror.pio)
    target_include_directories(${name} PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../chr_test)   # chr_rom.h(試験画面の PRG)
    target_link_libraries(${name} pico_stdlib pico_multicore hardware_pio hardware_clocks)
    pico_enable_stdio_uart(${name} 0)
    pico_add_extra_outputs(${name})
endfunction()

if (FC_TUSB021)
    magicon_target(magicon_wifi)
    target_compile_definitions(magicon_wifi PRIVATE MAGICON_USB_HOST=1)
    target_include_directories(magicon_wifi PRIVATE ${CMAKE_CURRENT_LIST_DIR}/usb_host)   # tusb_config.h(ホスト)
    target_link_libraries(magicon_wifi tinyusb_host)
    pico_enable_stdio_usb(magicon_wifi 0)     # USB はホストに使う
else()
    magicon_target(magicon)
    pico_enable_stdio_usb(magicon 1)
endif()
