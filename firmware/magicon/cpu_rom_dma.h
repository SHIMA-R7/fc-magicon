// Four PRG lanes use two DMA channels each. PPU DMA and IRQ remain unchanged.
#include "hardware/structs/sio.h"
static uint cpu_dma_program_offset,cpu_dma_reply_pc;
static uint32_t cpu_dma_rom_execctrl3;
static uint32_t cpu_dma_fall_time;
static inline __attribute__((always_inline)) bool cpu_dma_lane_idle(uint slot) {
    uint pc=pio0->sm[slot].addr;
    return pc==cpu_dma_program_offset || pc==cpu_dma_program_offset+1;
}
static inline __attribute__((always_inline)) void cpu_dma_publish_bank(uint slot,uint32_t prefix) {
    if(!cpu_dma_lane_idle(slot) || (uint32_t)(m33_hw->dwt_cyccnt-cpu_dma_fall_time)>=24) {
        cpu_dma_update_busy++;cpu_dma_fault_pc=pio0->sm[slot].addr;return;
    }
    pio0->txf[slot]=prefix;
}
static void cpu_rom_dma_start(void) {
    cpu_dma_program_offset=pio_add_program(pio0,&cpu_rom_dma_program);
    cpu_dma_reply_pc=cpu_dma_program_offset+cpu_rom_dma_offset_wram_reply;
    for(uint slot=0;slot<4;slot++) {
        hard_assert(!((uintptr_t)prg_map[slot]&8191));
        cpu_rom_dma_program_init(pio0,slot,cpu_dma_program_offset,(uint32_t)prg_map[slot]);
        uint data=dma_claim_unused_channel(true),address=dma_claim_unused_channel(true);
        cpu_dma_data_channel[slot]=data;
        dma_channel_config dc=dma_channel_get_default_config(data);
        channel_config_set_transfer_data_size(&dc,DMA_SIZE_8);
        channel_config_set_read_increment(&dc,false);channel_config_set_write_increment(&dc,false);
        dma_channel_configure(data,&dc,&pio0->txf[slot],prg_map[slot],1,false);
        dma_channel_config ac=dma_channel_get_default_config(address);
        channel_config_set_transfer_data_size(&ac,DMA_SIZE_32);
        channel_config_set_read_increment(&ac,false);channel_config_set_write_increment(&ac,false);
        channel_config_set_dreq(&ac,pio_get_dreq(pio0,slot,false));
        dma_channel_configure(address,&ac,&dma_hw->ch[data].al3_read_addr_trig,
            &pio0->rxf[slot],dma_encode_endless_transfer_count(),true);
    }
    cpu_dma_rom_execctrl3=pio0->sm[3].execctrl;
}
static inline __attribute__((always_inline)) void cpu_dma_finish_wram(void) {
    uint32_t start=m33_hw->dwt_cyccnt;
    while(!cpu_dma_lane_idle(3) && !(sio_hw->gpio_in&(1u<<25)) &&
        (uint32_t)(m33_hw->dwt_cyccnt-start)<24)tight_loop_contents();
    bool reset=!cpu_dma_lane_idle(3);
    if(reset) {
        cpu_dma_wram_busy++;cpu_dma_fault_pc=0x100|pio0->sm[3].addr;
        pio_sm_set_enabled(pio0,3,false);
        pio_sm_exec(pio0,3,pio_encode_mov(pio_osr,pio_null));
        pio_sm_exec(pio0,3,pio_encode_out(pio_pindirs,8));
        pio_sm_clear_fifos(pio0,3);
        pio_sm_exec(pio0,3,pio_encode_jmp(cpu_dma_program_offset));
    }
    pio0->sm[3].execctrl=cpu_dma_rom_execctrl3;
    // An exceptional recovery stays input/disabled until the next FC power
    // cycle; a delayed DMA byte must never become a source-address command.
}
static void __not_in_flash_func(cpu_dma_io_loop)(void) {
    save_and_disable_interrupts();
    m33_hw->demcr|=M33_DEMCR_TRCENA_BITS;m33_hw->dwt_ctrl|=M33_DWT_CTRL_CYCCNTENA_BITS;
    __dmb();bus_ready=true;
    for(;;) {
        while(!(sio_hw->gpio_in&(1u<<25)))tight_loop_contents();
        uint32_t begun=m33_hw->dwt_cyccnt;
        while((uint32_t)(m33_hw->dwt_cyccnt-begun)<10)tight_loop_contents();
        uint32_t h=sio_hw->gpio_in,last=h,v=h;
        if(!(h&(1u<<25)))continue;
        uint a=(h>>8)&0x7fff;
        uint addr=a|((h&B_ROMSEL)?0:0x8000);
        bool wram_reply=false;
        uint prepared=0,early=0;bool published=false;uint32_t source0=0,source1=0,source2=0;
        if(!(h&B_RW) && addr>=0x8000 && (addr&0xe000)==0x8000) {
            // Calculate during the write phase; only publish after validating
            // this sample against the final data at M2 falling.
            while((uint32_t)(m33_hw->dwt_cyccnt-begun)<32 && (sio_hw->gpio_in&(1u<<25)))tight_loop_contents();
            early=sio_hw->gpio_in&255;
            if(!(addr&1)) {
                if((m3_sel^early)&0x40){prepared=5;
                    source0=(uint32_t)prg_map[2]>>13;source2=(uint32_t)prg_map[0]>>13;}
            } else {
                uint reg=m3_sel&7;
                if(reg==6){uint slot=(m3_sel>>5)&2;prepared=1u<<slot;
                    uint32_t source=(uint32_t)prg_bank_addresses[(early&0x3f)&m3_prg_mask]>>13;
                    source0=source2=source;}
                else if(reg==7){prepared=2;source1=(uint32_t)prg_bank_addresses[(early&0x3f)&m3_prg_mask]>>13;}
            }
        }
        // A mapper write cannot drive ROM data. Queue the already sampled
        // bank command during its high phase, before the next low prefetch.
        if(prepared && (sio_hw->gpio_in&(1u<<25))) {
            if(prepared&1)pio0->txf[0]=source0;
            if(prepared&2)pio0->txf[1]=source1;
            if(prepared&4)pio0->txf[2]=source2;
            published=true;
        }
        if((h&(B_RW|B_ROMSEL))==(B_RW|B_ROMSEL) && a>=0x6000 && wram_enabled) {
            // Lane 3 is idle on WRAM cycles; reuse its M2-guarded reply tail.
            // That tail preserves X/Y for its subsequent ROM cycle.
            while(pio0->sm[3].addr!=cpu_dma_program_offset && (sio_hw->gpio_in&(1u<<25)))tight_loop_contents();
            if(pio0->sm[3].addr==cpu_dma_program_offset && (sio_hw->gpio_in&(1u<<25))) {
                pio0->sm[3].execctrl=(cpu_dma_rom_execctrl3&~PIO_SM0_EXECCTRL_JMP_PIN_BITS)|
                    (25u<<PIO_SM0_EXECCTRL_JMP_PIN_LSB);
                pio0->txf[3]=wram[a&0x1fff];
                pio0->sm[3].instr=pio_encode_jmp(cpu_dma_reply_pc);
                wram_reply=true;
            } else cpu_dma_wram_busy++;
        }
        v=sio_hw->gpio_in;
        if(!(v&(1u<<25))){
            if(wram_reply)cpu_dma_finish_wram();
            if(h&B_RW)cpu_dma_read_miss++;else cpu_dma_write_miss++;
            continue;
        }
        do {last=v;v=sio_hw->gpio_in;}while(v&(1u<<25));
        cpu_dma_fall_time=m33_hw->dwt_cyccnt;
        if(wram_reply)cpu_dma_finish_wram();
        if(!(h&B_RW)) {
            if(addr>=0x8000) {
                if(prepared && early==(last&255)) {
                    if(!published) {
                    if(prepared&1)cpu_dma_publish_bank(0,source0);
                    if(prepared&2)cpu_dma_publish_bank(1,source1);
                    if(prepared&4)cpu_dma_publish_bank(2,source2);
                    }
                } else prepared=0;
                uint changed=mmc3_dma_write(addr,last&255);
                if(!prepared) {
                    if(changed&1)cpu_dma_publish_bank(0,(uint32_t)prg_map[0]>>13);
                    if(changed&2)cpu_dma_publish_bank(1,(uint32_t)prg_map[1]>>13);
                    if(changed&4)cpu_dma_publish_bank(2,(uint32_t)prg_map[2]>>13);
                }
                m3_last_write=(addr<<8)|(last&255);m3_write_count++;
            } else if(addr>=0x6000 && wram_enabled&&!wram_protected)wram[addr&0x1fff]=last&255;
            stat_wr++;
        }
        stat_cpu++;
    }
}
