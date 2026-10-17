#pragma once
#include "address_probe.pio.h"

typedef struct {
    uint32_t read_pages[4],write_pages[4];
    uint32_t read_other,write_other;
} nt_address_probe;

static void nt_address_probe_init(void) {
    // NoPpu mode leaves PIO1 unused. GPIO functions/directions are untouched.
    uint write_offset=pio_add_program(pio1,&nt_write_probe_program);
    uint read_offset=pio_add_program(pio1,&nt_read_probe_program);
    pio_sm_config w=nt_write_probe_program_get_default_config(write_offset);
    pio_sm_config r=nt_read_probe_program_get_default_config(read_offset);
    sm_config_set_in_pins(&w,26);sm_config_set_in_pins(&r,26);
    pio_sm_init(pio1,0,write_offset,&w);
    pio_sm_init(pio1,1,read_offset,&r);
    pio_sm_set_enabled(pio1,0,true);pio_sm_set_enabled(pio1,1,true);
}

static inline void nt_address_probe_poll(nt_address_probe *p) {
    for(unsigned sm=0;sm<2;sm++) {
        while(!pio_sm_is_rx_fifo_empty(pio1,sm)) {
            uint32_t v=pio_sm_get(pio1,sm);
            if(v&(1u<<16)) {
                uint32_t *pages=sm?p->read_pages:p->write_pages;
                pages[(v>>8)&3]++;
            } else if(sm)p->read_other++;
            else p->write_other++;
        }
    }
}

static void nt_address_probe_report(const nt_address_probe *p) {
    printf("ALOG read=%lu,%lu,%lu,%lu write=%lu,%lu,%lu,%lu other=%lu,%lu fdebug=%08lx\n",
        (unsigned long)p->read_pages[0],(unsigned long)p->read_pages[1],
        (unsigned long)p->read_pages[2],(unsigned long)p->read_pages[3],
        (unsigned long)p->write_pages[0],(unsigned long)p->write_pages[1],
        (unsigned long)p->write_pages[2],(unsigned long)p->write_pages[3],
        (unsigned long)p->read_other,(unsigned long)p->write_other,(unsigned long)pio1->fdebug);
}
