"""Select the source flat graphic underneath each U7CHUNKS placement."""

import struct

from .terrain import CHUNK_BYTES
from .u7 import flex_directory


def shape_frames(archive):
    """Positive counts are raw 8×8 frames, negative counts are RLE frames."""
    counts = []
    for offset, size in flex_directory(archive):
        if not size:
            counts.append(0)
            continue
        if size < 8:
            raise ValueError("Truncated SHAPES.VGA member")
        declared, directory = struct.unpack_from("<II",archive,offset)
        if declared == size or size%2 == 0 and declared == size-1:
            if not 8 <= directory < declared or directory%4:
                raise ValueError("Invalid SHAPES.VGA frame table")
            offsets = struct.unpack_from(f"<{directory//4-1}I",archive,offset+4)
            if any(a+8>b for a,b in zip(offsets,(*offsets[1:],declared))):
                raise ValueError("Invalid RLE frame span in SHAPES.VGA")
            counts.append(-len(offsets))
        else:
            if size%64:
                raise ValueError("Incomplete flat frame in SHAPES.VGA")
            counts.append(size//64)
    return counts


def chunk_underlays(words, frames):
    """Follow Exult's local-neighbor order and whole-chunk fallback for RLE shapes."""
    types = []
    for word in words:
        count = frames[word & 1023]
        frame = (word>>10) & 31
        types.append(0 if frame >= abs(count) else 1 if count>0 else -1)
    first_flat = next((i for i,t in enumerate(types) if t==1),None)
    donors = []
    for i,t in enumerate(types):
        if t != -1:
            donors.append(i if t==1 else None)
            continue
        x,y = i%16,i//16
        nearby = (16*ny+nx for ny in range(max(1,y-1),min(16,y+2))
                  for nx in range(max(0,x-1),min(16,x+2)))
        donor = next((j for j in nearby if types[j]==1 and (words[j]&0x7fff)!=12),first_flat)
        donors.append(donor)
    return donors


def substrate_chunks(chunks, frames):
    if len(chunks)%CHUNK_BYTES or len(frames)!=1024:
        raise ValueError("Unexpected source terrain dimensions")
    result = bytearray(len(chunks))
    for offset in range(0,len(chunks),CHUNK_BYTES):
        words = struct.unpack_from("<256H",chunks,offset)
        donors = chunk_underlays(words,frames)
        struct.pack_into("<256H",result,offset,*(0xffff if j is None else words[j] for j in donors))
    return result
