// Full-screen grayscale tile conversion shared with host validation.
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
static uint8_t rd_nt[1024];
static uint32_t rd_tiles[960][4];
static uint16_t rd_tile_ids[960],rd_tile_counts[960],rd_selected[256];
static uint32_t rd_cached_tiles[256][4];
static bool rd_cached_valid[256];
static uint16_t rd_selected_slot[256];
static void remote_full_convert(const uint8_t *fb) {
    uint unique=0;
    for(uint t=0;t<960;t++) {
        uint8_t tile[16];uint tx=t%32,ty=t/32;
        for(uint y=0;y<8;y++)for(uint p=0;p<2;p++)
            tile[y+p*8]=fb[((ty*8+y)*32+tx)*2+p];
        uint id=0;
        while(id<unique && memcmp(rd_tiles[id],tile,16))id++;
        if(id==unique){memcpy(rd_tiles[id],tile,16);rd_tile_counts[id]=0;unique++;}
        rd_tile_counts[id]++;rd_tile_ids[t]=id;
    }
    uint n=unique<256?unique:256;
    // Retain common tiles first; rare excess tiles use the nearest retained one.
    for(uint k=0;k<n;k++) {
        uint best=0;
        for(uint id=1;id<unique;id++)if(rd_tile_counts[id]>rd_tile_counts[best])best=id;
        rd_selected[k]=best;rd_tile_counts[best]=0;
    }
    // Preserve slot identities across frames, independent of frequency ranking.
    // Reserve every exact match before replacing any cached pattern.
    bool reserved[256]={false};
    for(uint k=0;k<n;k++) {
        rd_selected_slot[k]=256;
        for(uint slot=0;slot<256;slot++)
            if(rd_cached_valid[slot] && !reserved[slot] &&
               !memcmp(rd_cached_tiles[slot],rd_tiles[rd_selected[k]],16)) {
                rd_selected_slot[k]=slot;reserved[slot]=true;break;
            }
    }
    for(uint k=0;k<n;k++) {
        uint slot=rd_selected_slot[k];
        if(slot==256) {
            for(slot=0;reserved[slot];slot++){}
            reserved[slot]=true;rd_selected_slot[k]=slot;
            memcpy(rd_cached_tiles[slot],rd_tiles[rd_selected[k]],16);
            rd_cached_valid[slot]=true;
            const uint8_t *b=(const uint8_t *)rd_cached_tiles[slot];
            for(uint i=0;i<16;i++)diag_chr_lookup[slot*16+i]=0xff00u|b[i];
        }
    }
    for(uint t=0;t<960;t++) {
        uint id=rd_tile_ids[t],best=0,error=129;
        for(uint k=0;k<n;k++) {
            uint j=rd_selected[k];
            if(j==id){best=k;break;}
            uint e=0;
            for(uint w=0;w<4;w++)e+=__builtin_popcount(rd_tiles[id][w]^rd_tiles[j][w]);
            if(e<error){error=e;best=k;}
        }
        rd_nt[t]=(uint8_t)rd_selected_slot[best];
    }
    memset(rd_nt+960,0,64);
}
