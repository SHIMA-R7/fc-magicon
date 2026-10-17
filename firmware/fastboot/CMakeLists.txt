# Standalone experiment; does not replace magicon or program OTP.
add_executable(magicon_fastboot main.c)
pico_generate_pio_header(magicon_fastboot ${CMAKE_CURRENT_LIST_DIR}/../magicon/cpu_m2.pio)
pico_generate_pio_header(magicon_fastboot ${CMAKE_CURRENT_LIST_DIR}/../chr_test/ppu_chr.pio)
pico_generate_pio_header(magicon_fastboot ${CMAKE_CURRENT_LIST_DIR}/../magicon/mirror.pio)
target_link_libraries(magicon_fastboot pico_stdlib pico_multicore hardware_pio hardware_clocks hardware_watchdog)
pico_enable_stdio_uart(magicon_fastboot 0)
pico_enable_stdio_usb(magicon_fastboot 1)
pico_add_extra_outputs(magicon_fastboot)
