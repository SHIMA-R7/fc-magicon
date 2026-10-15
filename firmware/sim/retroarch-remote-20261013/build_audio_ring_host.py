"""Compile the actual audio ring logic, substituting only the RP DMA/PWM setup."""
from pathlib import Path
import re,subprocess
here=Path(__file__).resolve().parent
source=(here.parents[1]/'magicon/audio.c').read_text(encoding='utf-8')
source=re.sub(r'#include "(?:pico|hardware)/[^\n]+\n','',source)
source=source.replace('__attribute__((aligned(RING_LEN * 2)))','') # DMA ring alignment is not used on the host.
source=source.replace('#include "audio.h"','#include <stdint.h>\n#include <stdbool.h>\n#include "../../magicon/audio.h"\nstatic uint32_t sim_idx;\nstatic uint64_t sim_puts,sim_resets;')
start=source.index('static uint32_t rd_index(void)');end=source.index('void audio_poll(void)',start)
source=source[:start]+'''static uint32_t rd_index(void){return sim_idx;}
__declspec(dllexport) void host_reset(void){
 for(unsigned i=0;i<RING_LEN;i++)ring[i]=SILENCE;
 sim_idx=0;dma_ch=1;rd_abs=wr_abs=cleared_abs=last_rd_idx=0;sim_puts=sim_resets=0;
}
__declspec(dllexport) void host_advance(unsigned n,uint16_t *out){
 for(unsigned i=0;i<n;i++){out[i]=ring[sim_idx];sim_idx=(sim_idx+1)&RING_MASK;}
}
'''+source[end:]
source=source.replace('wr_abs++;','wr_abs++;sim_puts++;')
source=source.replace('wr_abs = rd_abs + LATENCY;','sim_resets++;wr_abs = rd_abs + LATENCY;')
source=source.replace('void audio_poll(void)','__declspec(dllexport) void audio_poll(void)')
source=source.replace('void audio_push(uint8_t','__declspec(dllexport) void audio_push(uint8_t')
source=source.replace('unsigned audio_local_space(void)', '__declspec(dllexport) unsigned audio_local_space(void)')
source=source.replace('void audio_local_write(const int16_t', '__declspec(dllexport) void audio_local_write(const int16_t')
source+='''
__declspec(dllexport) uint64_t host_puts(void){return sim_puts;}
__declspec(dllexport) uint64_t host_resets(void){return sim_resets;}
__declspec(dllexport) uint32_t host_lead(void){return wr_abs-rd_abs;}
'''
(here/'audio-ring-host.c').write_text(source,encoding='utf-8')
subprocess.run(['C:/Users/Yugo/pico/zig/zig-x86_64-windows-0.16.0/zig.exe','cc','-O2','-shared',str(here/'audio-ring-host.c'),'-o',str(here/'audio-ring-host.dll')],check=True)
