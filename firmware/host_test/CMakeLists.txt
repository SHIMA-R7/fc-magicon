add_executable(host_test main.c)
target_include_directories(host_test PRIVATE ${CMAKE_CURRENT_LIST_DIR})   # tusb_config.h
target_link_libraries(host_test pico_stdlib hardware_clocks tinyusb_host)
pico_enable_stdio_usb(host_test 0)      # USB はホストに使うので printf は出せない
pico_enable_stdio_uart(host_test 1)     # 試験中の様子と TinyUSB のログ: UART0 TX = GPIO0(Core2350B2 の P1 の 2 番)、115200
pico_add_extra_outputs(host_test)
