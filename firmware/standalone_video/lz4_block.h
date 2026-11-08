#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
// Independent raw LZ4 block, exact output length, no allocation/dictionary.
static inline bool lz4_block_decode(const uint8_t *src,size_t size,uint8_t *dst,size_t output) {
    size_t ip=0,op=0;
    while(ip<size) {
        unsigned token=src[ip++];size_t length=token>>4;
        if(length>output-op)return false;
        if(length==15) {
            unsigned extra;
            do {
                if(ip>=size)return false;
                extra=src[ip++];
                if(extra>output-op-length)return false;
                length+=extra;
            } while(extra==255);
        }
        if(length>size-ip)return false;
        memcpy(dst+op,src+ip,length);op+=length;ip+=length;
        if(ip==size)return op==output;
        if(size-ip<2)return false;
        unsigned offset=(unsigned)src[ip]|((unsigned)src[ip+1]<<8);ip+=2;
        if(!offset || offset>op)return false;
        length=4+(token&15);
        if(length>output-op)return false;
        if((token&15)==15) {
            unsigned extra;
            do {
                if(ip>=size)return false;
                extra=src[ip++];
                if(extra>output-op-length)return false;
                length+=extra;
            } while(extra==255);
        }
        for(size_t i=0;i<length;i++){dst[op]=dst[op-offset];op++;}
    }
    return false;
}
