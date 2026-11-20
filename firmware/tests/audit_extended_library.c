// Actual cart.c, including mapper state; no copyrighted ROM content in this test.
#define CART_HOST
#define CART_EXTENDED_ROM 1
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "../magicon/cart.c"
bool host_irq;

static void large_mmc3(void) {
    const size_t length = 16 + 512 * 1024 + 256 * 1024;
    uint8_t *image = calloc(1, length);
    assert(image);
    memcpy(image, "NES\x1a", 4);
    image[4] = 32; image[5] = 32; image[6] = 0x42;
    for (uint32_t i=16; i<length; i++) image[i]=(uint8_t)(i ^ (i>>8) ^ (i>>16));
    cart_info_t info;
    assert(!cart_load(image, (uint32_t)length, &info));
    assert(active_rom == large_rom);
    assert(chr == (FC_GAME_PRG_SRAM ? large_rom+512*1024 : rom));
    assert(!memcmp(chr, image + 16 + 512*1024, 256*1024));
    // PRG register 6 exposes every 8KB bank, including banks >= 384KB.
    for (uint bank=0; bank<64; bank++) {
        mmc3_write(0x8000, 6); mmc3_write(0x8001, bank);
        assert(!memcmp(prg_map[0], image + 16 + bank*8192, 8192));
#if FC_GAME_PRG_SRAM
        if(bank>=16)assert(prg_map[0]>=rom && prg_map[0]+8192<=rom+sizeof rom);
        else assert(prg_map[0]==large_rom+bank*8192);
#endif
    }
    // 1KB CHR banks must wrap at 256KB, preserving the full eight-bit index.
    for (uint bank=0; bank<256; bank++) {
        mmc3_write(0x8000, 2); mmc3_write(0x8001, bank);
        assert(!memcmp(chr_map[4], image + 16 + 512*1024 + bank*1024, 1024));
    }
    const uint values[]={0,1,2,63,64,127,128,255};
    for(uint mode=0;mode<4;mode++)for(uint reg=0;reg<8;reg++)for(uint j=0;j<8;j++) {
        mmc3_write(0x8000,(mode<<6)|reg);mmc3_write(0x8001,values[j]);
        uint8_t *p[4],*c[8];memcpy(p,prg_map,sizeof p);memcpy(c,chr_map,sizeof c);
        mmc3_update();
        assert(!memcmp(p,prg_map,sizeof p) && !memcmp(c,chr_map,sizeof c));
    }
#if FC_DIAG_MMC3_GAME
    // Exercise the actual fast write handler used by the preserved CPU loop,
    // including SRAM-cached and PSRAM-backed PRG banks, against full mapping.
    for(uint mode=0;mode<4;mode++)for(uint reg=0;reg<8;reg++)for(uint j=0;j<8;j++) {
        mmc3_game_write(0x8000,(mode<<6)|reg);
        mmc3_game_write(0x8001,values[j]);
        for(uint r=0;r<6;r++)mmc3_fast_chr(r);
        uint8_t *p[4],*c[8];memcpy(p,prg_map,sizeof p);memcpy(c,chr_map,sizeof c);
        mmc3_update();
        assert(!memcmp(p,prg_map,sizeof p) && !memcmp(c,chr_map,sizeof c));
    }
    puts("PASS preserved MMC3 fast writes: all modes/registers and PRG cache boundaries");
    for(uint mode=0;mode<4;mode++)for(uint reg=0;reg<8;reg++)for(uint j=0;j<8;j++) {
        uint expected=((m3_sel^((mode<<6)|reg))&0x40)?5:0;
        assert(mmc3_dma_write(0x8000,(mode<<6)|reg)==expected);
        uint mask=mmc3_dma_write(0x8001,values[j]);
        assert(mask==(reg==6?(1u<<((m3_sel>>5)&2)):reg==7?2:0));
        for(uint r=0;r<6;r++)mmc3_fast_chr(r);
        uint8_t *p[4],*c[8];memcpy(p,prg_map,sizeof p);memcpy(c,chr_map,sizeof c);
        mmc3_update();assert(!memcmp(p,prg_map,sizeof p)&&!memcmp(c,chr_map,sizeof c));
    }
    puts("PASS DMA mapper writes and lane-publication masks");
#endif
    // Returning to the menu must restore SRAM storage and reset mapper state.
    lib_entry_t entries[14] = {0};
    strcpy(entries[0].name,"FIRST GAME"); strcpy(entries[13].name,"LAST GAME");
    cart_load_menu(entries, 14, &info);
    assert(info.is_menu && active_rom == rom && mapper == 0);
    assert(active_rom[MENUD_COUNT] == 14 && cart_menu_choice() == -1);
#if FC_GAME_FAST_NROM
    assert(nrom_replies);
    for(uint a=0;a<32768;a++)assert(nrom_replies[a]==(0x8000ff00u|rom[a]));
    nrom_bookkeeping((0x5ff0u<<8)|B_ROMSEL);
    nrom_bookkeeping(13);
    assert(cart_menu_choice()==13 && !wr_pending);
    cart_load_menu(entries,14,&info);
    nrom_bookkeeping((0x6000u<<8)|B_ROMSEL);nrom_bookkeeping(0x5a);
    assert(wram[0]==0x5a && !wr_pending);
    nrom_bookkeeping((0x5ff1u<<8)|B_ROMSEL);nrom_bookkeeping(0x90);
    assert(menu_pad==0x90);
#endif
    cpu_write(0x5ff0, 13); assert(cart_menu_choice() == 13);
    cart_load_menu(entries, 14, &info);
    cpu_write(0x5ff0, 14); assert(cart_menu_choice() == -1);
    free(image);
    puts("PASS 768KB MMC3: all 64 PRG banks, 256 CHR banks, menu return and bounds");
}

int main(int argc, char **argv) {
    assert(cart_storage_selftest());
    large_mmc3();
    for (int k=1; k<argc; k++) {
        FILE *f=fopen(argv[k],"rb"); assert(f);
        fseek(f,0,SEEK_END); long n=ftell(f); rewind(f); assert(n>16);
        uint8_t *data=malloc((size_t)n); assert(data);
        assert(fread(data,1,(size_t)n,f)==(size_t)n); fclose(f);
        cart_info_t info; const char *err=cart_load(data,(uint32_t)n,&info);
        if(err) { fprintf(stderr,"%s: %s\n",argv[k],err); return 1; }
        uint off=16+((data[6]&4)?512:0);
        assert(!memcmp(prg,data+off,info.prg_size));
        if(info.chr_size) assert(!memcmp(chr,data+off+info.prg_size,info.chr_size));
        printf("LOAD PASS mapper=%d PRG=%u CHR=%u %s\n",info.mapper,
               info.prg_size,info.chr_size,argv[k]);
        free(data);
    }
    return 0;
}
