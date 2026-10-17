"""Nano parser, input ownership and real sketch via native Arduino IO shim.

No COM access or OS input injection.
"""
from pathlib import Path
import ctypes as C
import random
import subprocess
import sys
import tempfile
import time
import binascii

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from nano_mouse import Parser,MouseState,NanoMouse,packet,QUERY

def parser_and_state():
    assert binascii.crc_hqx(b'123456789',0xffff)==0x29b1
    frames=[packet(0,0,0)]+[packet(1,i%256,1,i%4,i%255-127,127-i%255) for i in range(1,600)]
    broken=bytearray(packet(1,4,1,3,10,20));broken[8]^=64
    wire=b'noise'+b''.join(frames[:20])+bytes(broken)+b'rubbish'+b''.join(frames[20:])
    parser=Parser();got=[];rng=random.Random(9)
    while wire:
        n=rng.randrange(1,38);got+=parser.feed(wire[:n]);wire=wire[n:]
    assert len(got)==len(frames) and parser.bad>=1
    assert [packet(*e) for e in got]==frames
    assert Parser().feed(packet(1,0,1,0,-128,0))==[]
    moves=[];buttons=[];s=MouseState(lambda x,y:moves.append((x,y)),buttons.append,.5)
    s.update((1,1,1,1,1,-1),1);s.update((1,2,1,1,1,-1),1.1)
    assert moves==[(1,-1)] and buttons==[2]
    s.update((1,2,1,1,1,-1),1.1);assert moves==[(1,-1)]
    s.update((1,3,2,1,0,0),1.2);s.update((2,4,1,0,0,0),1.3);assert buttons==[2]
    s.expire(1.8);assert buttons==[2,4]
    s.update((1,5,1,3,0,0),2);s.release();assert buttons[-4:]==[2,8,4,16]
    print('PASS: CRC, fragmentation, corrupt-byte resync, sign bounds, duplicate reports, fractional gain, two-port button ownership, timeout/release')

def worker():
    moves=[];buttons=[];holders=[]
    class Serial:
        def __init__(self,*a,**kw):self.rx=bytearray();self.closed=False;self.writes=[];holders.append(self)
        def write(self,b):
            self.writes.append(b)
            self.rx+=packet(0,1,0)+packet(1,2,1,1,-3,4)
            return len(b)
        def read(self,n):
            time.sleep(.002)
            b=bytes(self.rx[:3]);del self.rx[:3];return b
        def close(self):self.closed=True
    nano=NanoMouse('FAKE',lambda x,y:moves.append((x,y)),buttons.append,6,Serial);nano.start()
    deadline=time.monotonic()+2
    while not moves and time.monotonic()<deadline:time.sleep(.005)
    nano.stop.set();nano.join(1)
    assert not nano.is_alive() and nano.error is None and nano.ready.is_set()
    assert moves==[(-18,24)] and buttons==[2,4] and holders[0].closed and holders[0].writes[0]==QUERY
    print('PASS: actual reader thread handshake, fractional serial reads, movement and stop cleanup')

def sketch():
    shim=r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <vector>
#define A0 14
#define A1 15
#define A3 17
#define A5 19
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT_PULLUP 2
extern uint32_t raw[2], nowms; extern int indices[2];
class MockSerial {
public:
std::vector<uint8_t> tx,rx;size_t pos=0;
void begin(unsigned long){} int available(){return rx.size()-pos;}
int read(){return rx[pos++];} size_t write(const uint8_t*p,size_t n){tx.insert(tx.end(),p,p+n);return n;}
};
extern MockSerial Serial;
inline void pinMode(int,int){}
inline void digitalWrite(int p,int v){if(p==A0 && v==HIGH)indices[0]=indices[1]=0;}
inline int digitalRead(int p){int n=p==A1?0:1;return (raw[n]>>(31-indices[n]++))&1;}
inline void delayMicroseconds(unsigned){} inline void delay(unsigned n){nowms+=n;}
inline uint32_t millis(){return nowms;}
'''
    source=r'''
