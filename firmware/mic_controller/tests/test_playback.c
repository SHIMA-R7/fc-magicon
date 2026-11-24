
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <stdlib.h>
#undef assert
#define assert(x) do {if(!(x)){fprintf(stderr,"CHECK FAILED line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
#include <stdio.h>
#include <string.h>
#define __not_in_flash_func(x) x
#define __dmb() ((void)0)
#define sleep_us(x) ((void)0)
#include "../playback.h"
static void send(char type,const uint8_t *data,unsigned n){
 uint8_t p[527]={'M','2','U','P',type,n,n>>8};if(n)memcpy(p+7,data,n);
 uint32_t h=upload_hash(p,n+7,2166136261u);for(unsigned i=0;i<4;i++)p[n+7+i]=h>>(i*8);
 playback_upload(p,n+11);
}
static void start(uint32_t n){uint8_t p[4]={n,n>>8,n>>16,n>>24};send('S',p,4);}
static void fill(unsigned n){uint32_t w=produced;uint8_t p[516]={w,w>>8,w>>16,w>>24};for(unsigned i=0;i<n;i++)p[4+i]=((w+i)*13)&127;send('D',p,n+4);}
int main(){
 start(100000);assert(play_state==1);
 while(consumed<total){
  if(produced<total){unsigned n=total-produced;if(n>512)n=512;if(PLAY_RING-(produced-consumed)>=n)fill(n);}
  if(play_state==2){unsigned n=produced-consumed;if(n>300)n=300;while(n--){uint32_t r=consumed;assert(playback_sample()==((r*13)&127));}}
  assert(play_state!=4);
 }
 assert(play_state==3&&produced==100000);send('E',0,0);assert(play_state==3);
 assert(playback_sample()==64&&consumed==100000);
 start(9000);for(int i=0;i<4;i++)fill(512);assert(play_state==2);
 for(int i=0;i<2048;i++)playback_sample();assert(play_state==2);assert(playback_sample()==64&&play_state==4);
 send('X',0,0);assert(play_state==0);
 start(100);uint8_t bad[5]={1,0,0,0,64};send('D',bad,5);assert(play_state==4);
 start(100);uint8_t corrupt[11]={'M','2','U','P','E',0,0};playback_upload(corrupt,11);assert(play_state==4);
 puts("PASS: actual C ring, 100000 ordered samples across wraparound, exact finish, underrun, offset and checksum rejection");
}
