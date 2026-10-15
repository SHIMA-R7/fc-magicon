#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef unsigned uint;
static uint32_t diag_chr_lookup[8192];
#include <stdbool.h>
#include "../../magicon/remote_full.h"
int main(int argc,char**argv){
 uint8_t fb[15360],chr[8192];
 if(argc!=4)return 2;
 FILE*f=fopen(argv[1],"rb");if(!f)return 3;
 if(fread(fb,1,sizeof fb,f)!=sizeof fb)return 4;fclose(f);
 remote_full_convert(fb);
 for(uint i=0;i<8192;i++)chr[i]=(uint8_t)diag_chr_lookup[i];
 f=fopen(argv[2],"wb");fwrite(chr,1,8192,f);fclose(f);
 f=fopen(argv[3],"wb");fwrite(rd_nt,1,1024,f);fclose(f);
 return 0;
}
