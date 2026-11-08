#pragma once
#include "tusb.h"

static uint8_t desktop_cdc = UINT8_MAX;

void tuh_cdc_mount_cb(uint8_t idx) { desktop_cdc = idx; }
void tuh_cdc_umount_cb(uint8_t idx) {
    if (idx == desktop_cdc) desktop_cdc = UINT8_MAX;
}
uint32_t tusb_time_millis_api(void) { return time_us_64() / 1000; }

static bool desktop_connected(void) { return desktop_cdc != UINT8_MAX; }
static uint32_t desktop_write_available(void) { return tuh_cdc_write_available(desktop_cdc); }
static void desktop_write(const void *packet, uint32_t size) {
    tuh_cdc_write(desktop_cdc, packet, size);
    tuh_cdc_write_flush(desktop_cdc);
}
