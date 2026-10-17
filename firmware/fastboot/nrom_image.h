#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>

static inline const char *fc_load_nrom_image(const uint8_t *slot,size_t available,
        uint8_t *prg,uint8_t *chr,bool *vertical) {
    if (available<16) return "short slot";
    uint32_t len,sum;
    memcpy(&len,slot+4,4); memcpy(&sum,slot+8,4);
    if (memcmp(slot,"FCMG",4) || len<16 || len>16+32768+8192 || len>available-16)
        return "requires a single FCMG NROM image";
    const uint8_t *p=slot+16;
    uint32_t actual=0;
    for (uint32_t i=0;i<len;i++) actual+=p[i];
    if (actual!=sum) return "checksum mismatch";
    // Only NTSC iNES mapper0 / CHR-ROM; trainer and battery need extra handling.
    if (memcmp(p,"NES\x1a",4) || (p[4]!=1 && p[4]!=2) || p[5]!=1 ||
        (p[6]&0xfe) || p[7] || p[8]>1 || p[9] || p[10])
        return "only NTSC iNES mapper0 / CHR-ROM supported";
    uint32_t off=16,size=(uint32_t)p[4]*16384;
    if (len!=off+size+8192) return "invalid NROM length";
    uint16_t reset=(uint16_t)p[off+size-4] | ((uint16_t)p[off+size-3]<<8);
    if (reset<0x8000) return "reset vector outside PRG";
    // No output buffers are changed until all validation succeeds.
    memcpy(prg,p+off,size);
    if (size==16384) memcpy(prg+16384,prg,16384);
    memcpy(chr,p+off+size,8192);
    *vertical=!!(p[6]&1);
    return NULL;
}
