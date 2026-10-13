"""Instruction-level control-flow tests; not an electrical timing simulator."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def run(path, levels, reply_at=None, reply=0x8000ff55, steps=200, base=0, jmp_pin=25, data_out=None, rx_capacity=None, rx_drain_at=(), stats=None):
    code, labels, wrap, end = [], {}, 0, None
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.split(';')[0].strip()
        if line.startswith('%'): break
        if line == '.wrap_target': wrap = len(code); continue
        if line == '.wrap': end = len(code)-1; continue
        if not line or line.startswith('.'): continue
        if line.endswith(':'): labels[line[:-1]] = len(code); continue
        code.append(line.replace(',', '').split())
    pc=0; regs=dict(x=0,y=0,isr=0,osr=0); driven=[]; pushes=[]; values=[]; consumed=0; delay=0
    arrivals=reply_at if isinstance(reply_at,list) else ([] if reply_at is None else [reply_at])
    occupancy=0; drains=set(rx_drain_at)
    if stats is None: stats={}
    stats.update(rx_stall_ticks=0, rx_dropped=0, rx_max_depth=0)
    for tick in range(steps):
        if tick in drains and occupancy: occupancy-=1
        if delay: delay-=1; continue
        pins=levels(tick); ins=code[pc]; op=ins[0]; next_pc=pc+1
        def val(name):
            if name.startswith('~') or name.startswith('!'): return (~val(name[1:]))&0xffffffff
            return 0 if name=='null' else ((pins>>base) if name=='pins' else regs[name])
        if op=='wait':
            pin=int(ins[3]) + (base if ins[2]=='pin' else 0)
            if ((pins>>pin)&1)!=int(ins[1]): next_pc=pc
        elif op=='nop': delay=int(ins[1].strip('[]')) if len(ins)>1 else 0
        elif op=='mov':
            if ins[1]=='exec':
                encoded=val(ins[2])&0xffff
                assert encoded&0xffe0==0x6060, hex(encoded) # OUT NULL only
                regs['osr']>>=(encoded&31) or 32
                delay=1 # injected instruction takes an additional cycle
            else: regs[ins[1]]=val(ins[2])
        elif op=='set': regs[ins[1]]=int(ins[2])
        elif op=='in':
            n=int(ins[2]);regs['isr']=((regs['isr']<<n)|(val(ins[1])&((1<<n)-1)))&0xffffffff
        elif op=='out':
            n=int(ins[2]); v=regs['osr']&((1<<n)-1);regs['osr']>>=n
            if ins[1]=='pindirs':
                if v: driven.append((tick,v))
            elif ins[1] in regs: regs[ins[1]]=v
            elif ins[1]=='pins' and data_out is not None: data_out.append((tick,v))
        elif op=='pull':
            if consumed<len(arrivals) and tick>=arrivals[consumed]:
                regs['osr']=reply[consumed] if isinstance(reply,list) else reply;consumed+=1
            elif ins[1]=='block': next_pc=pc
            else: regs['osr']=regs['x']
        elif op=='push':
            if rx_capacity is not None and occupancy>=rx_capacity:
                if 'noblock' in ins:
                    stats['rx_dropped']+=1; regs['isr']=0
                else:
                    stats['rx_stall_ticks']+=1; next_pc=pc
            else:
                pushes.append(tick); values.append(regs['isr']); regs['isr']=0
                occupancy+=1
                stats['rx_max_depth']=max(stats['rx_max_depth'],occupancy)
        elif op=='irq': pass
        elif op=='jmp':
            cond=True
            if len(ins)==3:
                c=ins[1]
                if c=='pin':cond=bool(pins&(1<<jmp_pin))
                elif c.startswith('!'):cond=not regs[c[1:]]
                elif c.endswith('--'):
                    name=c[:-2];cond=regs[name]!=0;regs[name]=(regs[name]-1)&0xffffffff
                else: raise AssertionError(c)
            if cond:next_pc=labels[ins[-1]]
        else:raise AssertionError(ins)
        if next_pc==end+1 and pc==end:next_pc=wrap
        pc=next_pc
    return driven,pushes,pc==labels.get('halt'),values

def main():
    cpu=ROOT/'magicon/cpu_m2.pio';ppu=ROOT/'chr_test/ppu_chr.pio'
    high=lambda t:(1<<24)|((1<<25) if 5<=t<80 else 0)
    assert run(cpu,high,reply_at=100)[0]==[]
    assert run(cpu,high,reply_at=10)[0]
    assert run(cpu,high,reply_at=10,reply=0x80010000)[0]==[]
    two=lambda t:(1<<24)|((1<<25) if 5<=t<80 or 140<=t<220 else 0)
    recovered=run(cpu,two,reply_at=[100,155],steps=260)
    assert recovered[0] and all(t>=140 for t,v in recovered[0])
    def wr(t):
        data=0x10 if t<70 else (0x5a if t<85 else 0xa5)
        return ((1<<25) if 5<=t<80 else 0)|data
    delayed=run(cpu,wr,reply_at=110,reply=0x80010000,steps=160)
    assert not delayed[0] and len(delayed[3])==2
    assert delayed[3][1]&255==0x5a and delayed[1][1]<110
    assert not (delayed[3][0]&(1<<24))
    timely=run(cpu,wr,reply_at=40,reply=0x80010000,steps=160)
    assert timely[3]==delayed[3]  # acknowledgement delay cannot change captured data
    def wr_then_rd(t):
        if t<120:return wr(t)
        return (1<<24)|((1<<25) if 140<=t<220 else 0)
    mixed=run(cpu,wr_then_rd,reply_at=[110,180],reply=[0x80010000,0x8000ff99],steps=260)
    assert mixed[0] and all(t>=140 for t,v in mixed[0])
    assert len(mixed[3])==3 and mixed[3][1]&255==0x5a and mixed[3][2]&(1<<24)



    # /RD high initially, low during read, then high at end.
    rd=lambda t:(1<<40) if t<5 or t>=35 else 0
    assert run(ppu,rd,reply_at=100,base=26,jmp_pin=40)[0]==[]
    assert run(ppu,rd,reply_at=12,base=26,jmp_pin=40)[0]
    rd2=lambda t:(1<<40) if t<5 or 35<=t<50 or t>=100 else 0
    recovered=run(ppu,rd2,reply_at=[40,60],base=26,jmp_pin=40,steps=130)[0]
    assert recovered and all(t>=50 for t,v in recovered)

    irq=ROOT/'magicon/mmc3_a12.pio'
    def levels(t):return ((1<<25) if t%40<20 else 0)|((1<<38) if t>=140 else 0)
    assert len(run(irq,levels,base=25,jmp_pin=38,steps=190)[1])==1
    def brief(t):return ((1<<25) if t%40<20 else 0)|((1<<38) if t>=50 else 0)
    assert run(irq,brief,base=25,jmp_pin=38,steps=190)[1]==[]
    direct=ROOT/'magicon/ppu_constant.pio'
    rd=lambda t:(1<<40) if t<5 or t>=65 else 0
    rd2=lambda t:(1<<40) if t<5 or 65<=t<90 or t>=160 else 0
    assert run(direct,rd,base=26,jmp_pin=40)[0]
    assert all(v==255 for t,v in run(direct,rd,base=26,jmp_pin=40)[0])
    assert not run(direct,lambda t:rd(t)|(1<<42),base=26,jmp_pin=40)[0]
    for row in range(16):
        outputs=[]
        # AD0-2 change after read starts: use preceding address, not data.
        run(direct,lambda t:rd(t)|((row if t<5 else 15-row)<<26),base=26,jmp_pin=40,data_out=outputs)
        assert outputs and all(v==(15 if row&8 else 240) for t,v in outputs)
    outputs=[]
    run(direct,lambda t:rd(t)|((1<<42) if t<5 else 0),base=26,jmp_pin=40,data_out=outputs)
    assert not outputs
    assert not run(direct,lambda t:0 if 5<=t<10 else 1<<40,base=26,jmp_pin=40)[0]
    outputs=[]
    run(direct,lambda t:rd2(t)|((8<<26) if 65<=t<90 else 0),base=26,jmp_pin=40,data_out=outputs,steps=190)
    assert [v for t,v in outputs]==[240,15] # A3 changes across successive reads
    for edge in range(5,13):
        enable_times=[]
        for row in range(16):
            outputs=[]
            def shifted(t):
                return ((1<<40) if t<edge or t>=edge+46 else 0) | ((row if t<edge else 15-row)<<26)
            result=run(direct,shifted,base=26,jmp_pin=40,data_out=outputs)
            assert result[0]
            enable_times.append(result[0][0][0])
            assert outputs and all(v==(15 if row&8 else 240) for t,v in outputs)
        assert len(set(enable_times))==1 # no row-dependent response delay
    width=ROOT/'magicon/rd_width.pio'
    lookup=ROOT/'magicon/ppu_lookup.pio'
    for address in (0,1,7,8,255,256,4095,4096,8191):
        base_addr=0x20010000
        def lookup_pins(t):
            return ((1<<40) if t<8 or t>=65 else 0)|((address if t<8 else 8191-address)<<26)
        output=[]
        result=run(lookup,lookup_pins,reply_at=[0,35],reply=[base_addr>>15,0xff00|(255>>(address&7))],
            base=26,jmp_pin=40,data_out=output)
        assert result[3]==[base_addr+address*4],result[3]
        assert output and output[0][1]==(255>>(address&7))
    nt=run(lookup,lambda t:rd(t)|(1<<42),reply_at=[0,35],reply=[0x20010000>>15,0xffff],base=26,jmp_pin=40)
    assert nt[1] and not nt[0] # now prefetches but drains nametable answer without drive
    assert not run(lookup,rd,reply_at=[0,100],reply=[0x20010000>>15,0xffff],base=26,jmp_pin=40)[0]
    short=run(width,lambda t:0 if 5<=t<25 else 1<<40,base=40,jmp_pin=40,steps=50)[3][0]
    long=run(width,lambda t:0 if 5<=t<45 else 1<<40,base=40,jmp_pin=40,steps=70)[3][0]
    over=run(width,lambda t:0 if 5<=t<100 else 1<<40,base=40,jmp_pin=40,steps=120)[3][0]
    assert 0<=long<short<=31 and over==0xffffffff
    print('PASS: deadline handling, A12 qualification, passive RD-width monotonicity/overflow')

if __name__=='__main__':main()





