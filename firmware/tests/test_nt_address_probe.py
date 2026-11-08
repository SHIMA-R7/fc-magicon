"""Run the exact passive PIO instructions on synthetic read/write strobes."""
from pathlib import Path
import tempfile
from test_pio_logic import run

source=Path(__file__).resolve().parents[1]/'standalone_video/address_probe.pio'
programs={}
current=None
for line in source.read_text().splitlines():
    if line.startswith('.program '):
        current=line.split()[1];programs[current]=[]
    if current:programs[current].append(line)
with tempfile.TemporaryDirectory() as d:
    for name,lines in programs.items():
        assert all(not l.strip().startswith(('out ','set ','side ')) for l in lines)
        pin=15 if 'write' in name else 14
        other=14 if pin==15 else 15
        path=Path(d)/'probe.pio';path.write_text('\n'.join(lines))
        def levels(t):
            page=min(t//30,3)
            phase=t%30
            v=(page<<8)|(1<<16)|(1<<other)
            if not 8<=phase<18:v|=1<<pin
            return v<<26
        driven,pushes,_,values=run(path,levels,steps=120,base=26)
        assert not driven and len(values)==4,(name,driven,pushes,values)
        assert [(v>>8)&3 for v in values]==[0,1,2,3],values
        assert all(v&(1<<16) for v in values)
        print('PASS:',name,'four page addresses captured; no outputs')
