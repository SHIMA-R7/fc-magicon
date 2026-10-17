"""Independent Nano USB SFC mouse reader; no game/desktop capture dependency."""
import binascii
import math
import struct
import threading
import time

MAGIC=b'FNM1'
QUERY=b'FCNM?\n'

def packet(kind,seq,port,buttons=0,dx=0,dy=0):
    b=struct.pack('<4sBBBBbb',MAGIC,kind,seq,port,buttons,dx,dy)
    return b+struct.pack('<H',binascii.crc_hqx(b,0xffff))

class Parser:
    def __init__(self):self.buffer=bytearray();self.bad=0
    def feed(self,data):
        self.buffer.extend(data)
        out=[]
        while True:
            i=self.buffer.find(MAGIC)
            if i<0:
                self.buffer[:]=self.buffer[-3:];break
            if i:del self.buffer[:i]
            if len(self.buffer)<12:break
            b=bytes(self.buffer[:12]);kind,seq,port,buttons,dx,dy=struct.unpack('<BBBBbb',b[4:10])
            valid=binascii.crc_hqx(b[:10],0xffff)==struct.unpack('<H',b[10:])[0]
            valid=valid and ((kind==0 and port==0 and buttons==dx==dy==0) or
                             (kind==1 and port in (1,2) and buttons<=3 and dx!=-128 and dy!=-128) or
                             (kind==2 and port in (1,2) and buttons==dx==dy==0))
            if not valid:del self.buffer[0];self.bad+=1;continue
            del self.buffer[:12];out.append((kind,seq,port,buttons,dx,dy))
        return out

class MouseState:
    def __init__(self,move,button,gain=6):
        if not math.isfinite(gain) or not 0<gain<=32:raise ValueError('Nano感度は0より大きく32以下')
        self.move,self.button,self.gain=move,button,gain
        self.buttons={1:0,2:0};self.seen={1:0.,2:0.};self.remainder={1:[0.,0.],2:[0.,0.]}
        self.last_sequence=None
    def aggregate(self):return self.buttons[1]|self.buttons[2]
    def set_buttons(self,port,value):
        old=self.aggregate();self.buttons[port]=value;new=self.aggregate()
        for bit,down,up in ((1,2,4),(2,8,16)):
            if (old^new)&bit:self.button(down if new&bit else up)
    def update(self,event,now):
        kind,seq,port,buttons,dx,dy=event
        if seq==self.last_sequence:return
        self.last_sequence=seq
        if kind==0:return
        self.seen[port]=now
        self.set_buttons(port,buttons)
        if kind==2:self.remainder[port]=[0.,0.];return
        rem=self.remainder[port];rem[0]+=dx*self.gain;rem[1]+=dy*self.gain
        x,y=int(rem[0]),int(rem[1]);rem[0]-=x;rem[1]-=y
        if x or y:self.move(x,y)
    def expire(self,now):
        for port in (1,2):
            if now-self.seen[port]>.5:
                self.set_buttons(port,0);self.remainder[port]=[0.,0.]
    def release(self):
        for port in (1,2):self.set_buttons(port,0)

class NanoMouse(threading.Thread):
    def __init__(self,port,move,button,gain=6,serial_factory=None):
        super().__init__(daemon=True)
        self.port=port;self.state=MouseState(move,button,gain)
        self.stop=threading.Event();self.ready=threading.Event();self.error=None
        self.serial_factory=serial_factory
    def run(self):
        transport=None
        try:
            factory=self.serial_factory
            if factory is None:
                import serial
                factory=serial.Serial
            transport=factory(self.port,115200,timeout=.01,write_timeout=.2)
            parser=Parser();deadline=time.monotonic()+6;next_query=0;last_rx=0;mouse_seen=set()
            while not self.stop.is_set():
                now=time.monotonic()
                if now>=next_query:
                    if transport.write(QUERY)!=len(QUERY):raise OSError('Nanoへの問い合わせ送信失敗')
                    next_query=now+1
                for event in parser.feed(transport.read(512)):
                    if not self.ready.is_set():
                        if event[0]!=0:continue
                        self.ready.set();print(f'Nanoマウス接続: {self.port} / 感度{self.state.gain:g}倍',flush=True)
                    last_rx=now
                    if event[0] in (1,2):
                        if event[0]==1 and event[2] not in mouse_seen:
                            mouse_seen.add(event[2]);print(f'SFCマウス検出: {event[2]}P',flush=True)
                        self.state.update(event,now)
                self.state.expire(now)
                if not self.ready.is_set() and now>=deadline:
                    raise OSError('Nano専用ファームの応答なし。COM選択とNanoへの書込みを確認')
                if self.ready.is_set() and now-last_rx>2:
                    raise OSError('Nanoからの通信が途切れた')
        except Exception as e:
            self.error=str(e);print('Nanoマウス停止: '+str(e),flush=True)
        finally:
            try:self.state.release()
            finally:
                if transport is not None:transport.close()
