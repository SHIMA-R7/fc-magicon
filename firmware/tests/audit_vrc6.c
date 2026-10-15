#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <time.h>
#include "../magicon/nsf_expansion.h"
int main(int argc,char **argv) {
 vrc6_audio_t s;
 for(unsigned d=0;d<8;d++) {
  vrc6_reset(&s);vrc6_write(&s,0,(d<<4)|15);vrc6_write(&s,2,128);
  unsigned high=0;for(unsigned k=0;k<16;k++)high+=vrc6_tick(&s)==15;
  assert(high==d+1);
 }
 vrc6_reset(&s);vrc6_write(&s,0,0x8f);vrc6_write(&s,2,128);
 for(unsigned k=0;k<100;k++)assert(vrc6_tick(&s)==15);
 vrc6_write(&s,9,1);unsigned phase=s.phase[0];
 for(unsigned k=0;k<100;k++)assert(vrc6_tick(&s)==15 && s.phase[0]==phase);
 vrc6_write(&s,2,0);assert(vrc6_level(&s)==0 && s.phase[0]==15);
 vrc6_reset(&s);vrc6_write(&s,6,8);vrc6_write(&s,8,128);
 for(unsigned k=1;k<=14;k++){unsigned v=vrc6_tick(&s);assert(v==(k==14?0:k/2));}
 vrc6_write(&s,8,0);assert(s.accum==0 && s.phase[2]==0);
 vrc6_reset(&s);vrc6_write(&s,1,255);vrc6_write(&s,2,143);vrc6_write(&s,9,6);
 vrc6_tick(&s);assert(s.timer[0]==15); // 256x takes priority over 16x
 assert(vrc6_register(0x9003)==9 && vrc6_register(0xb002)==8 && vrc6_register(0xb003)==-1);
 nsf_expansion_t e;nsf_expansion_init(&e);
 for(unsigned k=0;k<NSF_EVENT_COUNT;k++)nsf_expansion_write(&e,k,0,0);
 nsf_expansion_write(&e,300,0,1);assert(atomic_load(&e.fault));
 int16_t pcm[320];assert(nsf_expansion_render(&e,1000,pcm,10)==10);
 for(unsigned k=0;k<10;k++)assert(!pcm[k]);
 nsf_expansion_init(&e);nsf_expansion_write(&e,100,0,0x8f);nsf_expansion_write(&e,100,2,128);
 assert(nsf_expansion_render(&e,200,pcm,4)==3);
 assert(pcm[0]==0 && pcm[1]>0 && pcm[2]==6000);
 e.head=e.tail=UINT32_MAX-2;nsf_expansion_write(&e,200,2,0);
 assert(nsf_expansion_render(&e,400,pcm,4)==4 && pcm[3]==0);
 // Output an independently configured 440Hz pulse + saw diagnostic, PCM16 32kHz.
 nsf_expansion_init(&e);
 nsf_expansion_write(&e,0,0,0x3f);nsf_expansion_write(&e,0,1,253);nsf_expansion_write(&e,0,2,128);
 nsf_expansion_write(&e,0,6,24);nsf_expansion_write(&e,0,7,34);nsf_expansion_write(&e,0,8,129);
 FILE *f=argc>1?fopen(argv[1],"wb"):NULL;clock_t start=clock();unsigned n=0;
 while(n<64000){unsigned got=nsf_expansion_render(&e,3579546,pcm,320);assert(got);if(f)fwrite(pcm,2,got,f);n+=got;}
 if(f)fclose(f);
 printf("PASS: VRC6 duty, mode, halt, saw, scaling, timestamp ordering, queue overflow/wrap; 2s synthesis %.3fs (host only)\n",(double)(clock()-start)/CLOCKS_PER_SEC);
}
