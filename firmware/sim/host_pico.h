// FC-MAGICON sim: cart.c を PC でビルドするための、pico-sdk の代わりの最低限の定義
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

typedef unsigned int uint;
#define __not_in_flash_func(f) f

extern bool host_irq;                   // GPIO45(/IRQ を Q1 で引く)の状態
static inline void gpio_put(uint pin, bool v) {
    if (pin == 45)
        host_irq = v;
}
