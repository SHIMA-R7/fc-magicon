"""Position-address and independent output models; no electrical timing claim."""
from pathlib import Path
from test_pio_logic import run
ROOT=Path(__file__).resolve().parents[1]/'standalone_video/baseline'
TABLE=0x20010000

def levels(reads,period=100):
    def pins(t):
        k=min(t//period,len(reads)-1);address=reads[k]
        low=20<=t%period<75 and t//period<len(reads)
        # A0..7 are taken over by data after /RD falls; A8..13 stay stable.
        bits=(address&0x1f00)|((address&255) if not low else 0xa5)
        return (bits<<26)|((address&0x2000)<<29)|(0 if low else 1<<40)
    return pins

def main():
    count=0
    for tile in (0,1,31,32,511,959):
        for quadrant in (0,0x400,0x800,0xc00):
            for fine in range(16):
                reads=[0x2000|quadrant|tile,0x23c0|quadrant|(tile&63),0x1000|0x5a0|fine]
                requests=run(ROOT/'full_tiles_address.pio',levels(reads),reply_at=0,reply=TABLE>>6,base=26,jmp_pin=40,steps=300)[3]
                assert len(requests)==3 and requests[-1]==TABLE+(tile*16+fine)*4,(tile,fine,requests)
                count+=1
    # Pair the generated DMA request time with the independent output machine.
    pins=levels([0x20c3,0x23cc,0x00a5,0x00ad,0x20c4,0x23cc,0x0063])
    _,request_ticks,_,addresses=run(ROOT/'full_tiles_address.pio',pins,reply_at=0,reply=TABLE>>6,base=26,jmp_pin=40,steps=700)
    assert len(addresses)==7
    for latency in (3,10,20,40,65,90):
        output=[]
        driven,_,_,_=run(ROOT/'full_tiles_output.pio',pins,reply_at=[t+latency for t in request_ticks],reply=[0x8000ff88,0x8000ff88,0x8000ff11,0x8000ff22,0x8000ff88,0x8000ff88,0x8000ff33],base=42,jmp_pin=40,steps=800,data_out=output)
        assert all(not(pins(t)&(1<<42)) and not(pins(t)&(1<<40)) for t,_ in driven),(latency,driven)
        if latency<=20:assert [v for t,v in output]==[0x11,0x22,0x33],(latency,output)
    assert not run(ROOT/'full_tiles_output.pio',levels([0x2000,0x23c0]),base=42,jmp_pin=40,steps=200)[0]
    print('PASS',count,'position/plane combinations; DMA timing, nametable tri-state, deadline recovery')

if __name__=='__main__':main()
