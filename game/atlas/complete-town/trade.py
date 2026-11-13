import struct
def vendor_records(binary,actors,record):
    shops={o['name']:o['source_position'] for o in actors if o['placed']}
    from u7uo.u7 import usecode_inventory
    functions={r['id']:r for r in usecode_inventory(binary)['records']}
    def lookup(values,func):
        r=functions[func];start=r['code_offset'];end=start+r['code_length']
        instructions=b''.join(b'\x1f'+struct.pack('<H',v) for v in reversed(values))
        at=binary.find(instructions,start,end)
        assert at>=0 and binary.find(instructions,at+1,end)<0,'Expected one copy of the original Usecode array'
        return [at+3*(len(values)-i-1) for i in range(len(values))]
    lists=[[0,594,659,599,600,602,590,474,597,722,723],[0,1004,572,574,575,569],[0,595,801,627,810,588,583]]
    for func,group in zip((0x872,0x873,0x874),lists):
        offsets=lookup(group,func)
        for s,off in zip(group[1:],offsets[1:]):
            record(s,0,*shops['Dell'],'Shop shape (frame unspecified)','USECODE',off,'Dell · wildcard frame; frame 0 illustrates the offer')
    group=[0,377,377,616,377,377,377,616,616];frames=[65177,8,0,0,13,31,4,5,3]
    offsets=lookup(group,0x842);fo=lookup(frames,0x842)
    for s,f,at,frameoff in list(zip(group,frames,offsets,fo))[1:]:
        record(s,f,*shops['Apollonia'],'Shop frame','USECODE',at,'Apollonia · frame operand at byte '+str(frameoff))


