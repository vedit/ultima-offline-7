import struct
def rle(raw,frame):
    pos=struct.unpack_from('<I',raw,4+4*frame)[0]
    end=struct.unpack_from('<I',raw,8+4*frame)[0] if 8+4*frame<struct.unpack_from('<I',raw,4)[0] else len(raw)
    data=memoryview(raw)[pos:end]
    right,left,above,below=struct.unpack_from('<4h',data)
    w,h=left+right+1,above+below+1
    assert 0<w<=1024 and 0<h<=1024
    pixels=[None]*(w*h); cursor=8
    while True:
        tag,=struct.unpack_from('<H',data,cursor); cursor+=2
        if not tag:break
        x,y=struct.unpack_from('<2h',data,cursor);cursor+=4
        x+=left;y+=above;n=tag//2
        assert n and 0<=x<=w-n and 0<=y<h
        start=y*w+x
        if tag&1:
            run=[]
            while len(run)<n:
                enc=data[cursor];cursor+=1
                length=enc//2
                assert length and len(run)+length<=n
                if enc&1:
                    run.extend([data[cursor]]*length);cursor+=1
                else:run.extend(data[cursor:cursor+length]);cursor+=length
        else:run=list(data[cursor:cursor+n]);cursor+=n
        assert len(run)==n
        pixels[start:start+n]=run
    return w,h,pixels,pos,(left,above)

