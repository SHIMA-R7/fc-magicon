"""FIFO capacity and service-delay tests, not electrical or ARM timing simulation."""
from pathlib import Path
from test_pio_logic import run

root=Path(__file__).resolve().parents[1]
def a12(t):
    return ((1<<25) if t%140<84 else 0)|((1<<38) if t%1400>=1000 else 0)

# A12 joins both FIFOs into an eight-word RX queue. No servicing loses events.
ideal=run(root/'magicon/mmc3_a12.pio',a12,base=25,jmp_pin=38,steps=28000)
stats={}
blocked=run(root/'magicon/mmc3_a12.pio',a12,base=25,jmp_pin=38,steps=28000,rx_capacity=8,stats=stats)
assert len(ideal[1])==20
assert len(blocked[1])==8 and stats['rx_dropped']==12 and not blocked[0]
serviced={}
timely=run(root/'magicon/mmc3_a12.pio',a12,base=25,jmp_pin=38,steps=28000,rx_capacity=8,rx_drain_at=range(1200,28000,1400),stats=serviced)
assert len(timely[1])==20 and serviced['rx_dropped']==0
print('PASS A12 RX: 20 events; unserviced queue retains 8/drops 12; timely servicing retains all')

# CPU RX is four words; ARM acknowledgements alone do not empty this queue.
def writes(t):
    return ((1<<25) if 5<=t%140<80 else 0)|0x5a
cpu_stats={}
cpu=run(root/'magicon/cpu_m2.pio',writes,reply_at=[100,240,380,520,660],reply=0x80010000,steps=800,rx_capacity=4,stats=cpu_stats)
assert len(cpu[1])==4 and cpu_stats['rx_stall_ticks']>0 and not cpu[0]
recovered_stats={}
recovered=run(root/'magicon/cpu_m2.pio',writes,reply_at=[100,240,380,520,660],reply=0x80010000,steps=800,rx_capacity=4,rx_drain_at=range(20,800,35),stats=recovered_stats)
assert len(recovered[1])>=10 and not recovered[0] and recovered_stats['rx_stall_ticks']==0
print('PASS CPU RX: full queue stalls without driving write bus; draining preserves transactions')
