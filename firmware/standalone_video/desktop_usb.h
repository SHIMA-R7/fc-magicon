#pragma once
#include <string.h>
#if !FC_REMOTE_WIFI
#include "pico/stdio_usb.h"
#endif
#include "tusb.h"
#include "audio.h"

#if FC_REMOTE_WIFI
#include "wifi_transport.h"
#else
static bool desktop_connected(void) { return stdio_usb_connected(); }
static uint32_t desktop_write_available(void) { return tud_cdc_write_available(); }
static void desktop_write(const void *packet, uint32_t size) {
    tud_cdc_write(packet, size);
    tud_cdc_write_flush();
}
#endif

#if FC_REMOTE_WIFI
#include "usb_update.h"
#endif

static uint8_t desktop_last_input;
bool cart_desktop_idle(void);
static bool desktop_active,desktop_idle_pending,desktop_receiving;
static uint64_t desktop_last_rx;
static uint32_t desktop_next_stats;
static void desktop_stop(void) {audio_reset_stream();desktop_active=false;desktop_idle_pending=true;}
static void desktop_poll(void) {
    audio_poll();
#if FC_REMOTE_WIFI
    tuh_task();
#endif
    if(!desktop_receiving && desktop_active && (!desktop_connected() || time_us_64()-desktop_last_rx>3000000))desktop_stop();
    if(!desktop_receiving && desktop_idle_pending && cart_desktop_idle())desktop_idle_pending=false;
    if(!desktop_connected())return;
    uint32_t now=time_us_32();
    if((int32_t)(now-desktop_next_stats)>=0 && desktop_write_available()>=20) {
        uint32_t packet[5]={0x47444346u};audio_stats(packet+1);
        desktop_write(packet,sizeof packet);desktop_next_stats=now+1000000;
    }
    uint8_t io[16],packet[20]={'F','C','I','N'};
    cart_remote_io(io);
    if(io[15]==desktop_last_input || desktop_write_available()<20)return;
    desktop_last_input=io[15];memcpy(packet+4,io,16);
    desktop_write(packet,20);
}
static bool desktop_read(uint8_t *p,unsigned n,unsigned timeout) {
    absolute_time_t until=make_timeout_time_ms(timeout);
    while(n) {
        desktop_poll();
        if(time_reached(until))return false;
#if FC_REMOTE_WIFI
        if (!desktop_connected()) return false;
        int got = (int)tuh_cdc_read(desktop_cdc, p, n);
#else
        int got=stdio_get_until((char *)p,n,make_timeout_time_ms(1));
#endif
        if(got>0){p+=got;n-=got;}
    }
    return true;
}
static void __attribute__((noreturn)) desktop_usb_run(void) {
#if FC_REMOTE_WIFI
    desktop_host_init();
#else
    stdio_init_all();
#endif
    audio_init(44);
    static uint8_t meta[99],pcm[2048];
    uint32_t match=0;
    for(;;) {
        uint8_t c;
        if(!desktop_read(&c,1,1))continue;
        match=(match<<8)|c;
#if FC_REMOTE_WIFI
        if(match==0x4643504du) {match=0;update_media();while(update_quiesced)update_poll();continue;}
        if(match==0x46435550u) {match=0;update_receive();continue;}
#endif
        if(match==0x46435354u) {match=0;desktop_stop();} // FCST: normal stop
        else if(match==0x46434155u) { // FCAU: PCM16, signed PCM8 or ADPCM
            uint8_t h[3];match=0;
            if(!desktop_read(h,3,100))continue;
            uint16_t n=h[1]|((uint16_t)h[2]<<8);int len=audio_payload_len(h[0],n);
            if(len<0 || len>(int)sizeof pcm || !desktop_read(pcm,len,100))continue;
            desktop_last_rx=time_us_64();desktop_active=true;desktop_idle_pending=false;
            audio_push(h[0],n,pcm);
        } else if(match==0x46434652u) { // FCFR
            match=0;uint8_t *back;
            absolute_time_t ready_until = make_timeout_time_ms(500);
            while (!(back = cart_remote_back())) {
                desktop_poll();
                if (time_reached(ready_until)) break;
                tight_loop_contents();
            }
            if (!back) continue;
            desktop_receiving=true;
            bool complete=desktop_read(back,15360,500)&&desktop_read(meta,99,500);
            desktop_receiving=false;
            if(!complete)continue;
            desktop_last_rx=time_us_64();desktop_active=true;desktop_idle_pending=false;
            // The two pattern tables hold video banks; cursor is drawn by PC.
            for(unsigned i=0;i<32;i+=4)meta[i]=meta[0];
            cart_remote_commit(meta,meta+32,0,0,false);
        }
    }
}
