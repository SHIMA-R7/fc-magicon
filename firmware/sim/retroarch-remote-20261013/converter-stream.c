#include <stdint.h>
#include <stdbool.h>
typedef unsigned uint;
static uint32_t diag_chr_lookup[8192];
#include "../../magicon/remote_full.h"
__declspec(dllexport) void convert(const uint8_t *fb,uint8_t *chr,uint8_t *nt){
 remote_full_convert(fb);
 for(uint i=0;i<4096;i++)chr[i]=(uint8_t)diag_chr_lookup[i];
 memcpy(nt,rd_nt,1024);
}
