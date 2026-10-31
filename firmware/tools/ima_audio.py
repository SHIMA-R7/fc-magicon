"""FCPV2 independent IMA ADPCM blocks; matches standalone_video/ima_adpcm.h."""
import struct
import numpy as np

STEPS=(7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767)
ADJUST=(-1,-1,-1,-1,2,4,6,8)

def step(code,predictor,index):
    s=STEPS[index];delta=(s>>3)+((s>>2) if code&1 else 0)+((s>>1) if code&2 else 0)+(s if code&4 else 0)
    return max(-32768,min(32767,predictor+(-delta if code&8 else delta))),max(0,min(88,index+ADJUST[code&7]))

def encode(samples):
    samples=np.asarray(samples,dtype=np.int16)
    predictor=int(samples[0]) if len(samples) else 0;index=0;output=bytearray()
    for start in range(0,len(samples),256):
        output+=struct.pack('<hBB',predictor,index,0)
        codes=[]
        for k in range(256):
            value=int(samples[min(start+k,len(samples)-1)])
            delta=value-predictor;s=STEPS[index];code=8 if delta<0 else 0;delta=abs(delta)
            for mask,amount in ((4,s),(2,s>>1),(1,s>>2)):
                if delta>=amount:code|=mask;delta-=amount
            predictor,index=step(code,predictor,index);codes.append(code)
        output+=bytes(codes[k]|(codes[k+1]<<4) for k in range(0,256,2))
    return bytes(output)

def decode(data,count):
    if len(data)!=(count+255)//256*132:raise ValueError('ADPCM size mismatch')
    values=[]
    for at in range(0,len(data),132):
        predictor,index,reserved=struct.unpack_from('<hBB',data,at)
        if index>88 or reserved:raise ValueError('Invalid ADPCM block')
        for byte in data[at+4:at+132]:
            for code in (byte&15,byte>>4):
                predictor,index=step(code,predictor,index);values.append(predictor)
    return np.asarray(values[:count],dtype=np.int16)
