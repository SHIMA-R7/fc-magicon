"""Compile a MIDI into bounded 4-channel APU register snapshots.

Requires mido. Personal musical assets are kept outside the public sources.
No DMC/sample DMA. Two pulses, triangle bass, optional MIDI-channel-10 noise.
"""
import argparse,json,math
from pathlib import Path
import mido

REGS=(0x4000,0x4002,0x4003,0x4004,0x4006,0x4007,0x4008,0x400a,0x400b,0x400c,0x400e,0x400f)
RATE_NUM,RATE_DEN=60000,1001

def timer(note,triangle=False,bend=0):
    hz=440*2**((note-69+bend)/12)
    value=round(1789772.7272727273/((32 if triangle else 16)*hz)-1)
    return max(2 if triangle else 8,min(2047,value))

def compile_midi(mid,offset=0,scale=1):
    if mid.type==2:raise ValueError('Asynchronous type-2 MIDI is not supported')
    if scale<=0 or offset<0:raise ValueError('Positive time scale and nonnegative offset required')
    events=[];now=0
    for message in mid:
        now+=message.time
        if not message.is_meta:events.append((offset+now*scale,message))
    count=math.ceil((offset+now*scale+.1)*RATE_NUM/RATE_DEN)+1
    active={};pedal={};bends={};drum=None;serial=0;cursor=0
    previous=None;previous_keys=[None]*4;records=[];voice_frames=[0]*4
    for frame in range(count):
        at=(frame+.5)*RATE_DEN/RATE_NUM
        while cursor<len(events) and events[cursor][0]<=at:
            when,msg=events[cursor];cursor+=1
            ch=getattr(msg,'channel',0)
            if msg.type=='note_on' and msg.velocity:
                serial+=1
                if ch==9:drum=(when,msg.note,msg.velocity,serial)
                else:active[ch,msg.note]=(msg.velocity,when,serial,False)
            elif msg.type in ('note_off','note_on'):
                key=ch,msg.note
                if key in active:
                    if pedal.get(ch,False):active[key]=(*active[key][:3],True)
                    else:del active[key]
            elif msg.type=='control_change':
                if msg.control==64:
                    pedal[ch]=msg.value>=64
                    if not pedal[ch]:active={k:v for k,v in active.items() if k[0]!=ch or not v[3]}
                elif msg.control in (120,123):active={k:v for k,v in active.items() if k[0]!=ch}
            elif msg.type=='pitchwheel':bends[ch]=msg.pitch/8192*2
        notes=sorted(active,key=lambda k:(k[1],active[k][2]))
        bass=notes[0] if len(notes)>1 else None
        lead=notes[-1] if notes else None
        others=[n for n in notes if n not in (lead,bass)]
        selected=[lead,others[-1] if others else None,bass]
        values=[0xb0,0,0xf8,0xb0,0,0xf8,0x80,0,0xf8,0x30,4,0xf8]
        keys=[None]*4
        for voice,note in enumerate(selected):
            if note is None:continue
            velocity,start,identity,held=active[note];keys[voice]=identity;voice_frames[voice]+=1
            period=timer(note[1],voice==2,bends.get(note[0],0));base=voice*3
            if voice==2:values[base]=0xff
            else:
                decay=max(.45,math.exp(-max(0,at-start)*.8))
                volume=max(1,min(15,round(velocity/127*15*decay)))
                if voice==1:volume=max(1,round(volume*.7))
                values[base]=0xb0|volume
            values[base+1]=period&255;values[base+2]=0xf8|(period>>8)
        if drum and 0<=at-drum[0]<.1:
            age=at-drum[0];values[9]=0x30|max(1,round(drum[2]/127*15*(1-age/.1)))
            values[10]=12 if drum[1] in (35,36) else 3 if drum[1] in (42,44,46) else 6
            keys[3]=drum[3];voice_frames[3]+=1
        mask=0
        for i,value in enumerate(values):
            if previous is None or value!=previous[i]:mask|=1<<i
        for voice in range(4):
            if keys[voice] is not None and keys[voice]!=previous_keys[voice]:mask|=1<<(voice*3+2)
        records.append(bytes(values+[mask&255,mask>>8]));previous=values;previous_keys=keys
    # Always end with an explicit silence, including triangle linear counter.
    records.append(bytes([0xb0,0,0xf8,0xb0,0,0xf8,0x80,0,0xf8,0x30,4,0xf8,0xff,0x0f]))
    return records,dict(frames=len(records),rate_num=RATE_NUM,rate_den=RATE_DEN,duration=len(records)*RATE_DEN/RATE_NUM,voice_frames=voice_frames,notes_seen=serial)

def write_header(records,path,name='apu_score'):
    text='#pragma once\n#include <stdint.h>\n#define APU_SCORE_RATE_NUM 60000u\n#define APU_SCORE_RATE_DEN 1001u\n'
    text+=f'#define APU_SCORE_FRAMES {len(records)}u\nstatic const uint8_t {name}[APU_SCORE_FRAMES][14]={{\n'
    text+=''.join(' {'+','.join(f'0x{b:02x}' for b in r)+'},\n' for r in records)+'};\n'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)

def test_scale():
    mid=mido.MidiFile(ticks_per_beat=480);track=mido.MidiTrack();mid.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo',tempo=500000))
    for note in (72,74,76,77,79,81,83,84):
        for ch,n,vel in ((0,note,110),(1,67,75),(2,48,95),(9,42,90)):
            track.append(mido.Message('note_on',channel=ch,note=n,velocity=vel,time=0))
        for i,(ch,n) in enumerate(((0,note),(1,67),(2,48),(9,42))):
            track.append(mido.Message('note_off',channel=ch,note=n,velocity=0,time=480 if i==0 else 0))
    return mid

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('midi',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--offset',type=float,default=0);ap.add_argument('--time-scale',type=float,default=1)
    ap.add_argument('--test-scale',action='store_true');a=ap.parse_args()
    mid=test_scale() if a.test_scale else mido.MidiFile(a.midi)
    records,info=compile_midi(mid,a.offset,a.time_scale);write_header(records,a.output)
    info.update(source='synthetic scale - NOT INMU KING' if a.test_scale else str(a.midi),registers=[hex(v) for v in REGS],record_bytes=14)
    a.output.with_suffix('.json').write_text(json.dumps(info,indent=2));print(json.dumps(info,indent=2))

if __name__=='__main__':main()
