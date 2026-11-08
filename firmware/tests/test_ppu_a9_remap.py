"""Execute remapped PIO over every CHR address, including disconnected GPIO35 noise."""
from pathlib import Path
from test_pio_logic import run

path=Path(__file__).resolve().parents[1]/'standalone_video/baseline/ppu_lookup_a9_39.pio'
table=0x20010000
def pins(address,old,nt=0):
    return ((address&0x1dff)<<26)|(((address>>9)&1)<<39)|(old<<35)|(nt<<42)

for address in range(8192):
    for old in (0,1):
        def levels(t):
            # Multiplexed AD0..7 no longer carry the address after /RD falls.
            value=pins(address,old) if t<8 else pins(address^0x1fff,1-old)
            return value|((1<<40) if t<8 or t>=70 else 0)
        out=[]
        driven,pushes,_,values=run(path,levels,reply_at=[0,40],
            reply=[table>>15,0xff00|(address&255)],steps=90,
            base=26,jmp_pin=40,data_out=out)
        assert values==[table+4*address],(address,old,values)
        assert out and out[0][1]==address&255,(address,out)
        assert driven
for address in (0,0x200,0x1fff):
    def levels(t):return pins(address,1,1)|((1<<40) if t<8 or t>=70 else 0)
    result=run(path,levels,reply_at=[0,40],reply=[table>>15,0xffff],steps=90,base=26,jmp_pin=40)
    assert result[3]==[table+4*address] and not result[0]
    def short(t):return pins(address,1)|((1<<40) if t<8 or t>=12 else 0)
    assert not run(path,short,reply_at=[0,40],reply=[table>>15,0xffff],steps=90,base=26,jmp_pin=40)[0]
print('PASS: all 8192 addresses, both old GPIO35 levels, multiplexed address capture, NT and late-response isolation')
