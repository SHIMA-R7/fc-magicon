#pragma once
#include <stdint.h>
// FCPV2: independent blocks of 256 samples; int16 predictor, uint8 index,
// reserved zero, then 128 low-nibble-first IMA codes. No sample is implicit.
#define IMA_SAMPLES 256u
#define IMA_BYTES 132u
static const int ima_steps[89]={7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767};
static const int ima_adjust[8]={-1,-1,-1,-1,2,4,6,8};
static inline int ima_decode(unsigned code,int *predictor,int *index) {
    int step=ima_steps[*index],delta=step>>3;
    if(code&1)delta+=step>>2;
    if(code&2)delta+=step>>1;
    if(code&4)delta+=step;
    int p=*predictor+((code&8)?-delta:delta);
    if(p>32767)p=32767;if(p< -32768)p= -32768;
    int i=*index+ima_adjust[code&7];if(i<0)i=0;if(i>88)i=88;
    *predictor=p;*index=i;return p;
}
