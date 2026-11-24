// No PPU/CHR outputs, no audio outputs. Only CPU D0-D7 are ever driven.
#include <string.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/clocks.h"
#include "hardware/vreg.h"
#include "hardware/sync.h"
#include "tusb.h"
#include "cpu_m2.pio.h"
#define FC_PLAYER_A9_REMAP 1
#include "power_guard.h"
#include "rom.h"
#include "playback.h"

static uint8_t prg[32768];
static volatile uint8_t pad, frame, recording;
static volatile bool ready;
static uint8_t cdc = 255;
void tuh_cdc_mount_cb(uint8_t i) { cdc = i; }
void tuh_cdc_umount_cb(uint8_t i) { if (cdc == i) cdc = 255; recording = 0; play_state=0; }
uint32_t tusb_time_millis_api(void) { return to_ms_since_boot(get_absolute_time()); }

static void __not_in_flash_func(responder)(void) {
    save_and_disable_interrupts();
    bool payload = false;
    uint16_t address = 0;
    ready = true;
    for (;;) {
        uint32_t h = pio_sm_get_blocking(pio0, 0);
        if (payload) {
            if (address == 0x5f00) pad = (pad&2) | (h&1);
            else if (address == 0x5f03) pad = (pad&1) | ((h&1)<<1);
            else if (address == 0x5f01) { __dmb(); frame = h & 255; }
            else if (address==0x4011 && dac_pending) {
                uint8_t value=h&127;dac_actual=value;dac_writes++;
                if(value<dac_min)dac_min=value;if(value>dac_max)dac_max=value;
                if(value!=dac_expected)dac_errors++;
                dac_pending=false;
            }
            payload = false;
            continue;
        }
        if ((h&0x01800000u)==0x01800000u && ((h>>8)&0x7fff)==0x5f20) {
            uint32_t r=consumed;
            bool available=play_state==2 && r<produced;
            uint32_t value=available ? play_data[r&(PLAY_RING-1)] : 0x8000ff40u;
            // Release the PIO reply BEFORE counters, barriers or end-of-stream handling.
            pio_sm_put_blocking(pio0,0,value);
            dac_expected=value&127;dac_pending=true;
            if(available){consumed=r+1;if(consumed>=total)play_state=3;}
            else if(play_state==2)play_state=4;
            continue;
        }
        uint32_t reply = 0x80000000u;
        if (!(h & (1u << 24))) {
            address = ((h >> 8) & 0x7fff) | ((h & (1u << 23)) ? 0 : 0x8000);
            payload = true;
        } else if (!(h & (1u << 23))) reply |= 0xff00u | prg[(h >> 8) & 0x7fff];
        else if (((h >> 8) & 0x7fff) == 0x5f02) reply |= 0xff00u | recording;
        else if (((h >> 8) & 0x7fff) == 0x5f21) reply |= 0xff00u | (play_state==2);
        else if (((h >> 8) & 0x7fff) == 0x5f20) reply |= 0xff00u | playback_sample();
        pio_sm_put_blocking(pio0, 0, reply);
    }
}

int main(void) {
    for (uint p = 0; p <= 46; ++p) {
        gpio_init(p); gpio_set_dir(p, GPIO_IN); gpio_disable_pulls(p);
        gpio_set_oeover(p, GPIO_OVERRIDE_LOW);
    }
    vreg_set_voltage(VREG_VOLTAGE_1_20); sleep_ms(10);
    set_sys_clock_khz(250000, true);
    memcpy(prg, mic_rom, sizeof prg);
    pio_set_gpio_base(pio0, 0);
    cpu_m2_program_init(pio0, 0, pio_add_program(pio0, &cpu_m2_program));
    multicore_launch_core1(responder);
    while (!ready) tight_loop_contents();
    fc_wait_power(); fc_arm_power_guard();
    for (uint p = 0; p < 8; ++p) gpio_set_oeover(p, GPIO_OVERRIDE_NORMAL);
    pio_sm_set_enabled(pio0, 0, true);
    const tusb_rhport_init_t rh = {.role=TUSB_ROLE_HOST, .speed=TUSB_SPEED_AUTO};
    tusb_rhport_init(0, &rh);
    uint8_t previous = 0, rx[527] = {0}; unsigned used = 0, expected = 0;
    uint64_t next_pad=0, next_credit=0, last_upload=0;
    bool audit_sent=false;
    for (;;) {
        tuh_task();
        if (cdc == 255) { sleep_us(100); continue; }
        while (tuh_cdc_read_available(cdc)) {
            uint8_t ch;
            if (!tuh_cdc_read(cdc, &ch, 1)) break;
            rx[used++]=ch;
            if (used==4) {
                if (!memcmp(rx,"M2ST",4)) expected=5;
                else if (memcmp(rx,"M2UP",4)) { memmove(rx,rx+1,3); used=3; }
            }
            if (used==7 && !memcmp(rx,"M2UP",4)) {
                unsigned n=rx[5]|((unsigned)rx[6]<<8);
                if (n>516) { used=expected=0; play_state=4; continue; }
                expected=n+11;
            }
            if (expected && used==expected) {
                if (!memcmp(rx,"M2ST",4)) recording=rx[4]<=2 ? rx[4] : 0;
                else { playback_upload(rx,used); last_upload=time_us_64();if(rx[4]=='S')audit_sent=false; }
                used=expected=0;
            }
        }
        uint8_t f = frame;
        uint64_t now=time_us_64();
        if (now>=next_pad && f != previous && tuh_cdc_write_available(cdc) >= 8) {
            __dmb(); uint8_t a = pad;
            uint8_t packet[8] = {'M','2','B','T', a, f, (uint8_t)~a, 0xa5};
            tuh_cdc_write(cdc, packet, sizeof packet); tuh_cdc_write_flush(cdc);
            previous = f;
            next_pad=now+16000;
        }
        if (now>=next_credit && tuh_cdc_write_available(cdc)>=12) {
            if(play_state==3 && !audit_sent) {
                if(tuh_cdc_write_available(cdc)<36)continue;
                sleep_us(200); // Include the final CPU DAC write after the last sample read.
                uint32_t stats[2]={dac_writes,dac_errors};
                uint16_t detail[2]={(uint16_t)dac_min|((uint16_t)dac_max<<8),(uint16_t)dac_actual|((uint16_t)dac_expected<<8)};
                for(unsigned k=0;k<2;k++) {
                    uint32_t v=stats[k];uint16_t d=detail[k];
                    uint8_t a[12]={'M','2','F','C',v,v>>8,v>>16,v>>24,d,d>>8,10+k,0xa5};
                    tuh_cdc_write(cdc,a,12);
                }
                tuh_cdc_write_flush(cdc);audit_sent=true;
            }
            uint32_t r=consumed; unsigned free=PLAY_RING-(produced-r);
            uint8_t credit[12]={'M','2','F','C',r,r>>8,r>>16,r>>24,free,free>>8,play_state,0xa5};
            tuh_cdc_write(cdc,credit,12); tuh_cdc_write_flush(cdc); next_credit=now+20000;
        }
        if ((play_state==1 || play_state==2) && now-last_upload>2000000) play_state=4;
    }
}
