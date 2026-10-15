#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/clocks.h"
#include "hardware/vreg.h"
#include "../power_guard.h"
#include "baseline/cart.h"
#include "video_cart.h"
#include "flash_audio.h"
#include "fcpv.h"
#ifndef FC_PLAYER_CPU_WINDOW
#define FC_PLAYER_CPU_WINDOW 0
#endif
#if FC_PLAYER_PIN_AUDIT
#include "pin_audit.h"
#endif
#if FC_PLAYER_PALETTE_LOG || FC_PLAYER_NT_STRESS
#include "pico/stdio_usb.h"
#endif
#if FC_PLAYER_COLD_BOOT
#include "early_boot.h"
#include "hardware/structs/powman.h"
#include "hardware/regs/powman.h"
#endif

static void stop_with_code(unsigned code) {
    flash_audio_stop();
    printf("PLAYER FAULT %u\n",code);
    for(;;) {
        for(unsigned i=0;i<code;i++) {
            gpio_put(39,1);sleep_ms(100);gpio_put(39,0);sleep_ms(150);
        }
        sleep_ms(1000);
    }
}
static bool wait_for_vblank(void) {
    uint8_t before=cart_video_vblank();
    uint64_t start=time_us_64();
    while(cart_video_vblank()==before) {
        if(time_us_64()-start>2000000)return false;
        tight_loop_contents();
    }
    return true;
}
#if FC_PLAYER_NT_STRESS
static void run_nt_stress(void) {
    static uint8_t reports[52][32];
    unsigned count=0,protocol_errors=0;
    uint64_t start=time_us_64();
    uint8_t status=0;
#if FC_PLAYER_CPU_WINDOW
    uint8_t last_request=0;
#endif
#if FC_PLAYER_PIN_AUDIT
    pin_audit pins={0};
#endif
    while(time_us_64()-start<60000000u) {
#if FC_PLAYER_CPU_WINDOW
        uint8_t request=cart_video_diag_byte(0x73);
        if(request>=1 && request<=104 && request!=last_request) {
            if(request!=last_request+1)protocol_errors++;
            if(!cart_nt_cpu_source(request,cart_video_diag_byte(0x70),cart_video_diag_byte(0x71)))protocol_errors++;
            last_request=request;
        }
#endif
#if FC_PLAYER_PIN_AUDIT
        pin_audit_sample(&pins,gpio_get_all64());
#endif
        uint8_t sequence=cart_video_diag_byte(0x7e);
        if(sequence==count+1 && count<52) {
            __dmb();
            uint8_t *r=reports[count];
            for(unsigned i=0;i<32;i++)r[i]=cart_video_diag_byte(0x80+i);
            if(r[0]!=sequence || r[30]!=(FC_PLAYER_CPU_WINDOW?0xc5:0xa5))protocol_errors++;
            count++;cart_nt_stress_ack(sequence);
        }
        status=cart_video_readback_status();
        if(count==52 && (status==2 || status==3))break;
        tight_loop_contents();
    }
    bool complete=count==52 && (status==2 || status==3);
    stdio_init_all();
    for(;;) {
        if(stdio_usb_connected()) {
#if FC_PLAYER_PIN_AUDIT
            printf("GLOG samples=%lu high=%012llX low=%012llX changed=%012llX\n",(unsigned long)pins.samples,(unsigned long long)pins.high,(unsigned long long)pins.low,(unsigned long long)pins.changed);
#endif
            printf("SLOG status=%u reports=%u complete=%u protocol_errors=%u\n",status,count,complete,protocol_errors);
            for(unsigned k=0;k<count;k++) {
                printf("S%02u ",k);
                for(unsigned i=0;i<32;i++)printf("%02X",reports[k][i]);
                printf("\n");
            }
        }
        unsigned pulses=!complete || protocol_errors?3:status==2?1:2;
        for(unsigned i=0;i<pulses;i++) {
            gpio_put(39,1);sleep_ms(150);gpio_put(39,0);sleep_ms(200);
        }
        sleep_ms(1000);
    }
}
#endif
int main(void) {
    for(uint p=0;p<=46;p++) {
        if(p==39)continue;
        gpio_init(p);gpio_set_dir(p,GPIO_IN);gpio_disable_pulls(p);
#if FC_PLAYER_COLD_BOOT
        gpio_set_oeover(p,GPIO_OVERRIDE_LOW);
#endif
    }
    gpio_init(39);gpio_set_dir(39,GPIO_OUT);
    vreg_set_voltage(VREG_VOLTAGE_1_20);
#if FC_PLAYER_COLD_BOOT
    // SDK2.3.1 already waits for VREG_UPDATE_IN_PROGRESS. Check regulation too,
    // replacing the old fixed10ms sleep. This is core VREG, not IOVDD monitoring.
    while(!(powman_hw->vreg_sts&POWMAN_VREG_STS_VOUT_OK_BITS))tight_loop_contents();
#else
    sleep_ms(10);
#endif
    set_sys_clock_khz(250000,true);
#if FC_PLAYER_COLD_BOOT
    // No USB initialisation, no image conversion or whole-media CRC on this path.
    cart_boot_prepare();
    fc_wait_power();fc_arm_power_guard();
    cart_boot_enable();
#endif
    cart_info_t cart;
    const char *error=cart_load((const uint8_t *)"FCRD",4,&cart);
    if(error)panic("remote driver load failed");
#if !FC_PLAYER_COLD_BOOT
    bool usb_prepared=!gpio_get(46);
    if(usb_prepared)stdio_init_all(); // optional recovery while FC is off; no host wait
    fc_wait_power();fc_arm_power_guard();
#endif
    cart_start();
#if FC_PLAYER_NT_STRESS
    run_nt_stress(); // Rendering/audio/media staging are never started in this mode.
#endif
#if !FC_PLAYER_COLD_BOOT
    if(!usb_prepared)stdio_init_all();
#endif
    // Start the built-in driver before expensive media validation; no USB waits.
    if(!wait_for_vblank())stop_with_code(1);
    const uint8_t *media=(const uint8_t *)(XIP_BASE+0x00800000u);
    fcpv_info info;
    if(!fcpv_parse(media,0x00800000u,&info) ||
       fcpv_crc32(media+64,info.total-64)!=info.crc) {
        // Remain on the built-in screen without touching audio or bad pointers.
        stop_with_code(2);
    }
    if(!cart_video_stage(media+info.video))panic("initial frame busy");
    uint64_t staged_at=time_us_64();
    while(cart_video_pending()) {
        if(time_us_64()-staged_at>2000000)stop_with_code(3);
        tight_loop_contents();
    }
#if FC_PLAYER_READBACK
    // Freeze the first record: expected data remains unchanged throughout readback.
    uint64_t check_started=time_us_64();
    uint8_t status;
#if FC_PLAYER_FRAME_READBACK
    uint32_t checked=0;
    gpio_put(39,1);
    for(;;) {
#endif
    while((status=cart_video_readback_status())!=2 && status!=3 && status!=4) {
        if(time_us_64()-check_started>10000000)stop_with_code(6);
        tight_loop_contents();
    }
#if FC_PLAYER_FRAME_READBACK
        if(status!=2 || ++checked==info.frames)break;
        if(!cart_video_stage(media+info.video+(size_t)checked*FCPV_FRAME))stop_with_code(5);
        uint64_t next_staged=time_us_64();
        while(cart_video_pending()) {
            if(time_us_64()-next_staged>2000000)stop_with_code(5);
            tight_loop_contents();
        }
        check_started=time_us_64();
    }
#endif
    // Green means a match; mismatch colour is red for NT, blue for CHR.
#if FC_PLAYER_PALETTE_LOG
    // Start USB only after the final test result; never during its bus accesses.
    uint8_t actual[16],expected[16];
    __dmb();
    for(unsigned i=0;i<16;i++) {
        actual[i]=cart_video_diag_byte(0x30+i);
        expected[i]=cart_video_diag_byte(0x40+i);
    }
    uint32_t result_frame=checked==info.frames?checked-1:checked;
    const uint8_t *target=media+info.video+(size_t)result_frame*FCPV_FRAME+5120;
    uint16_t nt_offset=cart_video_diag_byte(0x50)|((uint16_t)cart_video_diag_byte(0x51)<<8);
    uint16_t nt_errors=cart_video_diag_byte(0x21)|((uint16_t)cart_video_diag_byte(0x22)<<8);
    uint8_t nt_valid=cart_video_diag_byte(0x54)==1;
    uint8_t nt_actual=cart_video_diag_byte(0x52),nt_expected=cart_video_diag_byte(0x53);
    uint8_t nt_target=nt_valid && nt_offset<1024 ? target[-1024+(int)nt_offset] : 0;
    stdio_init_all();
#endif
    for(;;) {
#if FC_PLAYER_PALETTE_LOG
        if(stdio_usb_connected()) {
            printf("NLOG valid=%u offset=%04X target=%02X expected=%02X actual=%02X errors=%u\n",nt_valid,nt_offset,nt_target,nt_expected,nt_actual,nt_errors);
            printf("PLOG status=%u frame=%lu palette_errors=%u\n",status,(unsigned long)result_frame,cart_video_diag_byte(0x23));
            for(unsigned i=0;i<16;i++)printf("P%02u target=%02X expected=%02X actual=%02X\n",i,target[i],expected[i],actual[i]);
        }
#endif
        unsigned pulses=status==2?1:status==4?3:2;
        for(unsigned i=0;i<pulses;i++) {
            gpio_put(39,1);sleep_ms(150);gpio_put(39,0);sleep_ms(200);
        }
        sleep_ms(1000);
    }
#endif
    flash_audio_start(media+info.audio,info.samples,info.rate);
    uint32_t frame=1;
    for(;;) {
        uint32_t played=flash_audio_poll();
        if(flash_audio_faulted())stop_with_code(4);
        if(cart_video_pending() && time_us_64()-staged_at>500000)stop_with_code(5);
        if(frame<info.frames && !cart_video_pending() && fcpv_frame_due(&info,frame,played)) {
            if(cart_video_stage(media+info.video+(size_t)frame*FCPV_FRAME)) {
                frame++;staged_at=time_us_64();gpio_put(39,!gpio_get(39));
            }
        }
        // Last picture stays displayed; the audio ring is filled with silence at EOF.
        tight_loop_contents();
    }
}
