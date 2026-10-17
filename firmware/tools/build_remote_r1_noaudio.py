"""Exact r1 comparison: skip audio_init(44), preserve all other UF2 bytes.

The checked original instruction is a Thumb BL from 0x100003de to
0x10002390, immediately after movs r0,#44. Its target has been checked
against the original PIO audio initialization disassembly. Replace with
two Thumb NOPs. audio_poll/push retain their dma_ch<0 early returns.
No device access. This is a diagnostic, intentionally without sound.
"""
import hashlib
import json
import struct
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'out-standalone-video/remote-desktop-usb-a9-gpio39-20261017-r1-confirmed.uf2'
OUT=ROOT/'out-standalone-video/remote-desktop-usb-r1-noaudio-20261018.uf2'
EXPECTED='d1519162bc985604b754ef6880487e6870d1567da0e1b5374fb4f67c7b884899'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pin-mute',action='store_true',help='Keep audio DMA/PIO but leave GPIO44 on disabled PWM')
    args=parser.parse_args()
    original=BASE.read_bytes();assert hashlib.sha256(original).hexdigest()==EXPECTED
    data=bytearray(original);memory={};positions={}
    for offset in range(0,len(data),512):
        assert struct.unpack_from('<II',data,offset)==(0x0a324655,0x9e5d5157)
        assert struct.unpack_from('<I',data,offset+508)[0]==0x0ab16f30
        addr,n=struct.unpack_from('<II',data,offset+12)
        assert n==256 and struct.unpack_from('<I',data,offset+8)[0] in (0x2000,0xa000)
        for i in range(n):
            assert addr+i not in memory
            memory[addr+i]=data[offset+32+i];positions[addr+i]=offset+32+i
    def read(addr,n):return bytes(memory[addr+i] for i in range(n))
    assert read(0x100003dc,6)==bytes.fromhex('2c2001f0d7ff')
    assert read(0x10002390,4)==bytes.fromhex('2de9f047')
    # Actual audio_poll and audio_push check the disabled DMA channel first.
    assert read(0x10002600,4)==bytes.fromhex('002b26db')
    assert read(0x100026a8,6)==bytes.fromhex('002bc0f28980')
    if args.pin_mute:
        # gpio_set_function(pin, GPIO_FUNC_PIO2=8) -> GPIO_FUNC_PWM=4.
        # PWM was disabled earlier; PIO2/SM2 and its DMA remain enabled.
        # RP2350 SDK io_bank0.h defines PWM=4, PIO2=8.
        address=0x10002522;before=bytes.fromhex('0821');after=bytes.fromhex('0421')
        assert read(0x10002520,10)==bytes.fromhex('20460821069300f045fb')
        output=ROOT/'out-standalone-video/remote-desktop-usb-r1-pinmute-20261018.uf2'
    else:
        address=0x100003de;before=bytes.fromhex('01f0d7ff');after=bytes.fromhex('00bf00bf');output=OUT
    for i,value in enumerate(after):data[positions[address+i]]=value
    changed=[i for i,(a,b) in enumerate(zip(original,data)) if a!=b]
    assert len(changed)==(1 if args.pin_mute else 4)
    assert all(i in {positions[address+j] for j in range(len(after))} for i in changed)
    output.write_bytes(data)
    report=dict(base_sha256=EXPECTED,sha256=hashlib.sha256(data).hexdigest(),
                patch_address=hex(address),original=before.hex(),replacement=after.hex(),
                changed_bytes=len(changed),audio_dma_and_pio_enabled=args.pin_mute,
                device_written=False,hardware_result='pending')
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
