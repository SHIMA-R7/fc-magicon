#define CART_HOST
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include "../magicon/cart.c"
bool host_irq;
static uint8_t p[128+8192];
static cart_info_t info;
static void header(void) {
 memset(p,0,sizeof p); memcpy(p,"NESM\x1a",5);
 p[5]=1;p[6]=255;p[7]=255;p[9]=p[11]=p[13]=0x80;
}
int main(void) {
 header();assert(!cart_load(p,sizeof p,&info));
 p[5]=3;assert(cart_load(p,sizeof p,&info));
 header();p[5]=2;p[0x7c]=1;assert(cart_load(p,sizeof p,&info));
 header();p[0x7a]=1;assert(cart_load(p,sizeof p,&info));
 header();p[0x7b]=2;assert(cart_load(p,sizeof p,&info));
 header();p[6]=0;assert(cart_load(p,sizeof p,&info));
 header();p[11]=0x50;assert(cart_load(p,sizeof p,&info));
 header();p[9]=0xf0;assert(cart_load(p,sizeof p,&info));
 header();p[5]=2;p[0x7f]=1;assert(cart_load(p,sizeof p,&info));
 header();p[0x70]=1;assert(!cart_load(p,sizeof p,&info));
 nsf_write(0x5ff8,255);assert(nsf_prg[0]==nsf_empty_bank);
 nsf_write(0x5ff8,1);assert(nsf_prg[0]==rom+4096);
 for(unsigned us=1;us<65536;us+=137) {
  nsf_clock_t c;nsf_clock_init(&c,us);nsf_clock_start(&c,true);
  uint64_t total=0;
  for(unsigned k=0;k<1000;k++){total+=c.remaining;nsf_clock_reload(&c);}
  assert(total==((uint64_t)us*1789773*1000)/1000000);
 }
 nsf_clock_start(&nsf_clock,true);uint32_t n=nsf_clock.remaining;
 for(uint32_t k=1;k<n;k++)nsf_clock_tick(&nsf_clock);
 assert(!nsf_clock_take(&nsf_clock));nsf_clock_tick(&nsf_clock);
 assert(nsf_clock_take(&nsf_clock)==1 && !nsf_clock_take(&nsf_clock));
 nsf_clock_start(&nsf_clock,false);nsf_clock_tick(&nsf_clock);assert(!nsf_clock_take(&nsf_clock));
 header();p[0x7b]=1;assert(!cart_load(p,sizeof p,&info));
 nsf_write(0x9000,0x8f);nsf_write(0x9002,128);
 for(unsigned k=0;k<256;k++)nsf_cpu_access(B_RW|B_ROMSEL); // actual M2-header path
 int16_t pcm[8];unsigned got=cart_nsf_audio(pcm,8);assert(got>0 && pcm[got-1]==6000);
 nsf_write(0x5f03,0);for(unsigned k=0;k<256;k++)nsf_cpu_access(B_RW|B_ROMSEL);
 got=cart_nsf_audio(pcm,8);assert(got>0 && pcm[got-1]==0 && !cart_nsf_audio_fault());
 puts("PASS: actual NSF loader, bounds, unsupported modes, banks and fractional timer");
 puts("PASS: actual cartridge write capture -> VRC6 samples; stop resets expansion");
}
