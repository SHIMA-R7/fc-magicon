#pragma once
#include <WiFi.h>
#include "driver/gpio.h"

// OpenOCD remote_bitbang SWD protocol, TCP 5001.
// GPIOs remain inputs until a debugger connects and are released on disconnect.
static WiFiServer swd_server(5001);
static WiFiClient swd_client;
static bool swd_active;
static bool swd_uart_active;
static uint32_t swd_last_activity;
static constexpr gpio_num_t SWD_CLK = GPIO_NUM_7;
static constexpr gpio_num_t SWD_DIO = GPIO_NUM_6;

static void swd_release() {
  gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT);
  gpio_set_direction(SWD_CLK, GPIO_MODE_INPUT);
  swd_client.stop();
  swd_active = false;
}

static void swd_begin() {
  gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT);
  gpio_set_direction(SWD_CLK, GPIO_MODE_INPUT);
  gpio_set_pull_mode(SWD_DIO, GPIO_FLOATING);
  gpio_set_pull_mode(SWD_CLK, GPIO_FLOATING);
  swd_server.begin();
  swd_server.setNoDelay(true);
}

static bool swd_uart_poll() {
  // A dedicated UART session starts with STX (0x02); Q returns to status logs.
  if (!swd_uart_active) {
    if (swd_active) return false;
    while (Serial0.available() && Serial0.peek() != 2) Serial0.read();
    if (Serial0.peek() != 2) return false;
    Serial0.read();
    gpio_set_level(SWD_DIO, 1);
    gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT_OUTPUT);
    gpio_set_level(SWD_CLK, 0);
    gpio_set_direction(SWD_CLK, GPIO_MODE_OUTPUT);
    swd_uart_active = true;
    swd_last_activity = millis();
    Serial0.print("SWD READY\n");
  }
  while (Serial0.available()) {
    int c = Serial0.read();
    swd_last_activity = millis();
    if (c >= 'd' && c <= 'g') {
      int value = c - 'd';
      gpio_set_level(SWD_DIO, value & 1);
      gpio_set_level(SWD_CLK, (value >> 1) & 1);
      delayMicroseconds(1);
    } else if (c == 'O') gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT_OUTPUT);
    else if (c == 'o') gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT);
    else if (c == 'c' || c == 'R') Serial0.write(gpio_get_level(SWD_DIO) ? '1' : '0');
    else if (c == 'Z') delay(1);
    else if (c == 'z') delayMicroseconds(1);
    else if (c == 'Q') {
      gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT);
      gpio_set_direction(SWD_CLK, GPIO_MODE_INPUT);
      swd_uart_active = false;
      return false;
    }
  }
  if (millis() - swd_last_activity > 15000) {
    gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT);
    gpio_set_direction(SWD_CLK, GPIO_MODE_INPUT);
    swd_uart_active = false;
  }
  return swd_uart_active;
}

static bool swd_poll() {
  if (swd_uart_poll()) return true;
  if (!swd_client || !swd_client.connected()) {
    if (swd_active) swd_release();
    swd_client = swd_server.accept();
    if (!swd_client) return false;
    swd_client.setNoDelay(true);
    gpio_set_level(SWD_DIO, 1);
    gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT_OUTPUT);
    gpio_set_level(SWD_CLK, 0);
    gpio_set_direction(SWD_CLK, GPIO_MODE_OUTPUT);
    swd_last_activity = millis();
    swd_active = true;
  }
  if (millis() - swd_last_activity > 15000) {
    swd_release();
    return false;
  }
  uint8_t commands[512], replies[512];
  int count = swd_client.read(commands, sizeof commands);
  if (count <= 0) return true;
  swd_last_activity = millis();
  size_t reply_count = 0;
  for (int i = 0; i < count; ++i) {
    const uint8_t c = commands[i];
    if (c >= 'd' && c <= 'g') {
      const uint8_t value = c - 'd';
      gpio_set_level(SWD_DIO, value & 1);
      gpio_set_level(SWD_CLK, (value >> 1) & 1);
      delayMicroseconds(1);
    } else if (c == 'H' || c == 'h') {
      // Batch the fixed-length input phase used by OpenOCD bitbang SWD:
      // read = turnaround + ACK + data + parity + turnaround (38),
      // write = turnaround + ACK (4).
      const int cycles = c == 'H' ? 38 : 4;
      if (reply_count) {
        swd_client.write(replies, reply_count);
        reply_count = 0;
      }
      uint8_t samples[38];
      for (int bit = 0; bit < cycles; ++bit) {
        gpio_set_level(SWD_DIO, 0);
        gpio_set_level(SWD_CLK, 0);
        delayMicroseconds(1);
        samples[bit] = gpio_get_level(SWD_DIO) ? '1' : '0';
        gpio_set_level(SWD_CLK, 1);
        delayMicroseconds(1);
      }
      swd_client.write(samples, cycles);
    } else if (c == 'O') {
      gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT_OUTPUT);
    } else if (c == 'o') {
      gpio_set_direction(SWD_DIO, GPIO_MODE_INPUT);
    } else if (c == 'c' || c == 'R') {
      replies[reply_count++] = gpio_get_level(SWD_DIO) ? '1' : '0';
    } else if (c == 'Q') {
      if (reply_count) swd_client.write(replies, reply_count);
      swd_release();
      return false;
    } else if (c == 'Z') {
      delay(1);
    } else if (c == 'z') {
      delayMicroseconds(1);
    } else if (c == 'B' || c == 'b' || (c >= 'r' && c <= 'u')) {
      // No reset wire is connected; OpenOCD uses the ARM software reset.
    } else {
      swd_release();
      return false;
    }
  }
  if (reply_count && swd_client.write(replies, reply_count) != reply_count)
    swd_release();
  return swd_active;
}
