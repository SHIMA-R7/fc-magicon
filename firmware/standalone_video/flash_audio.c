// Same successful PIO PWM program, fed locally from flash through an SRAM ring.
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "audio_fifo.pio.h"
#include "flash_audio.h"
#include "pcm_ring.h"

#define RING 8192u
static uint32_t ring[RING] __attribute__((aligned(RING*4)));
static pcm_ring_state state;
static pcm_refill_deadline deadline;
static uint32_t div256;
static int channel=-1;
static uint32_t last_played;

void flash_audio_start(const uint8_t *pcm,uint32_t samples,uint32_t rate) {
    pcm_ring_init(&state,ring,pcm,samples);
    last_played=0;
    const uint sm=2,pin=44;
    pio_sm_claim(pio2,sm);
    uint off=pio_add_program(pio2,&audio_fifo_program);
    pio_sm_config c=audio_fifo_program_get_default_config(off);
    sm_config_set_set_pins(&c,pin,1);
    sm_config_set_out_shift(&c,true,false,32);
    sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_TX);
    div256=(uint32_t)(((uint64_t)clock_get_hz(clk_sys)*256+((uint64_t)rate*6206)/2)/((uint64_t)rate*6206));
    sm_config_set_clkdiv_int_frac8(&c,div256>>8,div256&255);
    pio_gpio_init(pio2,pin);
    pio_sm_set_consecutive_pindirs(pio2,sm,pin,1,true);
    pio_sm_init(pio2,sm,off,&c);
    pio_sm_put(pio2,sm,255);
    channel=dma_claim_unused_channel(true);
    dma_channel_config d=dma_channel_get_default_config(channel);
    channel_config_set_transfer_data_size(&d,DMA_SIZE_32);
    channel_config_set_read_increment(&d,true);
    channel_config_set_write_increment(&d,false);
    channel_config_set_ring(&d,false,15);
    channel_config_set_dreq(&d,pio_get_dreq(pio2,sm,true));
    dma_channel_configure(channel,&d,&pio2->txf[sm],ring,dma_encode_endless_transfer_count(),true);
    deadline=(pcm_refill_deadline){.last_us=time_us_64()};
    pio_sm_set_enabled(pio2,sm,true);
}
uint32_t flash_audio_poll(void) {
    if(channel<0 || deadline.faulted)return last_played;
    if(!pcm_refill_on_time(&deadline,time_us_64())) {
        flash_audio_stop();return last_played;
    }
    uint32_t index=((uintptr_t)dma_hw->ch[channel].read_addr-(uintptr_t)ring)/4&(RING-1);
    // DMA may have prefetched eight samples into TX FIFO and one into OSR.
    last_played=pcm_ring_refill(&state,ring,index);
    return last_played;
}
uint32_t flash_audio_div256(void) { return div256; }
bool flash_audio_faulted(void) { return deadline.faulted; }
void flash_audio_stop(void) {
    if(channel<0)return;
    // Stop fetching stale samples. Keep mid-level PWM, rather than DC low.
    dma_channel_abort((uint)channel);
    // Software stop can discard the ring, but must not drive another bus pin.
    pio_sm_set_enabled(pio2,2,false);
    pio_sm_clear_fifos(pio2,2);
    // The power guard's OE override, if asserted, remains authoritative.
    gpio_set_function(44,GPIO_FUNC_PWM);
    uint slice=pwm_gpio_to_slice_num(44);
    pwm_set_enabled(slice,false);
    pwm_set_wrap(slice,255);
    pwm_set_clkdiv(slice,1.0f);
    pwm_set_gpio_level(44,128);
    pwm_set_counter(slice,0);
    pwm_set_enabled(slice,true);
    channel=-1;
}
