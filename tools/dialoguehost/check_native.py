"""Exercise the built, bounded dialogue ABI with authored source and replies."""

import argparse
import ctypes
import json
import struct
from pathlib import Path


class Machine:
    def __init__(self, library, source, function=0x40C, event=1, item=-12):
        self.dll = ctypes.CDLL(str(library))
        ptr, size = ctypes.c_void_p, ctypes.c_int
        self.dll.u7_dialog_open.argtypes = [ptr, size, ptr, size, size, size, size, ptr, size]
        self.dll.u7_dialog_open.restype = ptr
        self.dll.u7_dialog_next.argtypes = [ptr, ptr, size, ptr, size]
        self.dll.u7_dialog_next.restype = size
        self.dll.u7_dialog_close.argtypes = [ptr]
        self.dll.u7_dialog_close.restype = None
        self.output = ctypes.create_string_buffer(65536)
        bridge = Path(__file__).with_name("bridge.lua").read_bytes()
        self.handle = self.dll.u7_dialog_open(source, len(source), bridge, len(bridge), function,
                                               event, item, self.output, len(self.output))
        if not self.handle:
            raise ValueError(self.output.value.decode())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.dll.u7_dialog_close(self.handle)

    def step(self, reply=None):
        if reply is None:
            raw = b"n"
        elif type(reply) is int:
            raw = b"i" + struct.pack("<q", reply)
        elif isinstance(reply, str):
            raw = b"s" + reply.encode()
        elif isinstance(reply,list) and all(type(i) is int for i in reply):
            raw = b"a" + struct.pack("<" + "q"*len(reply),*reply)
        else:
            raise TypeError("Unsupported reply type")
        length = self.dll.u7_dialog_next(self.handle, raw, len(raw), self.output, len(self.output))
        if length < 0:
            raise ValueError(self.output.value.decode())
        return json.loads(self.output.raw[:length])


FIXTURE = b'''
return {start=function(f,e,item)
  assert(f==0x40c and e==1 and item==-12)
  assert(io==nil and os==nil and require==nil and load==nil and debug==nil)
  local i=0
  return {resume=function(_,v)
    i=i+1
    if i==1 then assert(v==nil); return {status="effect",kind="choice",args={"a","b"}} end
    if i==2 then return {arg=v, args={}} end
    return {int=v,array={{1,2},"x"}}
  end}
end}
'''


def check(library):
    with Machine(library, FIXTURE) as vm:
        assert vm.step()["args"] == ["a", "b"]
        literal = 'quote" null\0 newline\n and Lua syntax: load(1) é'
        assert vm.step(literal) == {"arg": literal, "args": []}
        assert vm.step(-3) == {"int": -3, "array": [[1, 2], "x"]}
        assert vm.step([-356,-1])["int"] == [-356,-1]
        assert vm.step([])["int"] == []
    for body, expected in [
        (b"while true do end", "budget"),
        (b"coroutine.wrap(function() while true do end end)()", "budget"),
        (b"string.rep('x', 64*1024*1024)", "memory"),
    ]:
        with Machine(library, b"return {start=function() return {resume=function() "+body+b" end} end}") as vm:
            try:
                vm.step()
            except ValueError as ex:
                if expected not in str(ex).lower():
                    raise
            else:
                raise AssertionError("Unbounded dialogue execution")
    print("Native ABI passed source, escaping, reply, memory, coroutine and budget checks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    check(parser.parse_args().library)
