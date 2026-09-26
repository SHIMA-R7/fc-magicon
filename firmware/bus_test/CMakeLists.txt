add_executable(bus_test main.c)
pico_generate_pio_header(bus_test ${CMAKE_CURRENT_LIST_DIR}/cpu_bus.pio)
target_link_libraries(bus_test pico_stdlib pico_multicore hardware_pio hardware_clocks)
pico_enable_stdio_usb(bus_test 1)       # FPC アダプターの USB で printf
pico_enable_stdio_uart(bus_test 0)      # UART のピンはバスに使っている
pico_add_extra_outputs(bus_test)        # .uf2 も作る
