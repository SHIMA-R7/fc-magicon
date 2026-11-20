"""Execute real PIO control flow, not DMA/electrical latency."""
from pathlib import Path
from test_pio_logic import run
pio=Path(__file__).resolve().parents[1]/'magicon/cpu_rom_dma.pio'

def bus(address,write=False):
    def pins(t):
        active=70<=t<180
        return ((address&0x7fff)<<8)|((1<<23) if not active or address<0x8000 else 0)|(0 if write else 1<<24)|((1<<25) if active else 0)
    return pins

cases=0
for source in (0x20010000,0x15020000):
    for lane in range(4):
        initial={'x':source>>13,'y':lane}
        for bank in range(4):
            for offset in (0,1,255,1023,4095,4096,8191):
                out=[]
                driven,_,_,values=run(pio,bus(0x8000+bank*8192+offset),base=21,gpio_window_base=0,jmp_pin=23,
                    reply_at=110,reply=0xa5,steps=220,data_out=out,initial_registers=initial)
                cases+=1
                if lane==bank:
                    assert values==[source+offset],(lane,bank,offset,values)
                    assert driven and all(70<=t<180 and mask==255 for t,mask in driven)
                    assert out[0][1]==0xa5
                else:assert not driven and not values
        for address in (0x2002,0x6000,0x7fff):
            driven,_,_,values=run(pio,bus(address),base=21,gpio_window_base=0,jmp_pin=23,initial_registers=initial)
            assert not driven
        assert not run(pio,bus(0x8001,True),base=21,gpio_window_base=0,jmp_pin=23,initial_registers=initial)[3]
        assert not run(pio,bus(0x8000+lane*8192+123),base=21,gpio_window_base=0,jmp_pin=23,reply_at=210,
            reply=0xaa,initial_registers=initial)[0]

def consecutive(t):
    active=70<=t<180 or 240<=t<350
    address=0x9234 if t<190 else 0x8567
    return ((address&0x7fff)<<8)|(0 if active else 1<<23)|(1<<24)|((1<<25) if active else 0)
_,_,_,values=run(pio,consecutive,base=21,gpio_window_base=0,jmp_pin=23,reply_at=[110,280],reply=[0xaa,0x55],steps=390,
    initial_registers={'x':0x15020000>>13,'y':0})
assert values==[0x15021234,0x15020567],values

# A bank command is consumed before a speculative address is generated, and
# the later byte reply must not be mistaken for a command.
_,_,_,values=run(pio,bus(0x8123),base=21,gpio_window_base=0,jmp_pin=23,
    reply_at=[0,110],reply=[0x15060000>>13,0xa5],steps=220,
    initial_registers={'x':0x15020000>>13,'y':0})
assert values==[0x15060123],values

for arrival in (90,140,190,220):
    out=[]
    driven,_,_,values=run(pio,bus(0x6000),reply_at=arrival,reply=0x36,steps=200,
        base=21,gpio_window_base=0,jmp_pin=25,entry_label='wram_reply',initial_registers={'x':0x15020000>>13,'y':3},data_out=out)
    assert all(70<=t<180 for t,_ in driven)
    if arrival>=180:assert not driven and not out
print(f'PASS speculative CPU ROM DMA: {cases} address/lane cases, SRAM/PSRAM addressing, writes, WRAM isolation and late ACKs')
