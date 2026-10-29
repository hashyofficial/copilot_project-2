#!/usr/bin/env python3
"""Xiaomi flash_gen_crc_list.py-compatible streaming sparse CRC generator.

Ported from the user's *successful* MIUI Build 10, for the same Redmi Pad
MT6789 fastboot toolchain, adapted to verified HyperOS 1 stock raw super size.
Critical: verify it reproduces the original Xiaomi sparsecrclist before writing.
"""
import struct
import zlib
from pathlib import Path
RAW_BYTES=9126805504
MAXCRC=(256*1024*1024)-(28+2*12+4)
NREAD=8*1024*1024
def fail(msg): raise RuntimeError(msg)
def exact(f,n):
    b=f.read(n)
    if len(b)!=n:fail("Truncated file: expected "+str(n))
    return b
class Joined:
    def __init__(self,paths):self.paths=paths;self.index=0;self.handle=None
    def __enter__(self):return self
    def __exit__(self,*a):
        if self.handle:self.handle.close()
    def read(self,n=0):
        if n<0:fail("Unsupported unbounded input")
        b=bytearray()
        while len(b)<n and self.index<len(self.paths):
            if self.handle is None:self.handle=self.paths[self.index].open("rb")
            part=self.handle.read(n-len(b))
            if not part:
                self.handle.close();self.handle=None;self.index+=1
            else:b.extend(part)
        return bytes(b)
def sparse_crc(stream):
    """Streaming Python3 port of uploaded Xiaomi flash_gen_crc_list.py CRC splitting."""
    h=struct.unpack("<I4H4I",exact(stream,28))
    magic,major,minor,header,chunk_head,block_size,total_blocks,total_chunks,checksum=h
    if (magic,major,minor,header,chunk_head)!=(0xED26FF3A,1,0,28,12):fail("Unexpected Android sparse format")
    if block_size%512 or block_size*total_blocks!=RAW_BYTES:fail("Invalid super logical capacity")
    crcs=[0]*68;idx=0;backed=28;accounted=0
    for ci in range(total_chunks):
        typ,res,blocks,total=struct.unpack("<2H2I",exact(stream,12))
        remaining=total-12
        if typ==0xCAC1 and remaining!=blocks*block_size:fail("Invalid sparse RAW payload")
        if typ in (0xCAC2,0xCAC4) and remaining!=4:fail("Invalid sparse fill/checksum payload")
        if typ==0xCAC3 and remaining!=0:fail("Unexpected sparse DONT_CARE bytes")
        if typ not in (0xCAC1,0xCAC2,0xCAC3,0xCAC4):fail("Unknown sparse chunk")
        if typ!=0xCAC4:accounted+=blocks
        fill=exact(stream,4) if typ in (0xCAC2,0xCAC4) else None
        while True:
            backed_real=backed-12-4
            split=False;before=False;after=False
            if backed_real+remaining<=MAXCRC:
                piece=remaining;backed+=remaining+12
            elif backed_real>=(MAXCRC*7)//8 and remaining+12<=MAXCRC:
                piece=remaining;backed=remaining+12+28+12;before=True
            else:
                over=backed_real>=(MAXCRC*7)//8
                if over:backed_real=0
                piece=block_size*((MAXCRC-backed_real)//block_size)
                if typ!=0xCAC1 or not 0<piece<remaining:fail("Unrecognized Xiaomi CRC splitting")
                split=True;backed=(piece+12 if over else 28+12)
                before=over;after=not over
            if before:idx+=1
            if idx>=len(crcs):fail("Too many Xiaomi CRC segments")
            if typ==0xCAC1:
                remaining_piece=piece
                while remaining_piece:
                    raw=exact(stream,min(remaining_piece,NREAD))
                    crcs[idx]=zlib.crc32(raw,crcs[idx])
                    remaining_piece-=len(raw)
            elif typ==0xCAC2:
                if piece!=4:fail("Fill segment unexpectedly split")
                fb=fill*(block_size//4)
                repeat=blocks
                while repeat:
                    n=min(repeat,max(1,NREAD//block_size))
                    crcs[idx]=zlib.crc32(fb*n,crcs[idx])
                    repeat-=n
            if after:idx+=1
            remaining-=piece
            if not split:break
    if accounted!=total_blocks or stream.read(1):fail("Unexpected Android sparse image length")
    return crcs[:idx+1]
def crc_line(text,key):
    matches=[l for l in text.splitlines() if l.startswith(key+" ")]
    if len(matches)!=1:fail("Missing/duplicate checksum row: "+key)
    return matches[0]
def replace_crc(text,key,new):
    prev=crc_line(text,key)
    return text.replace(prev+"\n",new+"\n",1)
