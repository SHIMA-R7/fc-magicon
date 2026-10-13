// Experimental position decoder: nametable gives coarse Y/column, CHR gives fine Y.
// Inspired by the documented PPUppy approach; independently implemented.
// Host-validated only: the current RP2350 DMA path does not yet feed these events.
#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef struct { uint16_t coarse_y; uint8_t column; bool valid; } remote_position;
static inline void remote_position_name(remote_position *position, uint16_t address) {
    uint16_t offset=address&0x3ff;
    if (offset>=960) return; // Attribute addresses do not identify the tile row.
    position->coarse_y=(uint16_t)((offset>>5)*8);
    position->column=(uint8_t)(offset&31);
    position->valid=true;
}
static inline bool remote_position_byte(const remote_position *position, uint16_t address,
    uint16_t *offset) {
    if (!position->valid || (address&0x1000)) return false; // Sprite table belongs to native CHR.
    uint16_t y=(uint16_t)(position->coarse_y+(address&7));
    if (y>=240) return false;
    *offset=(uint16_t)((y*32+position->column)*2+((address>>3)&1));
    return true;
}
