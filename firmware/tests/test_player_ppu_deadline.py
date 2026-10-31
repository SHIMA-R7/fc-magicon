"""Stock GPIO player: expired DMA replies, valid zero-direction tiles, recovery.

Instruction model only; real FC timing and analogue levels require hardware.
"""
from pathlib import Path
from test_pio_logic import run

PIO=Path(__file__).resolve().parents[1]/'standalone_video/baseline/ppu_lookup.pio'
TABLE=0x20008000

def main():
    for address in (0,1,7,8,255,256,4095,4096,8191):
        def pins(t):return ((1<<40) if t<8 or t>=75 else 0)|((address if t<8 else 8191-address)<<26)
        out=[]
        driven,_,_,requests=run(PIO,pins,reply_at=[0,35],reply=[TABLE>>15,0x8000ffa5],base=26,jmp_pin=40,data_out=out)
        assert requests==[TABLE+address*4] and driven and out[0][1]==0xa5
    for delay in range(20,180):
        def pins(t):return ((1<<40) if t<8 or 50<=t<100 or t>=150 else 0)|((1<<42) if t>=75 else 0)
        driven,_,_,_=run(PIO,pins,reply_at=[0,delay],reply=[TABLE>>15,0x8000ff55],base=26,jmp_pin=40,steps=220)
        assert not any(pins(t)&(1<<42) for t,v in driven),(delay,driven)
    def two(t):return ((1<<40) if t<8 or 60<=t<100 or t>=180 else 0)
    out=[]
    driven,_,_,requests=run(PIO,two,reply_at=[0,35,135],reply=[TABLE>>15,0x80000000,0x8000ff22],base=26,jmp_pin=40,steps=220,data_out=out)
    assert len(requests)==2 and [v for t,v in out]==[0,0x22]
    assert driven and all(t>=100 for t,v in driven)
    def recovery(t):return ((1<<40) if t<8 or 50<=t<100 or t>=170 else 0)|((0x123 if t<8 else 0x456)<<26)
    out=[]
    driven,_,_,requests=run(PIO,recovery,reply_at=[0,80,130],reply=[TABLE>>15,0x8000ff11,0x8000ff22],base=26,jmp_pin=40,steps=220,data_out=out)
    assert out and [v for t,v in out]==[0x22]
    assert requests==[TABLE+0x123*4,TABLE+0x456*4]
    print('PASS: stock player DMA deadline, zero-direction reply, address and recovery')

if __name__=='__main__':main()
