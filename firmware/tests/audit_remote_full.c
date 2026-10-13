#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
typedef unsigned uint;
static uint32_t diag_chr_lookup[8192];
#include "../magicon/remote_full.h"
int main(void){
 static uint8_t fb[15360],oldids[200];
 for(uint frame=0;frame<2;frame++){
  for(uint t=0;t<960;t++)for(uint y=0;y<8;y++)for(uint p=0;p<2;p++){
   uint id=frame?(199-t%200):t%200;
   fb[((t/32*8+y)*32+t%32)*2+p]=(uint8_t)(id*13+y*19+p*37);
  }
  remote_full_convert(fb);
  for(uint t=0;t<960;t++){
   uint id=frame?(199-t%200):t%200;
   if(!frame)oldids[id]=rd_nt[t];else assert(oldids[id]==rd_nt[t]);
   for(uint y=0;y<8;y++)for(uint p=0;p<2;p++)
    assert((diag_chr_lookup[rd_nt[t]*16+y+p*8]&255)==fb[((t/32*8+y)*32+t%32)*2+p]);
  }
 }
 puts("PASS stable slots despite changed frequency/order; exact 200-pattern reconstruction across frames");
}
