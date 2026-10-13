"""Run the actual power_guard.h against mocked GPIO/PIO/watchdog registers."""
from pathlib import Path
import shutil
import subprocess
import tempfile

SOURCE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <setjmp.h>
#include <stdio.h>
typedef unsigned uint;
#define __not_in_flash_func(x) x
#define GPIO_OVERRIDE_LOW 2u
#define IO_BANK0_GPIO0_CTRL_OEOVER_LSB 12
#define IO_BANK0_GPIO0_CTRL_OEOVER_BITS (3u << 12)
#define GPIO_IRQ_EDGE_FALL 4
#define IO_IRQ_BANK0 21
#define PICO_HIGHEST_IRQ_PRIORITY 0
static void irq_set_priority(int irq, int priority) { assert(irq == 21 && priority == 0); }
struct bank { struct { uint32_t ctrl; } io[48]; } bank;
struct pio { uint32_t ctrl; } pios[3];
struct wd { uint32_t scratch[8]; } wd;
struct sio { uint32_t gpio_hi_togl; } sio;
#define io_bank0_hw (&bank)
#define pio0 (&pios[0])
#define pio1 (&pios[1])
#define pio2 (&pios[2])
#define watchdog_hw (&wd)
#define sio_hw (&sio)
static bool powered;
static int delay_ms, sleeps;
static uint64_t now;
static jmp_buf stopped;
static void (*callback)(uint, uint32_t);
static void hw_write_masked(uint32_t *p, uint32_t v, uint32_t m) { *p = (*p & ~m) | (v & m); }
static void watchdog_enable(int ms, bool debug) { delay_ms = ms; }
static void tight_loop_contents(void) { longjmp(stopped, 1); }
static bool gpio_get(uint p) { assert(p == 46); return powered; }
static uint64_t time_us_64(void) { return now; }
static void sleep_us(int n) { assert(n == 10); now += n; if (++sleeps == 3) powered = true; }
static void gpio_set_irq_enabled_with_callback(uint p, uint32_t e, bool enable, void (*cb)(uint,uint32_t)) {
    assert(p == 46 && e == GPIO_IRQ_EDGE_FALL && enable); callback = cb;
}
#include "power_guard.h"
static void reset(void) {
    for (int p=0;p<48;p++) bank.io[p].ctrl = 0x123;
    for (int p=0;p<3;p++) pios[p].ctrl = 15;
    wd.scratch[0] = 0xFC010001; delay_ms=0; callback=0;
}
static void verify(void) {
    for (int p=0;p<48;p++) {
        uint32_t expected = (p <= 45 && p != 39) ? (0x123 | (2u << 12)) : 0x123;
        assert(bank.io[p].ctrl == expected);
    }
    assert(pios[0].ctrl == 0 && pios[1].ctrl == 0 && pios[2].ctrl == 0);
    assert(wd.scratch[0] == 0 && delay_ms == 50);
}
int main(void) {
    reset(); powered=true; fc_arm_power_guard(); assert(callback && !delay_ms);
    powered=false;
    if (!setjmp(stopped)) { callback(46, GPIO_IRQ_EDGE_FALL); assert(0); }
    verify(); puts("PASS: falling edge disables PIO/PWM/SIO outputs, preserves LED/PSRAM, resets menu");
    reset(); powered=false;
    if (!setjmp(stopped)) { fc_arm_power_guard(); assert(0); }
    verify(); puts("PASS: low power during arming fails closed without resuming setup");
    powered=false; sleeps=0; now=0; fc_wait_power(); assert(sleeps == 3);
    puts("PASS: waiting detects power at 10us polling interval");
    return 0;
}
'''

def main():
    zig = next(Path(r'C:\Users\Yugo\pico\zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='fc-power-test-') as folder:
        root = Path(folder)
        assert root.resolve().parent == Path(tempfile.gettempdir()).resolve()
        assert root.name.startswith('fc-power-test-')
        for name in ['pico/stdlib.h', 'hardware/pio.h', 'hardware/irq.h', 'hardware/watchdog.h',
                     'hardware/structs/io_bank0.h', 'hardware/structs/sio.h',
                     'hardware/regs/io_bank0.h', 'hardware/sync.h']:
            header = root / name
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text('', encoding='utf-8')
        shutil.copyfile(Path(__file__).resolve().parents[1] / 'power_guard.h', root / 'power_guard.h')
        (root / 'test.c').write_text(SOURCE, encoding='utf-8')
        subprocess.run([str(zig), 'cc', '-O0', '-I', str(root), str(root / 'test.c'), '-o', str(root / 'test.exe')], check=True, timeout=120)
        subprocess.run([str(root / 'test.exe')], check=True, timeout=10)

if __name__ == '__main__':
    main()
