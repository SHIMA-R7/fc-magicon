#define CART_HOST
#define FC_DIAG_CPU_ONLY 1
#define FC_DIAG_DIRECT_CHR 1
#define FC_DIAG_IMAGE 1
#include <assert.h>
#include <stdio.h>
#include "../magicon/cart.c"
bool host_irq;
int main(void) {
    cart_info_t info;cart_load_fallback(&info);
    for(unsigned a=0;a<32768;a++)assert(rom[a]==static_image_prg[a%16384]);
    for(unsigned a=0;a<8192;a++)assert(cart_host_peek_chr(a)==static_image_chr[a]);
    assert(rom[0x3ffc]==0 && rom[0x3ffd]==0xc0);
    assert(STATIC_IMAGE_LOOP_END-STATIC_IMAGE_LOOP_START==10);
    assert(rom[STATIC_IMAGE_LOOP_START]==0xe6);
    diag_marks=1;
    diag_record_cpu(B_RW | ((0x4000+STATIC_IMAGE_LOOP_START)<<8),0x8000ffe6);
    assert(!diag_trace_count);
    diag_record_cpu(B_RW | ((0x4000+STATIC_IMAGE_LOOP_END)<<8),0x8000ff40);
    assert(diag_trace_count==2);
    puts("PASS static-image PRG/CHR mirrors, vectors and diagnostic loop bounds");
}
