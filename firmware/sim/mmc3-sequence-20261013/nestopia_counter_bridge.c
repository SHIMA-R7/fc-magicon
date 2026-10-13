// Validation-only adapter: actual cartridge counter, Nestopia CPU/PPU clock.
#define CART_HOST
#include "../../magicon/cart.c"
bool host_irq;
static uint64_t fc_epoch,fc_low_m2;
static bool fc_a12_high;
static void fc_chr_reset(void);
void fc_mmc3_reset(void){
 m3_latch=m3_count=0;m3_irq_en=false;host_irq=false;
 atomic_store_explicit(&m3_reload_requested,0,memory_order_relaxed);m3_reload_handled=0;
 fc_epoch=fc_low_m2=0;fc_a12_high=false;fc_chr_reset();
}
void fc_mmc3_write(unsigned addr,unsigned value){mmc3_write(addr,value);}
int fc_mmc3_clock(void){bool was=host_irq;mmc3_clock();return !was && host_irq;}
int fc_mmc3_a12(unsigned addr,uint64_t cycle,unsigned m2_period){
 bool high=(addr&0x1000)!=0;uint64_t m2=(fc_epoch+cycle)/m2_period;
 if(!high&&fc_a12_high)fc_low_m2=m2;
 bool qualified=high&&!fc_a12_high&&m2-fc_low_m2>=3;
 fc_a12_high=high;return qualified;
}
void fc_mmc3_frame(uint64_t cycles){fc_epoch+=cycles;}

// Diagnostic model: in-place expansion of one 1KiB slot takes a configured time.
#include <stdlib.h>
#include <stdio.h>
#include "../../magicon/remote_position.h"
static uint8_t fc_chr_cache[8192];
static const uint8_t *fc_desired[8],*fc_cached[8],*fc_batch[8];
static bool fc_valid[8],fc_copying;
static unsigned fc_slot,fc_pos,fc_next;
static uint64_t fc_started,fc_duration;
static unsigned long long fc_changed_reads;
static void fc_chr_reset(void){
 memset(fc_valid,0,sizeof fc_valid);memset(fc_desired,0,sizeof fc_desired);
 memset(fc_cached,0,sizeof fc_cached);fc_copying=false;fc_next=8;fc_changed_reads=0;
 const char *v=getenv("FC_CHR_COPY_US");double us=v?atof(v):0;
 fc_duration=us>0?(uint64_t)(us*21.477272+0.5):0;
}
static bool fc_chr_start(uint64_t now){
 if(fc_next==8){memcpy(fc_batch,fc_desired,sizeof fc_batch);fc_next=0;}
 while(fc_next<8){unsigned i=fc_next++;
  if(fc_valid[i]&&fc_cached[i]!=fc_batch[i]){fc_slot=i;fc_pos=0;fc_started=now;fc_copying=true;return true;}
 }
 fc_copying=false;return false;
}
static void fc_chr_service(uint64_t now){
 if(!fc_duration)return;
 if(!fc_copying&&!fc_chr_start(now))return;
 for(unsigned guard=0;guard<32;guard++){
  uint64_t elapsed=now>=fc_started?now-fc_started:0;
  unsigned to=elapsed>=fc_duration?1024:(unsigned)(elapsed*1024/fc_duration);
  if(to>fc_pos){memcpy(fc_chr_cache+fc_slot*1024+fc_pos,fc_batch[fc_slot]+fc_pos,to-fc_pos);fc_pos=to;}
  if(to<1024)return;
  uint64_t done=fc_started+fc_duration;fc_cached[fc_slot]=fc_batch[fc_slot];fc_copying=false;
  if(!fc_chr_start(done)){
   // End of batch: pick up register changes received while copying.
   if(!fc_chr_start(done))return;
  }
 }
}
void fc_chr_bank(unsigned address,const uint8_t*source,uint64_t cycle){
 uint64_t now=fc_epoch+cycle;fc_chr_service(now);unsigned i=(address>>10)&7;
 fc_desired[i]=source;
 if(!fc_valid[i]){memcpy(fc_chr_cache+i*1024,source,1024);fc_cached[i]=source;fc_valid[i]=true;}
 fc_chr_service(now);
}
static int remote_scanline;
static remote_position remote_pos;
static int remote_use_nametable=-1;
void fc_remote_nametable(unsigned address){remote_position_name(&remote_pos,(uint16_t)address);}
static int remote_mode=-1;
static uint8_t remote_frame[15360];
__declspec(dllexport) void fc_remote_frame(const uint8_t *frame){
 memcpy(remote_frame,frame,sizeof remote_frame);remote_mode=1;
}
void fc_remote_scanline(int line){remote_scanline=line;}
unsigned fc_chr_read(unsigned address,unsigned native,uint64_t cycle){
 // Validation-only reproduction of the original full framebuffer CHR responder.
 // Enabled only by an explicit environment path; ordinary MMC3 tests bypass it.
 if(remote_mode==-1){
  const char *path=getenv("FC_REMOTE_FB");remote_mode=0;
  if(path){FILE *f=fopen(path,"rb");
   if(f){remote_mode=fread(remote_frame,1,sizeof remote_frame,f)==sizeof remote_frame;fclose(f);}
  }
 }
 if(remote_mode && !(address&0x1000)){
  if(remote_use_nametable==-1)remote_use_nametable=getenv("FC_REMOTE_NAMETABLE")!=NULL;
  if(remote_use_nametable){
   uint16_t offset;
   return remote_position_byte(&remote_pos,(uint16_t)address,&offset)?remote_frame[offset]:native;
  }
  unsigned tile=address>>4,trow=tile>>5;
  unsigned line=remote_scanline<0||remote_scanline>=240?0:(unsigned)remote_scanline;
  unsigned group=line/64;
  if(trow==0 && (line%64)>=56)group=(group+1)%4;
  unsigned row=group*8+trow;if(row>29)row=29;
  return remote_frame[((row*8+(address&7))*32+(tile&31))*2+((address>>3)&1)];
 }
 if(!fc_duration)return native;
 fc_chr_service(fc_epoch+cycle);unsigned i=(address>>10)&7;
 unsigned result=fc_valid[i]?fc_chr_cache[address&8191]:native;
 if(result!=native)fc_changed_reads++;
 return result;
}
__declspec(dllexport) unsigned long long fc_chr_read_errors(void){return fc_changed_reads;}
