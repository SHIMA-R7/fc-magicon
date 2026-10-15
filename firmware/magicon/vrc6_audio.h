#pragma once
#include <stdint.h>
#include <string.h>
// Independent implementation of the documented VRC6 audio register interface.
// One tick = one NTSC CPU/M2 cycle. No mapper 24/26 implementation is implied.
typedef struct {
    uint8_t reg[3][3], control, phase[3], accum;
    uint16_t timer[3];
} vrc6_audio_t;
static inline void vrc6_reset(vrc6_audio_t *s) { memset(s,0,sizeof *s);s->phase[0]=s->phase[1]=15; }
static inline int vrc6_register(uint16_t a) {
    if(a==0x9003)return 9;
    unsigned page=a>>12, r=a&0xfff;
    return page>=9 && page<=11 && r<=2 ? (int)((page-9)*3+r) : -1;
}
static inline void vrc6_write(vrc6_audio_t *s,unsigned r,uint8_t d) {
    if(r==9){s->control=d&7;return;}
    if(r>=9)return;
    unsigned c=r/3,sub=r%3;s->reg[c][sub]=d;
    if(sub==2 && !(d&128)) {
        s->phase[c]=c==2 ? 0 : 15;
        if(c==2)s->accum=0;
    }
}
static inline unsigned vrc6_level(const vrc6_audio_t *s) {
    unsigned out=0;
    for(unsigned c=0;c<2;c++)if(s->reg[c][2]&128)
        if((s->reg[c][0]&128) || s->phase[c]<=((s->reg[c][0]>>4)&7))out+=s->reg[c][0]&15;
    if(s->reg[2][2]&128)out+=s->accum>>3;
    return out;
}
static inline unsigned vrc6_tick(vrc6_audio_t *s) {
    if(!(s->control&1))for(unsigned c=0;c<3;c++) {
        if(s->timer[c])--s->timer[c];
        else {
            unsigned p=s->reg[c][1]|((s->reg[c][2]&15)<<8);
            s->timer[c]=p>>((s->control&4)?8:(s->control&2)?4:0);
            if(s->reg[c][2]&128) {
                if(c<2)s->phase[c]=(s->phase[c]-1)&15;
                else {
                    if(++s->phase[2]==14){s->phase[2]=0;s->accum=0;}
                    else if(!(s->phase[2]&1))s->accum=(uint8_t)(s->accum+(s->reg[2][0]&63));
                }
            }
        }
    }
    return vrc6_level(s);
}
