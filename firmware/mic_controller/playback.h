#pragma once
#define PLAY_RING 8192u
static uint32_t play_data[PLAY_RING]; // preformatted PIO replies, not decoded on the bus deadline
static volatile uint32_t produced, consumed, total;
static volatile uint32_t dac_writes, dac_errors;
static volatile uint8_t dac_min, dac_max, dac_actual, dac_expected;
static volatile bool dac_pending;
// 0 idle, 1 buffering, 2 playing, 3 finished, 4 invalid packet/underrun.
static volatile uint8_t play_state;
static uint32_t upload_hash(const uint8_t *p, unsigned n, uint32_t h) {
    while (n--) h = (h ^ *p++) * 16777619u;
    return h;
}
static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static void playback_upload(const uint8_t *p, unsigned bytes) {
    unsigned n = p[5] | ((unsigned)p[6]<<8);
    if (bytes != n+11 || le32(p+7+n) != upload_hash(p, n+7, 2166136261u)) {
        play_state=4; return;
    }
    if (p[4]=='X' && !n) { play_state=0; return; }
    if (p[4]=='S' && n==4) {
        play_state=0; __dmb(); sleep_us(2); produced=consumed=0; total=le32(p+7);
        dac_writes=dac_errors=0; dac_min=127;dac_max=dac_actual=dac_expected=0;dac_pending=false;
        __dmb(); play_state=total ? 1 : 4; return;
    }
    if (p[4]=='D' && n>4 && (play_state==1 || play_state==2)) {
        unsigned count=n-4; uint32_t w=produced, r=consumed;
        if (le32(p+7)!=w || count>PLAY_RING-(w-r) || count>total-w) { play_state=4; return; }
        for (unsigned i=0;i<count;i++) {
            if (p[11+i]>127) { play_state=4; return; }
            play_data[(w+i)&(PLAY_RING-1)]=0x8000ff00u|p[11+i];
        }
        __dmb(); produced=w+count;
        if (play_state==1 && (produced>=2048 || produced==total)) play_state=2;
        return;
    }
    if (p[4]=='E' && !n && produced==total) return;
    play_state=4;
}
static inline uint8_t __not_in_flash_func(playback_sample)(void) {
    if (play_state!=2) return 64;
    uint32_t r=consumed;
    if (r==produced) { play_state=4; return 64; }
    __dmb(); uint8_t value=play_data[r&(PLAY_RING-1)]&127;
    consumed=r+1;
    if (consumed>=total) play_state=3;
    return value;
}
