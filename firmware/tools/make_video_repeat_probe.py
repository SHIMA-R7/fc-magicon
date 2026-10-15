"""Repeat already-packed frames for a physical display comparison; no device access."""
import argparse,json,struct,zlib
from pathlib import Path

HEADER=struct.Struct('<4s15I')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path)
    ap.add_argument('output',type=Path)
    a=ap.parse_args()
    data=a.source.read_bytes();h=list(HEADER.unpack_from(data))
    assert h[0]==b'FCPV' and h[1:3]==[1,64]
    assert h[4:6]==[4,1] and h[8]==5152 and h[11]==len(data)
    assert zlib.crc32(data[64:])==h[12] and h[3]>=97
    # Source timestamps 21.25..24.00s, including the observed scene change.
    context=list(range(85,97))
    hold=91 # source 22.75s: arm/sky scene near the recorded black rectangle
    order=[hold]*12+context*6+[hold]*12
    video=b''.join(data[h[9]+k*h[8]:h[9]+(k+1)*h[8]] for k in order)
    samples=len(order)*h[6]//4
    body=video+bytes([128])*samples
    h[3]=len(order);h[7]=samples;h[10]=64+len(video);h[11]=64+len(body)
    h[12]=zlib.crc32(body)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(HEADER.pack(*h)+body)
    # Read back records and compare exact source bytes, including CHR/NT/palette.
    got=a.output.read_bytes()
    for i,k in enumerate(order):
        assert got[64+i*5152:64+(i+1)*5152]==data[64+k*5152:64+(k+1)*5152]
    assert set(got[h[10]:])=={128}
    result=dict(source=str(a.source.resolve()),frames=len(order),fps=4,duration_s=len(order)/4,
        source_frame_order=order,audio='unsigned PCM8 silence; normal audio engine remains active',
        phases=[dict(begin_s=0,end_s=3,mode='same frame, alternating display banks',source_s=22.75),
                dict(begin_s=3,end_s=21,mode='21.25..24.00s source excerpt repeated six times'),
                dict(begin_s=21,end_s=24,mode='same frame, alternating display banks',source_s=22.75)],
        records_match_source=True,device_written=False)
    a.output.with_suffix('.probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='source_frame_order'},indent=2))

if __name__=='__main__':main()
