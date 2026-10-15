#pragma once
#include <stdbool.h>
#include <stdint.h>
// Reuse the tested 48-byte 6502 bootstrap / release-acquire mailbox protocol.
#include "../fastboot/boot_protocol.h"

void cart_boot_prepare(void); // configure CPU PIO / SRAM responder before full cart_load
void cart_boot_enable(void);  // call only after FC power guard has been armed

// Also used by the host test to exercise the same core1 protocol.
void cart_boot_reset_protocol(void);
void cart_boot_publish(void);
bool cart_boot_active(void);
uint32_t cart_boot_cpu_access(uint32_t header);
