/* Audit reproductions against the actual cart.c, with synthetic headers only. */
#define CART_HOST
#define FC_DIAG_CPU_ONLY 1
#define FC_DIAG_DIRECT_CHR 1
#include <stdio.h>
#include <assert.h>
#include <stdlib.h>
#include "../magicon/cart.c"
bool host_irq;
static uint8_t image[16 + 0x8000 + 0x2000];
static void load(int m, int flags, int chrn) {
    memset(image, 0, sizeof image);
    memcpy(image, "NES\x1a", 4);
    image[4]=2; image[5]=chrn; image[6]=(m<<4)|flags; image[7]=m&0xf0;
    cart_info_t i; const char *e=cart_load(image,sizeof image,&i);
    if(e){puts(e);exit(2);}
}
int main(int argc,char **argv) {
    cart_info_t i;
    if(argc>1) {
        uint8_t n[128]={0}; memcpy(n,"NESM\x1a",5);n[5]=1;n[6]=1;n[7]=1;n[9]=0x80;n[0x70]=1;
        const char *e=cart_load(n,sizeof n,&i);assert(e); printf("PASS empty NSF rejected: %s\n",e);return 0;
    }
    load(0,0,0); ppu_w=false;ppu_t=ppu_v=0;
    ppu_reg_write(0x2005,0x28); /* first scroll: coarse X=5 */
    ppu_reg_write(0x2005,0);
    ppu_reg_write(0x2006,0); /* first address write retains coarse X */
    ppu_reg_write(0x2005,0); /* second scroll copies t's coarse X unchanged */
    assert((ppu_t & 31) == 5);
    printf("scroll/address mixed: t coarse X=%u (expected 5)\n",ppu_t&31);
    load(4,0,1);wram[0]=0x19;mmc3_write(0xa001,0xc0);cpu_write(0x6000,0x72);
    assert(wram[0] == 0x19);
    printf("MMC3 protected WRAM=%02x (expected 19)\n",wram[0]);
    image[6]=8; assert(cart_load(image,sizeof image,&i)); puts("PASS four-screen rejected");
    image[6]=0;image[7]=8;image[8]=1;
    const char *e=cart_load(image,sizeof image,&i);
    assert(e);
    printf("NES2 mapper256: %s mapper=%d (expected rejection)\n",e?e:"ACCEPTED",i.mapper);
    load(1,0,0);m1_prg=1;mmc1_update();load(1,0,0);
    assert(m1_prg == 0);
    printf("second MMC1 load: bank=%u (expected reset bank 0)\n",m1_prg);
    load(1,0,0); m1_prg=0x10;mmc1_update();assert(!wram_enabled);
    load(4,0,1);mmc3_write(0xa001,0);assert(!wram_enabled);
    puts("PASS mapper and register regression checks");
    diag_marks=0;
    diag_record_cpu(B_RW | (0x4100u << 8),0x8000ffea);
    assert(diag_trace_count==0); // initialization cannot trigger trace
    diag_marks=23;
    diag_record_cpu(B_RW | B_ROMSEL,0x80000000); // internal RAM $00
    diag_record_cpu(B_RW | (0x4079u << 8),0x8000ffc0); // last JMP operand
    assert(diag_trace_count==0);
    uint32_t bad=B_RW | (0x4100u << 8);
    diag_record_cpu(bad,0x8000ffea);
    assert(diag_trace_count==2 && diag_trace_mark==23);
    assert(diag_trace[0][0]==(B_RW | (0x4079u<<8)) && diag_trace[1][0]==bad);
    assert(diag_trace[1][1]==0x8000ffea);
    for(int n=0;n<32;n++)diag_record_cpu(bad+n,0x8000ffea);
    assert(diag_trace_count==16 && diag_trace[1][0]==bad);
    puts("PASS bounded unexpected CPU-address trace");
    wr_pending=false;diag_marks=diag_mark_errors=stat_cpu=stat_wr=0;
    diag_nrom_bookkeeping(0); // write header for $8000
    assert(wr_pending && wr_addr==0x8000 && stat_cpu==1);
    diag_nrom_bookkeeping(0xff);
    assert(!wr_pending && diag_marks==1 && stat_wr==1);
    diag_nrom_bookkeeping(0);diag_nrom_bookkeeping(0); // wrap FF -> 00
    assert(diag_mark_errors==0 && diag_marks==2);
    diag_nrom_bookkeeping(0);diag_nrom_bookkeeping(2);
    assert(diag_mark_errors==1 && diag_marks==3);
    diag_nrom_bookkeeping(B_ROMSEL | (0x2007u<<8));diag_nrom_bookkeeping(0x22);
    assert(diag_marks==3 && stat_wr==4); // non-marker writes only counted
    diag_nrom_bookkeeping(B_RW | (0x4077u<<8));
    assert(!wr_pending && stat_cpu==5);
    puts("PASS lightweight NROM diagnostic bookkeeping");
    cart_load_fallback(&i);
    for(unsigned bank=0;bank<2;bank++) {
        for(unsigned k=0;k<16;k++)assert(rom[bank*0x4000+0x7b+k]==((const uint8_t[]){0x0f,0x30,0x10,0x0f}[k%4]));
        assert(rom[bank*0x4000+0x77]==0x4c && rom[bank*0x4000+0x79]==0xc0);
    }
    puts("PASS black/white diagnostic palettes, loop preserved");
    return 0;
}
