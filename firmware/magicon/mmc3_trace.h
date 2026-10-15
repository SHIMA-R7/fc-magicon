#pragma once
#if FC_MMC3_TRACE && !defined(CART_HOST)
// Bounded diagnostic only. Core1 owns CPU records; core0 owns IRQ/copy records.
typedef struct {uint32_t us,kind,data,aux;} m3_trace_record;
static m3_trace_record m3_trace_cpu[256],m3_trace_irq[128],m3_trace_chr[128];
static volatile uint32_t m3_trace_cpu_n,m3_trace_irq_n,m3_trace_chr_n;
static volatile uint32_t m3_trace_cpu_over,m3_trace_irq_over,m3_trace_chr_over;
static atomic_uint m3_trace_epoch,m3_trace_active;
static uint32_t m3_trace_cpu_epoch,m3_trace_end,m3_trace_started;
static bool m3_trace_pending;
static void __not_in_flash_func(m3_trace_cpu_record)(uint32_t kind,uint32_t data,uint32_t aux) {
    if(!atomic_load_explicit(&m3_trace_active,memory_order_acquire))return;
    uint32_t epoch=atomic_load_explicit(&m3_trace_epoch,memory_order_relaxed);
    if(epoch!=m3_trace_cpu_epoch){m3_trace_cpu_epoch=epoch;m3_trace_cpu_n=m3_trace_cpu_over=0;}
    uint32_t n=m3_trace_cpu_n;
    if(n>=256){m3_trace_cpu_over++;return;}
    m3_trace_cpu[n]=(m3_trace_record){time_us_32(),kind,data,aux};
    __dmb();m3_trace_cpu_n=n+1;
}
static void __not_in_flash_func(m3_trace_core0_record)(bool chr,uint32_t kind,uint32_t data,uint32_t aux) {
    if(!atomic_load_explicit(&m3_trace_active,memory_order_relaxed))return;
    volatile uint32_t *count=chr?&m3_trace_chr_n:&m3_trace_irq_n;
    volatile uint32_t *over=chr?&m3_trace_chr_over:&m3_trace_irq_over;
    uint32_t n=*count;
    if(n>=128){++*over;return;}
    (chr?m3_trace_chr:m3_trace_irq)[n]=(m3_trace_record){time_us_32(),kind,data,aux};
    __dmb();*count=n+1;
}
static void m3_trace_begin(void) {
    if(atomic_load(&m3_trace_active)||m3_trace_pending)return;
    m3_trace_irq_n=m3_trace_chr_n=m3_trace_irq_over=m3_trace_chr_over=0;
    atomic_fetch_add(&m3_trace_epoch,1);
    m3_trace_started=time_us_32();m3_trace_end=m3_trace_started+64000;
    m3_trace_pending=true;atomic_store_explicit(&m3_trace_active,1,memory_order_release);
}
static void m3_trace_dump(void) {
    uint32_t cpu=m3_trace_cpu_epoch==atomic_load(&m3_trace_epoch)?m3_trace_cpu_n:0;
    printf("MMC3_TRACE_BEGIN start=%lu cpu=%lu irq=%lu chr=%lu over=%lu/%lu/%lu\n",
        (unsigned long)m3_trace_started,(unsigned long)cpu,(unsigned long)m3_trace_irq_n,(unsigned long)m3_trace_chr_n,
        (unsigned long)(m3_trace_cpu_epoch==atomic_load(&m3_trace_epoch)?m3_trace_cpu_over:0),(unsigned long)m3_trace_irq_over,(unsigned long)m3_trace_chr_over);
    m3_trace_record *buffers[]={m3_trace_cpu,m3_trace_irq,m3_trace_chr};
    uint32_t counts[]={cpu,m3_trace_irq_n,m3_trace_chr_n};
    for(unsigned b=0;b<3;b++)for(unsigned n=0;n<counts[b];n++) {
        m3_trace_record r=buffers[b][n];
        printf("M3EV %u %lu %lu %08lx %08lx\n",b,(unsigned long)(r.us-m3_trace_started),
            (unsigned long)r.kind,(unsigned long)r.data,(unsigned long)r.aux);
    }
    puts("MMC3_TRACE_END");m3_trace_pending=false;
}
#define M3_TRACE_CPU(k,d,a) do { if(atomic_load_explicit(&m3_trace_active,memory_order_relaxed))m3_trace_cpu_record(k,d,a); } while(0)
#define M3_TRACE_0(c,k,d,a) m3_trace_core0_record(c,k,d,a)
#else
#define M3_TRACE_CPU(k,d,a) ((void)0)
#define M3_TRACE_0(c,k,d,a) ((void)0)
#endif
