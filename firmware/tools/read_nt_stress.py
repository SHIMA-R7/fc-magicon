"""Collect the completed FC-local NT stress diagnostic without sending commands."""
import argparse,json,re,time
from pathlib import Path
from remote_pc import Port

def decode(raw):
    u16=lambda i:raw[i]|raw[i+1]<<8
    result=dict(sequence=raw[0],pattern=raw[1],bank=raw[2],repeat=raw[3],errors=u16(4),
        first_offset=u16(6),first_expected=raw[8],first_actual=raw[9],xor_mask=raw[10],
        pattern_byte=raw[11],bit_errors=[u16(12+2*i) for i in range(8)],
        ppu_base=raw[29]<<8,signature=raw[30])
    if raw[30]==0xc5:
        result.update(cpu_window=True,cpu_errors=raw[28]|raw[31]<<8,cpu_xor_mask=raw[11])
        del result['pattern_byte']
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',default='COM11');p.add_argument('--timeout',type=float,default=180)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    deadline=time.monotonic()+a.timeout;port=None;buffer=bytearray();report=None;lines=[];gpio=None;gpio_line=None
    print('Waiting for NT stress report on '+a.port,flush=True)
    while time.monotonic()<deadline:
        if port is None:
            try:port=Port(a.port)
            except OSError:time.sleep(.25);continue
        buffer+=port.read()
        while b'\n' in buffer:
            raw,_,buffer=buffer.partition(b'\n');line=raw.decode('ascii',errors='replace').strip()
            m=re.fullmatch(r'GLOG samples=(\d+) high=([0-9A-F]{12}) low=([0-9A-F]{12}) changed=([0-9A-F]{12})',line)
            if m:
                gpio=dict(samples=int(m[1]),high=int(m[2],16),low=int(m[3],16),changed=int(m[4],16))
                gpio['pins']=[dict(gpio=i,seen_high=bool(gpio['high']&(1<<i)),seen_low=bool(gpio['low']&(1<<i)),changed=bool(gpio['changed']&(1<<i))) for i in range(47) if i!=39]
                gpio_line=line;continue
            m=re.fullmatch(r'SLOG status=(\d+) reports=(\d+) complete=(\d+) protocol_errors=(\d+)',line)
            if m:
                report=dict(zip(('status','count','complete','protocol_errors'),map(int,m.groups())))
                report['entries']={};lines=([gpio_line] if gpio_line else [])+[line]
                if gpio is not None:report['gpio']=gpio
                if report['count']:continue
            else:
                m=re.fullmatch(r'S(\d{2}) ([0-9A-F]{64})',line)
                if not m or report is None:continue
                report['entries'][int(m[1])]=decode(bytes.fromhex(m[2]));lines.append(line)
            if set(report['entries'])==set(range(report['count'])):
                report['entries']=[report['entries'][i] for i in range(report['count'])]
                report['total_errors']=sum(r['errors'] for r in report['entries'])
                if any(r.get('cpu_window') for r in report['entries']):
                    report['cpu_errors']=sum(r.get('cpu_errors',0) for r in report['entries'])
                report['bit_errors']=[sum(r['bit_errors'][i] for r in report['entries']) for i in range(8)]
                a.output.parent.mkdir(parents=True,exist_ok=True)
                a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                a.output.with_suffix('.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
                print(json.dumps({k:v for k,v in report.items() if k!='entries'},indent=2),flush=True);return
        if len(buffer)>8192:buffer=buffer[-4096:]
        time.sleep(.02)
    raise TimeoutError('No completed NT stress report')

if __name__=='__main__':main()
