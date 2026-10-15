#define CART_HOST
#define FC_DIAG_CPU_ONLY 1
#define FC_DIAG_NROM_GAME 1
#define FC_DIAG_MMC3_GAME 1
#undef NDEBUG
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include "../magicon/cart.c"
bool host_irq;
int main(void) {
    uint8_t *image=calloc(1,16+0x60000);assert(image);
    memcpy(image,"NES\x1a",4);image[4]=16;image[5]=16;image[6]=0x41;
    cart_info_t info;assert(!cart_load(image,16+0x60000,&info));
    // Independent MMC3 register vectors, not only comparison with our mapper.
    mmc3_game_write(0x8000,6);mmc3_game_write(0x8001,5);
    mmc3_game_write(0x8000,7);mmc3_game_write(0x8001,9);
    assert(prg_map[0]==prg+5*8192 && prg_map[1]==prg+9*8192);
    assert(prg_map[2]==prg+30*8192 && prg_map[3]==prg+31*8192);
    mmc3_game_write(0x8000,0x46);
    assert(prg_map[0]==prg+30*8192 && prg_map[2]==prg+5*8192);
    const uint8_t chr_regs[]={3,5,7,9,11,13};
    const uint8_t chr_banks[]={2,3,4,5,7,9,11,13};
    for(uint r=0;r<6;r++){mmc3_game_write(0x8000,r);mmc3_game_write(0x8001,chr_regs[r]);}
    for(uint r=0;r<6;r++)mmc3_fast_chr(r);
    for(uint i=0;i<8;i++)assert(chr_map[i]==chr+chr_banks[i]*1024);
    mmc3_game_write(0x8000,0x80);
    for(uint r=0;r<6;r++)mmc3_fast_chr(r);
    for(uint i=0;i<8;i++)assert(chr_map[i^4]==chr+chr_banks[i]*1024);
    const uint values[]={0,1,2,63,64,127,128,255};
    for(uint mode=0;mode<4;mode++)for(uint reg=0;reg<8;reg++)for(uint i=0;i<8;i++) {
        mmc3_game_write(0x8000,(mode<<6)|reg);mmc3_game_write(0x8001,values[i]);
        for(uint r=0;r<6;r++)mmc3_fast_chr(r); // deferred core0 work
        uint8_t *p[4],*c[8];memcpy(p,prg_map,sizeof p);memcpy(c,chr_map,sizeof c);
        mmc3_update(); // compare full existing mapping implementation
        assert(!memcmp(p,prg_map,sizeof p) && !memcmp(c,chr_map,sizeof c));
    }
    mmc3_game_write(0xc000,2);mmc3_game_write(0xc001,0);mmc3_game_write(0xe001,0);
    mmc3_clock();assert(m3_count==2);mmc3_clock();assert(m3_count==1);
    mmc3_clock();assert(m3_count==0);
#if FC_DIAG_MMC3_NO_IRQ
    assert(!host_irq);
#else
    assert(host_irq);
#endif
    mmc3_game_write(0xe000,0);assert(!host_irq);
    // A CPU reload arriving after the IRQ core's snapshot must survive its ACK.
    mmc3_game_write(0xc000,7);mmc3_game_write(0xc001,0);
    uint32_t observed=atomic_load_explicit(&m3_reload_requested,memory_order_acquire);
    mmc3_game_write(0xc001,0);
    mmc3_clock_snapshot(observed);
    assert(m3_reload_handled==observed);
    assert(atomic_load_explicit(&m3_reload_requested,memory_order_acquire)!=m3_reload_handled);
    mmc3_clock();assert(m3_count==7);
    assert(atomic_load_explicit(&m3_reload_requested,memory_order_acquire)==m3_reload_handled);
    atomic_store_explicit(&m3_reload_requested,UINT32_MAX,memory_order_relaxed);
    m3_reload_handled=UINT32_MAX;mmc3_game_write(0xc001,0);
    mmc3_clock();assert(m3_count==7 && m3_reload_handled==0);
    mmc3_game_write(0xa001,0xc0);assert(wram_enabled && wram_protected);
    mmc3_game_write(0xa001,0);assert(!wram_enabled);
    free(image);puts("PASS MMC3 independent vectors, 256 bank cases, IRQ reload race/wrap and WRAM protection");
}
