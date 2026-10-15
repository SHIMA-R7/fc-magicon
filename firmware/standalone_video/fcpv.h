#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>

#define FCPV_HEADER 64u
#define FCPV_FRAME 5152u
typedef struct {
    uint32_t frames,fps_num,fps_den,rate,samples,video,audio,total,crc;
} fcpv_info;
static inline uint32_t fcpv_u32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline bool fcpv_parse(const uint8_t *p,size_t available,fcpv_info *out) {
    if(available<FCPV_HEADER || memcmp(p,"FCPV",4) || fcpv_u32(p+4)!=1 ||
       fcpv_u32(p+8)!=FCPV_HEADER || fcpv_u32(p+32)!=FCPV_FRAME ||
       fcpv_u32(p+52)!=1 || fcpv_u32(p+56) || fcpv_u32(p+60)) return false;
    fcpv_info v={fcpv_u32(p+12),fcpv_u32(p+16),fcpv_u32(p+20),fcpv_u32(p+24),
        fcpv_u32(p+28),fcpv_u32(p+36),fcpv_u32(p+40),fcpv_u32(p+44),fcpv_u32(p+48)};
    if(!v.frames || !v.samples || !v.fps_num || !v.fps_den || v.rate!=32000 ||
       v.video!=FCPV_HEADER || (uint64_t)v.fps_num>8ull*v.fps_den ||
       v.fps_num>1000 || v.fps_den>1000 || v.total>available ||
       (uint64_t)v.video+(uint64_t)v.frames*FCPV_FRAME!=v.audio ||
       (uint64_t)v.audio+v.samples!=v.total) return false;
    uint64_t video_time=(uint64_t)v.frames*v.fps_den*v.rate;
    uint64_t audio_time=(uint64_t)v.samples*v.fps_num;
    uint64_t difference=video_time>audio_time ? video_time-audio_time : audio_time-video_time;
    if(difference>(uint64_t)v.rate*v.fps_num/10) return false; // <=100ms rounding/trimming
    *out=v;return true;
}
static inline uint32_t fcpv_crc32(const uint8_t *p,size_t size) {
    uint32_t crc=0xffffffffu;
    for(size_t i=0;i<size;i++) {
        crc^=p[i];
        for(unsigned b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));
    }
    return ~crc;
}
// Schedule approximately 6.5 NTSC frames ahead for seven-VBlank staging.
// All times are in source audio samples: the PIO clock is the playback clock.
static inline bool fcpv_frame_due(const fcpv_info *v,uint32_t next,uint32_t played) {
    uint32_t lead=(uint32_t)((uint64_t)v->rate*13*1001/120000);
    return (uint64_t)(played+lead)*v->fps_num >= (uint64_t)next*v->rate*v->fps_den;
}
