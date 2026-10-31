"""Compile the actual control read/write/staging paths into a host regression.

The host test checks protocol/state, not the analogue M2 deadline. The latter
must also be tested on an FC: an ordinary emulator accepts late responses.
"""
import os
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'standalone_video/baseline/cart.c'


def function(text, name):
    declaration = re.search(r'^.*\b' + name + r'\)?\([^;\n]*\)\s*\{', text, re.MULTILINE)
    assert declaration, name
    start = declaration.start()
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    text = SOURCE.read_text(encoding='utf-8')
    harness = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#define CART_HOST 1
#define FC_REMOTE_FULL 1
#define FC_PLAYER_FAST_CONTROL 1
#define __not_in_flash_func(x) x
#define B_RW (1u<<24)
#define B_ROMSEL (1u<<23)
typedef unsigned uint;
typedef struct {uint8_t pal[32],attr[64],oam[256];} rd_meta_t;
static rd_meta_t meta[2],*rd_meta_front=&meta[0],*rd_meta_back=&meta[1];
static uint8_t rd_io[256],rd_nt[1024],rd_prg[16384],rd_visible_bank;
static volatile bool rd_ready;
static bool wr_pending;
static uint stat_wr;
static uint32_t diag_chr_lookup[8192],rd_palette_replies[32];
static volatile uint32_t rd_control_replies[256];
static unsigned chr_lookup_index(unsigned a) {return a;}
'''
    harness += '\n'.join(function(text, name) for name in
                         ('remote_write', 'remote_fast_read', 'cart_video_stage'))
    harness += r'''
static uint32_t read_control(unsigned address) {
    uint32_t result=0;
    assert(remote_fast_read((address<<8)|B_RW|B_ROMSEL,&result));
    return result;
}
int main(void) {
    uint8_t record[5152];
    memset(record,0xa5,sizeof record);
    for(unsigned i=0;i<256;i++)rd_control_replies[i]=0x8000ffffu;
    rd_control_replies[0x10]=0x8000ff00u;
    assert(read_control(0x5f10)==0x8000ff00u); // valid driven zero
    // A 6502 RMW read must see the preceding write, including wraparound.
    remote_write(0x5f0f,0);
    for(unsigned i=0;i<1000;i++) {
        uint8_t old=read_control(0x5f0f)&255;
        assert(old==(i&255));
        remote_write(0x5f0f,old); // RMW dummy write
        remote_write(0x5f0f,(old+1)&255);
    }
    assert(cart_video_stage(record));
    assert(read_control(0x5f10)==0x8000ff03u);
    assert(!cart_video_stage(record));
    remote_write(0x5f11,0); // wrong bank may not consume the frame
    assert(rd_ready);
    remote_write(0x5f11,1);
    assert(!rd_ready && rd_visible_bank==1);
    assert(read_control(0x5f10)==0x8000ff00u);
    assert(cart_video_stage(record));
    assert(read_control(0x5f10)==0x8000ff01u);
    remote_write(0x5f11,0);
    assert(!rd_ready && rd_visible_bank==0);
    for(unsigned i=0;i<8192;i++)assert(diag_chr_lookup[i]==0x8000ffa5u);
    uint32_t ignored;
    wr_pending=true;
    assert(!remote_fast_read((0x5f10u<<8)|B_RW|B_ROMSEL,&ignored));
    return 0;
}
'''
    compiler = os.environ.get('ZIG_EXE', 'C:/Users/Yugo/pico/zig/zig-x86_64-windows-0.16.0/zig.exe')
    with tempfile.TemporaryDirectory(prefix='fc-control-test-') as directory:
        source = Path(directory) / 'test.c'
        binary = Path(directory) / 'test.exe'
        source.write_text(harness, encoding='utf-8')
        subprocess.run([compiler, 'cc', '-O2', '-std=gnu11', str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('PASS: real control paths, 1000 RMW increments, both frame banks, ACK validation')


if __name__ == '__main__':
    main()
