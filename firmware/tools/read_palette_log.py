"""Read one completed palette report from USB CDC, without sending commands."""
import argparse,json,re,time
from pathlib import Path
from remote_pc import Port

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',default='COM11')
    ap.add_argument('--timeout',type=float,default=60)
    ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args();deadline=time.monotonic()+args.timeout
    port=None;buffer=bytearray();report=None;lines=[];nt_report=None;nt_line=None
    print('Waiting for completed palette diagnostic on '+args.port,flush=True)
    while time.monotonic()<deadline:
        if port is None:
            try:port=Port(args.port)
            except OSError:time.sleep(.25);continue
        buffer+=port.read()
        while b'\n' in buffer:
            raw,_,buffer=buffer.partition(b'\n');line=raw.decode('ascii',errors='replace').strip()
            match=re.fullmatch(r'NLOG valid=(\d+) offset=([0-9A-F]{4}) target=([0-9A-F]{2}) expected=([0-9A-F]{2}) actual=([0-9A-F]{2}) errors=(\d+)',line)
            if match:
                nt_report=dict(valid=bool(int(match[1])),offset=int(match[2],16),target=int(match[3],16),expected=int(match[4],16),actual=int(match[5],16),errors=int(match[6]));nt_line=line
                continue
            match=re.fullmatch(r'PLOG status=(\d+) frame=(\d+) palette_errors=(\d+)',line)
            if match:
                report=dict(status=int(match[1]),frame=int(match[2]),palette_errors=int(match[3]),entries={})
                if nt_report is not None:report['nt']=nt_report
                lines=([nt_line] if nt_line else [])+[line];continue
            match=re.fullmatch(r'P(\d{2}) target=([0-9A-F]{2}) expected=([0-9A-F]{2}) actual=([0-9A-F]{2})',line)
            if match and report is not None:
                index=int(match[1]);report['entries'][index]=dict(zip(('target','expected','actual'),(int(match[i],16) for i in (2,3,4))))
                lines.append(line)
                if set(report['entries'])==set(range(16)):
                    report['entries']=[dict(index=i,**report['entries'][i]) for i in range(16)]
                    args.output.parent.mkdir(parents=True,exist_ok=True)
                    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                    args.output.with_suffix('.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
                    print(json.dumps(report,indent=2),flush=True);return
        if len(buffer)>8192:buffer=buffer[-4096:]
        time.sleep(.02)
    raise TimeoutError('No complete palette report before timeout')

if __name__=='__main__':main()
