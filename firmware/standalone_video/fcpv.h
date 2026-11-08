#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include "ima_adpcm.h"
#include "lz4_block.h"

#define FCPV_HEADER 64u
#define FCPV_FRAME 5152u
typedef struct {
    uint32_t frames,fps_num,fps_den,rate,samples,video,audio,total,crc;
    bool adpcm;
    bool full_tiles;
    uint32_t record;
    bool packed_video;
} fcpv_info;
static inline uint32_t fcpv_u32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline bool fcpv_parse(const uint8_t *p,size_t available,fcpv_info *out) {
    if(available<FCPV_HEADER)return false;
    bool packed_video=fcpv_u32(p+4)==4;
    bool full_tiles=fcpv_u32(p+4)==3 || packed_video;
    bool compressed=fcpv_u32(p+4)==2 || full_tiles;
    uint32_t record=full_tiles?15456u:FCPV_FRAME;
    if(memcmp(p,"FCPV",4) || (!compressed && fcpv_u32(p+4)!=1) ||
       fcpv_u32(p+8)!=FCPV_HEADER || fcpv_u32(p+32)!=record ||
       fcpv_u32(p+52)!=(compressed?2u:1u) ||
       fcpv_u32(p+56)!=(compressed?IMA_SAMPLES:0u) || fcpv_u32(p+60)) return false;
    fcpv_info v={fcpv_u32(p+12),fcpv_u32(p+16),fcpv_u32(p+20),fcpv_u32(p+24),
        fcpv_u32(p+28),fcpv_u32(p+36),fcpv_u32(p+40),fcpv_u32(p+44),fcpv_u32(p+48)};
    if(!v.frames || !v.samples || !v.fps_num || !v.fps_den || v.rate!=32000 ||
       v.video!=FCPV_HEADER || (uint64_t)v.fps_num>8ull*v.fps_den ||
       v.fps_num>1000 || v.fps_den>1000 || v.total>available ||
       (!packed_video && (uint64_t)v.video+(uint64_t)v.frames*record!=v.audio) ||
       (uint64_t)v.audio+(compressed?((uint64_t)v.samples+255)/256*IMA_BYTES:v.samples)!=v.total) return false;
    v.adpcm=compressed;
    v.full_tiles=full_tiles;v.record=record;v.packed_video=packed_video;
    if(packed_video) {
        uint64_t index_end=(uint64_t)v.video+((uint64_t)v.frames+1u)*4u;
        if(index_end>v.audio || fcpv_u32(p+v.video)!=index_end)return false;
        uint32_t previous=(uint32_t)index_end;
        for(uint32_t i=1;i<=v.frames;i++) {
            uint32_t next=fcpv_u32(p+v.video+i*4u);
            if(next<=previous || next>v.audio || next-previous<2 || p[previous]>1)return false;
            previous=next;
        }
        if(previous!=v.audio)return false;
    }
    if(compressed)for(uint32_t at=v.audio;at<v.total;at+=IMA_BYTES)
        if(p[at+2]>88 || p[at+3])return false;
    uint64_t video_time=(uint64_t)v.frames*v.fps_den*v.rate;
    uint64_t audio_time=(uint64_t)v.samples*v.fps_num;
    uint64_t difference=video_time>audio_time ? video_time-audio_time : audio_time-video_time;
    if(difference>(uint64_t)v.rate*v.fps_num/10) return false; // <=100ms rounding/trimming
    *out=v;return true;
}
static inline bool fcpv_unpack_frame(const uint8_t *media,const fcpv_info *v,uint32_t frame,uint8_t *out,size_t size) {
    if(!v->packed_video || frame>=v->frames || size<15456)return false;
    uint32_t begin=fcpv_u32(media+v->video+frame*4u);
    uint32_t end=fcpv_u32(media+v->video+(frame+1u)*4u);
    if(end<=begin+1u || end>v->audio || media[begin]>1)return false;
    if(!lz4_block_decode(media+begin+1u,end-begin-1u,out,15456))return false;
    if(media[begin])for(unsigned i=64;i<15360;i++)out[i]^=out[i-64];
    return true;
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
    if(v->full_tiles)lead=(uint32_t)((uint64_t)v->rate*1001/120000);
    return (uint64_t)(played+lead)*v->fps_num >= (uint64_t)next*v->rate*v->fps_den;
}
