#pragma once
#include "hardware/flash.h"
#include "hardware/dma.h"
#include "hardware/sync.h"
#include "hardware/watchdog.h"
#include "hardware/regs/watchdog.h"
#include "pico/bootrom.h"
#include "boot/picoboot_constants.h"
#include "pico/multicore.h"

// Updates also run with FC-supplied power: release the bus before flash access,
// then require an external power cycle before cartridge execution resumes.
#define USB_UPDATE_MAX (128u * 1024u)
#define USB_UPDATE_CHUNK 1024u
static uint8_t __uninitialized_ram(update_image)[USB_UPDATE_MAX] __attribute__((aligned(256)));
static bool desktop_host_started;
static bool update_quiesced;

static void desktop_host_init(void) {
    if (desktop_host_started) return;
    const tusb_rhport_init_t host = {.role = TUSB_ROLE_HOST, .speed = TUSB_SPEED_AUTO};
    if (!tusb_rhport_init(0, &host)) panic("USB host initialization failed");
    desktop_host_started = true;
}

static uint32_t update_crc(const uint8_t *data, uint32_t size) {
    uint32_t crc = UINT32_MAX;
    for (uint32_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static bool update_read(uint8_t *data, uint32_t size) {
    absolute_time_t deadline = make_timeout_time_ms(5000);
    while (size) {
        tuh_task();
        if (!desktop_connected() || time_reached(deadline)) return false;
        uint32_t got = tuh_cdc_read(desktop_cdc, data, size);
        data += got;
        size -= got;
    }
    return true;
}

static void update_reply(uint32_t status, uint32_t received, uint32_t crc) {
    uint32_t packet[4] = {0x41554346u, status, received, crc}; // FCUA
    if (!desktop_connected()) return;
    desktop_write(packet, sizeof packet);
    // Pump the USB controller so even the final response reaches the C6.
    absolute_time_t until = make_timeout_time_ms(10);
    while (!time_reached(until)) tuh_task();
}

static void __attribute__((noreturn)) __no_inline_not_in_flash_func(update_flash)(
        uint32_t size, uint32_t crc, rom_reboot_fn reboot) {
    uint32_t erase_size = (size + FLASH_SECTOR_SIZE - 1) & ~(FLASH_SECTOR_SIZE - 1);
    uint32_t write_size = (size + FLASH_PAGE_SIZE - 1) & ~(FLASH_PAGE_SIZE - 1);
    save_and_disable_interrupts();
    flash_range_erase(0, erase_size);
    flash_range_program(0, update_image, write_size);
    const volatile uint8_t *written = (const volatile uint8_t *)XIP_BASE;
    bool verified = true;
    for (uint32_t i = 0; i < size; ++i) {
        if (written[i] != update_image[i]) verified = false;
    }
    // Never return into the old firmware's XIP code after replacing it.
    if (!verified) {
        reboot(REBOOT2_FLAG_NO_RETURN_ON_SUCCESS | REBOOT2_FLAG_REBOOT_TYPE_BOOTSEL,
               10, 0, 0);
    }
    watchdog_hw->scratch[6] = size;
    watchdog_hw->scratch[7] = crc;
    watchdog_hw->scratch[5] = 0x55504432u;
    watchdog_hw->scratch[4] = 0; // normal flash boot, preserving result in 5..7
    watchdog_hw->ctrl |= WATCHDOG_CTRL_TRIGGER_BITS;
    for (;;) __asm volatile("wfi");
}

static void update_quiesce(void) {
    if (update_quiesced) return;
    // Release cartridge outputs first. The FC is reset by DP100 after completion.
    for (uint pin = 0; pin <= 45; ++pin) gpio_set_oeover(pin, GPIO_OVERRIDE_LOW);
    gpio_set_irq_enabled(46, GPIO_IRQ_EDGE_FALL, false);
    pio0->ctrl = pio1->ctrl = pio2->ctrl = 0;
    for (uint channel = 0; channel < NUM_DMA_CHANNELS; ++channel) {
        dma_channel_set_irq0_enabled(channel, false);
        dma_channel_set_irq1_enabled(channel, false);
        dma_channel_abort(channel);
    }
    multicore_reset_core1();
    watchdog_disable();
    watchdog_hw->scratch[0] = 0;
    update_quiesced = true;
}

static void update_receive(void) {
    uint32_t header[4];
    if (!update_read((uint8_t *)header, sizeof header)) return;
    uint32_t size = header[1], crc = header[2];
    if (header[0] != 1 || header[3] != 0 || size < 512 || size > USB_UPDATE_MAX) {
        update_reply(0x100, 0, 0);
        return;
    }
    memset(update_image, 0xff, sizeof update_image);
    update_reply(0, 0, crc);
    uint32_t received = 0;
    while (received < size) {
        uint32_t chunk[2];
        if (!update_read((uint8_t *)chunk, sizeof chunk)) return;
        if (chunk[0] != received || chunk[1] == 0 || chunk[1] > USB_UPDATE_CHUNK ||
            chunk[1] > size - received) {
            update_reply(0x102, received, 0);
            return;
        }
        if (!update_read(update_image + received, chunk[1])) return;
        received += chunk[1];
        update_reply(1, received, crc);
    }

    uint32_t actual_crc = update_crc(update_image, size);
    if (actual_crc != crc) {
        update_reply(0x103, received, actual_crc);
        return;
    }
    const uint32_t *vectors = (const uint32_t *)update_image;
    uint32_t reset = vectors[1] & ~1u;
    if (vectors[0] < 0x20000000u || vectors[0] > 0x20082000u ||
        (vectors[0] & 7u) || !(vectors[1] & 1u) ||
        reset < XIP_BASE || reset >= XIP_BASE + size) {
        update_reply(0x104, received, actual_crc);
        return;
    }
    update_quiesce();
    watchdog_enable(10000, true);
    update_flash(size, actual_crc, (rom_reboot_fn)rom_func_lookup(ROM_FUNC_REBOOT));
}

static void update_media(void) {
    uint32_t header[4];
    if (!update_read((uint8_t *)header, sizeof header)) return;
    uint32_t size = header[1], expected = header[2];
    if (header[0] != 2 || header[3] != 0x100000u || size < 64 ||
        size > PICO_FLASH_SIZE_BYTES - 0x100000u) {
        update_reply(0x100, 0, 0);
        return;
    }
    update_quiesce();
    update_reply(0, 0, expected);
    uint32_t received = 0, crc = UINT32_MAX;
    while (received < size) {
        uint32_t chunk[2];
        if (!update_read((uint8_t *)chunk, sizeof chunk)) return;
        uint32_t length = size - received;
        if (length > FLASH_SECTOR_SIZE) length = FLASH_SECTOR_SIZE;
        if (chunk[0] != received || chunk[1] != length) {
            update_reply(0x102, received, 0);
            return;
        }
        memset(update_image, 0xff, FLASH_SECTOR_SIZE);
        if (!update_read(update_image, length)) return;
        if (!received && memcmp(update_image, "FCPV", 4)) {
            update_reply(0x104, 0, 0);
            return;
        }
        uint32_t interrupts = save_and_disable_interrupts();
        flash_range_erase(0x100000u + received, FLASH_SECTOR_SIZE);
        uint32_t padded = (length + FLASH_PAGE_SIZE - 1) & ~(FLASH_PAGE_SIZE - 1);
        flash_range_program(0x100000u + received, update_image, padded);
        restore_interrupts(interrupts);
        if (memcmp((const void *)(XIP_BASE + 0x100000u + received), update_image, length)) {
            update_reply(0x105, received, 0);
            return;
        }
        for (uint32_t i = 0; i < length; ++i) {
            crc ^= update_image[i];
            for (unsigned bit = 0; bit < 8; ++bit)
                crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
        }
        received += length;
        update_reply(1, received, expected);
    }
    update_reply((~crc == expected) ? 2 : 0x103, received, ~crc);
}

static void update_completion_wait(void) {
    if (watchdog_hw->scratch[5] != 0x55504432u) return;
    desktop_host_init();
    while (!desktop_connected()) tuh_task();
    update_reply(2, watchdog_hw->scratch[6], watchdog_hw->scratch[7]);
    watchdog_hw->scratch[5] = 0;
    // All pins are still inputs. Wait for the external DP100 power cycle.
    for (;;) tuh_task();
}

static void update_poll(void) {
    static uint32_t match;
    desktop_host_init();
    tuh_task();
    if (!desktop_connected()) { match = 0; return; }
    uint8_t c;
    while (tuh_cdc_read(desktop_cdc, &c, 1) == 1) {
        match = (match << 8) | c;
        if (match == 0x46435550u || match == 0x4643504du) {
            bool media = match == 0x4643504du;
            match = 0;
            if (media) update_media(); else update_receive();
            return;
        }
    }
}

static void desktop_update_wait(void) {
    if (gpio_get(46)) return; // Preserve the normal cold-start timing.
    desktop_host_init();
    uint32_t match = 0;
    while (!gpio_get(46)) {
        tuh_task();
        if (!desktop_connected()) {
            match = 0;
            continue;
        }
        if (watchdog_hw->scratch[5] == 0x55504432u) {
            update_reply(2, watchdog_hw->scratch[6], watchdog_hw->scratch[7]);
            watchdog_hw->scratch[5] = 0;
        }
        uint8_t c;
        if (tuh_cdc_read(desktop_cdc, &c, 1) != 1) continue;
        match = (match << 8) | c;
        if (match == 0x46435550u) { // FCUP
            match = 0;
            update_receive();
        }
    }
}
