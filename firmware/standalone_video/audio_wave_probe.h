// Passive input sampling of GPIO44. Do not change its PWM mux or output enable.
#pragma once
#include "audio_sample.pio.h"
#include "hardware/pio.h"
static uint32_t wave_samples[32768];
static void audio_wave_probe(void) {
    const uint sm=3;
    if(pio_sm_is_claimed(pio2,sm) || !pio_can_add_program(pio2,&audio_sample_program)) {
        puts("WAVE unavailable");return;
    }
    pio_sm_claim(pio2,sm);
    uint offset=pio_add_program(pio2,&audio_sample_program);
    pio_sm_config c=audio_sample_program_get_default_config(offset);
    sm_config_set_in_pins(&c,44);
    sm_config_set_in_shift(&c,true,true,32);
    sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_RX);
    sm_config_set_clkdiv(&c,(float)clock_get_hz(clk_sys)/4000000.0f);
    pio_sm_init(pio2,sm,offset,&c);
    uint ch=dma_claim_unused_channel(true);
    dma_channel_config dc=dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&dc,DMA_SIZE_32);
    channel_config_set_read_increment(&dc,false);
    channel_config_set_write_increment(&dc,true);
    channel_config_set_dreq(&dc,pio_get_dreq(pio2,sm,false));
    dma_channel_configure(ch,&dc,wave_samples,&pio2->rxf[sm],32768,true);
    pio2->fdebug=1u<<sm;
    uint32_t started=time_us_32();
    pio_sm_set_enabled(pio2,sm,true);
    absolute_time_t deadline=make_timeout_time_ms(500);
    while(dma_channel_is_busy(ch) && !time_reached(deadline))tight_loop_contents();
    bool complete=!dma_channel_is_busy(ch);
    uint32_t elapsed=time_us_32()-started;
    uint32_t stalled=pio2->fdebug&(1u<<sm);
    pio_sm_set_enabled(pio2,sm,false);dma_channel_abort(ch);
    dma_channel_unclaim(ch);pio_remove_program(pio2,&audio_sample_program,offset);pio_sm_unclaim(pio2,sm);
    if(!complete){puts("WAVE timeout");return;}
    uint rises=0,previous=0,last=0,min_period=0xffffffff,max_period=0;
    for(uint i=0;i<32768*32;i++) {
        uint bit=(wave_samples[i/32]>>(i%32))&1;
        if(bit && !previous) {
            if(rises){uint d=i-last;if(d<min_period)min_period=d;if(d>max_period)max_period=d;}
            last=i;rises++;
        }
        previous=bit;
    }
    printf("WAVE rate=4000000 samples=1048576 rises=%u period_min=%u period_max=%u\n",rises,min_period,max_period);
    printf("WAVE elapsed_us=%lu rx_stall=%lu\n",(unsigned long)elapsed,(unsigned long)stalled);
    uint rise=0,state=2,last_change=0,changes=0,min_run=0xffffffff,max_run=0;
    uint runs[64];previous=0;
    for(uint i=0;i<32768*32;i++) {
        uint bit=(wave_samples[i/32]>>(i%32))&1;
        if(bit && !previous)rise=i;
        if(!bit && previous) {
            uint width=i-rise;
#ifdef FC_AUDIO_FIFO_TONE
            uint next=width>=6?1:width<=4?0:2;
#else
            uint next=width>=11?1:width<=5?0:2;
#endif
            if(next!=2 && next!=state) {
                if(state!=2) {
                    uint run=i-last_change;
                    if(run<min_run)min_run=run;if(run>max_run)max_run=run;
                    if(changes<64)runs[changes]=run;changes++;
                }
                state=next;last_change=i;
            }
        }
        previous=bit;
    }
    printf("WAVE envelope_changes=%u interval_min=%u interval_max=%u first_intervals:",changes,min_run,max_run);
    for(uint i=0;i<changes && i<64;i++)printf(" %u",runs[i]);puts("");
    // Each 125 words is exactly 1ms. High counts expose the PCM envelope.
    printf("WAVE duty_per_ms:");
    for(uint i=0;i+125<=32768;i+=125) {
        uint high=0;for(uint j=0;j<125;j++)high+=__builtin_popcount(wave_samples[i+j]);
        printf(" %u",high);
    }
    puts("");
}
