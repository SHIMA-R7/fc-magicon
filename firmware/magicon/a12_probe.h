#pragma once
#include "a12_probe.pio.h"
static uint32_t a12_raw[1024];
static unsigned a12_dma,a12_offset;
static bool a12_running;
static uint32_t a12_deadline;
static void a12_probe_init(void) {
    a12_offset=pio_add_program(pio2,&a12_probe_program);
    pio_sm_config c=a12_probe_program_get_default_config(a12_offset);
    sm_config_set_in_pins(&c,38);sm_config_set_jmp_pin(&c,38);
    sm_config_set_in_shift(&c,false,false,32);sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_RX);
    pio_sm_init(pio2,2,a12_offset,&c);
    a12_dma=dma_claim_unused_channel(true);
    dma_channel_config dc=dma_channel_get_default_config(a12_dma);
    channel_config_set_transfer_data_size(&dc,DMA_SIZE_32);
    channel_config_set_read_increment(&dc,false);channel_config_set_write_increment(&dc,true);
    channel_config_set_dreq(&dc,pio_get_dreq(pio2,2,false));
    dma_channel_configure(a12_dma,&dc,a12_raw,&pio2->rxf[2],1024,false);
}
static void a12_probe_poll(void) {
    if(!a12_running && getchar_timeout_us(0)=='p') {
        pio_sm_clear_fifos(pio2,2);pio_sm_restart(pio2,2);
        pio_sm_exec(pio2,2,pio_encode_jmp(a12_offset));
        dma_channel_set_write_addr(a12_dma,a12_raw,false);
        dma_channel_set_trans_count(a12_dma,1024,true);
        a12_deadline=time_us_32()+10000;a12_running=true;
        pio_sm_set_enabled(pio2,2,true);
    }
    if(a12_running && (!dma_channel_is_busy(a12_dma) || (int32_t)(time_us_32()-a12_deadline)>=0)) {
        pio_sm_set_enabled(pio2,2,false);
        unsigned words=1024-dma_hw->ch[a12_dma].transfer_count;
        dma_channel_abort(a12_dma);a12_running=false;
        printf("A12_PROBE_BEGIN pairs=%u quantum_ns=8 uncalibrated=1\n",words/2);
        for(unsigned i=0;i<words/2;i++)printf("A12RAW %u %lu %lu\n",i,(unsigned long)a12_raw[2*i],(unsigned long)a12_raw[2*i+1]);
        puts("A12_PROBE_END");
    }
}