#include "Arduino.h"
uint32_t raw[2]={0xffffffff,0xffffffff},nowms=200;int indices[2]={0,0};MockSerial Serial;
void scanSFC();bool dx_or_dy_nonzero(uint8_t,uint8_t);
#include "SKETCH"
extern "C" __declspec(dllexport) unsigned run(uint32_t a,uint32_t b,uint8_t *out){
 setup();raw[0]=a;raw[1]=b;
 processSFCPort(a,SFC1_BUTTON_BASE,SFC1_MOUSE_ID,sfc1IsMouse,sfc1PadButtons,sfc1MouseButtons,false,sfc1PadCandidate,sfc1PadCandidateCount);
 if(!Serial.tx.empty())return 0; // No USB output without an explicit PC handshake.
 toPico.tx.clear();
 const char*q="FCNM?\n";Serial.rx.assign(q,q+6);usbMousePoll();
 processSFCPort(a,SFC1_BUTTON_BASE,SFC1_MOUSE_ID,sfc1IsMouse,sfc1PadButtons,sfc1MouseButtons,false,sfc1PadCandidate,sfc1PadCandidateCount);
 processSFCPort(b,SFC2_BUTTON_BASE,SFC2_MOUSE_ID,sfc2IsMouse,sfc2PadButtons,sfc2MouseButtons,false,sfc2PadCandidate,sfc2PadCandidateCount);
 for(unsigned i=0;i<Serial.tx.size();i++)out[i]=Serial.tx[i];return Serial.tx.size();
}
extern "C" __declspec(dllexport) unsigned pico_bytes(uint8_t*out){for(unsigned i=0;i<toPico.tx.size();i++)out[i]=toPico.tx[i];return toPico.tx.size();}
'''.replace('SKETCH',str(ROOT/'nano_sfc_mouse/nano_sfc_mouse.ino').replace('\\','/'))
    zig=next(Path('C:/Users/Yugo/pico/zig').rglob('zig.exe'))
    with tempfile.TemporaryDirectory(prefix='nano-sfc-test-',ignore_cleanup_errors=True) as temp:
        d=Path(temp);(d/'Arduino.h').write_text(shim);(d/'test.cpp').write_text(source)
        (d/'SoftwareSerial.h').write_text('#pragma once\n#include "Arduino.h"\nclass SoftwareSerial { public: std::vector<uint8_t> tx;SoftwareSerial(int,int){} void begin(unsigned long){} size_t write(uint8_t b){tx.push_back(b);return 1;} };\n')
        subprocess.run([str(zig),'c++','-shared','-O2','-I',str(d),str(d/'test.cpp'),'-o',str(d/'test.dll')],check=True)
        lib=C.CDLL(str(d/'test.dll'));lib.run.argtypes=[C.c_uint32,C.c_uint32,C.POINTER(C.c_uint8)];lib.run.restype=C.c_uint
        output=(C.c_uint8*128)()
        # 1P: left button, dx=-7,dy=+12. 2P disconnected.
        raw=0xff000000|((~0x41&255)<<16)|((~12&255)<<8)|(~0x87&255)
        count=lib.run(raw,0xffffffff,output);events=Parser().feed(bytes(output[:count]))
        assert [(e[0],e[2],e[3],e[4],e[5]) for e in events]==[(0,0,0,0,0),(1,1,1,-7,12),(2,2,0,0,0)],events
        lib.pico_bytes.argtypes=[C.POINTER(C.c_uint8)];lib.pico_bytes.restype=C.c_uint
        count=lib.pico_bytes(output);assert bytes(output[:count])==bytes([0xe2,1,249,12])
    print('PASS: actual legacy Nano mouse decode, unchanged Pico event bytes, optional CRC USB mirror, silent USB without handshake')

if __name__=='__main__':parser_and_state();worker();sketch()
