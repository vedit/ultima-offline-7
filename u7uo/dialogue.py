"""Generate resumable Lua functions from the original Iolo and Finnigan bytecode."""

import hashlib
import json
from pathlib import Path
import struct
import subprocess

from .u7 import STEAM_FORGE_USECODE, usecode_inventory
from .usecode import BRANCHES, ROOTS

# This original callback is referenced inside Iolo's scheduled action array,
# so it is absent from the ordinary Usecode call graph.
ENTRY_POINTS = {**ROOTS, "Iolo opening callback": 0x06AA, "moongate callback": 0x0618,
                "opening cursor callback": 0x061A, "opening interaction callback": 0x06FA,
                "stables investigation trigger": 0x06A4, "Johnson": 0x040E,
                "gate raise callback": 0x0607, "gate lower callback": 0x0609,
                "Spark": 0x0402, "Gilberto": 0x040D, "use key": 641, "locked chest": 522, "read scroll": 797}


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _quote(s):
    # Decimal Lua escapes are always 3 digits. Source text can contain any characters.
    return '"' + "".join(chr(b) if 32 <= b < 127 and b not in (34,92) else f"\\{b:03d}"
                         for b in s.encode("utf-8")) + '"'


def _integer(v, lo=0, hi=65535):
    if type(v) is not int or not lo <= v <= hi:
        raise ValueError("invalid integer in dialogue program")
    return v


def _extract(raw, ir, roots):
    records = usecode_inventory(raw)
    if records["sha256"] != ir["sha256"]:
        raise ValueError("Conversation input differs from the decoded Usecode")
    by_id = {f["id"]:f for f in ir["functions"]}
    recs = {r["id"]:r for r in records["records"]}
    queue, selected = list(roots), {}
    while queue:
        fid = queue.pop()
        if fid in selected:
            continue
        f, r = by_id[fid], recs[fid]
        start, size = r["code_offset"], r["code_length"]
        data = r["offset"] + 6
        if (f["code_offset"], f["code_length"], f["arguments"], f["locals"]) != (
                start,size,r["arguments"],r["locals"]):
            raise ValueError("Conversation function header differs from Usecode")
        ext = [v for v, in struct.iter_unpack("<H",raw[data+r["data_length"]+6:start])]
        if ext != f["externs"]:
            raise ValueError("Conversation extern table differs from Usecode")
        strings = {}
        for k, ref in f["strings_referenced"].items():
            offset = data + int(k)
            end = raw.find(b"\0",offset,data+r["data_length"])
            if end < offset or offset != ref["offset"] or _sha(raw[offset:end]) != ref["sha256"]:
                raise ValueError("Conversation string differs from Usecode")
            strings[int(k)] = raw[offset:end].decode("cp437")
        rows, decoded = [], f["instructions"]
        for i,(pc,op,args,_,_,_) in enumerate(decoded):
            end = decoded[i+1][0] if i+1 < len(decoded) else size
            source = raw[start+pc:start+end]
            if not source or source[0] != op:
                raise ValueError("Conversation opcode differs from Usecode")
            fields = {0x02:"HHHHh",0x04:"h",0x05:"h",0x06:"h",0x07:"Hh",0x1F:"h",
                      0x31:"Hh",0x38:"HB",0x39:"HB",0x44:"B"}.get(op,"H"*len(args))
            if len(source) != 1 + struct.calcsize("<"+fields) or list(struct.unpack_from("<"+fields,source,1)) != args:
                raise ValueError("Conversation operands differ from Usecode")
            # Branch reachability is recalculated below from these source operands.
            rows.append([pc,op,args,end + args[-1] if op in BRANCHES else None])
        pc_rows = {r[0]: i for i,r in enumerate(rows)}
        visited, todo = set(), [0]
        while todo:
            pc = todo.pop()
            if pc in visited:
                continue
            if pc not in pc_rows:
                raise ValueError("Conversation branch target outside instruction table")
            i = pc_rows[pc]
            visited.add(pc)
            _,op,args,branch = rows[i]
            if op in {0x24,0x47}:
                queue.append(ext[args[0]] if op == 0x24 else args[0])
            if branch is not None:
                todo.append(branch)
            if op not in {0x06,0x25,0x2C,0x2D,0x32,0x3F}:
                if i+1 == len(rows):
                    raise ValueError("Conversation falls through its final instruction")
                todo.append(rows[i+1][0])
        selected[fid] = {"id":fid,"base":start,"arguments":r["arguments"],"externs":ext,
                         "strings":strings,"code_sha256":_sha(raw[start:start+size]),
                         "rows":[row for row in rows if row[0] in visited]}
    return {"schema":1,"source_sha256":records["sha256"],"roots":sorted(roots),
            "functions":[selected[f] for f in sorted(selected)]}


_BINARY = {0x09:"add",0x0C:"mul",0x0E:"and",0x0F:"or",0x16:"gt",0x17:"lt",
           0x18:"ge",0x19:"le",0x1A:"not_equal",0x22:"eq",0x30:"in",0x4A:"append"}


def _lower(op, args, dest, ext, strings):
    a = args[0] if args else None
    if op in _BINARY:
        return f'binary(s,"{_BINARY[op]}")'
    if op in {0x1C,0x1D}:
        val = _quote(strings[a])
        return f'h.text=h.text..{val}' if op==0x1C else f'push(s,{val})'
    if op in {0x38,0x39}:
        return f'intrinsic(h,s,{a},{args[1]},{"true" if op==0x38 else "false"})'
    if op == 0x24:
        return f"invoke(h,{ext[a]},event,item,s)"
    if op == 2:
        params = ",".join(str(v) for v in args[:4])
        return f"do local more=loop(l,{params},first); first=false; if not more then goto pc_{dest} end end"
    return {
        0x04:f"if not ask(h) then goto pc_{dest} end", 0x05:f"if not truth(pop(s)) then goto pc_{dest} end",
        0x06:f"goto pc_{dest}", 0x07:f"if not matches(h,s,{a}) then goto pc_{dest} end",
        0x10:"push(s,truth(pop(s)) and 0 or 1)",0x12:f"l[{a}]=pop(s)",0x13:"push(s,1)",0x14:"push(s,0)",
        0x1E:f"construct(s,{a})",0x1F:f"push(s,{a})",0x21:f"push(s,l[{a}] or U)",
        0x25:"do return end",0x26:f"push(s,get(l[{a}] or U,number(pop(s))))",0x2C:"do return end",
        0x2D:"do return pop(s) end",0x2E:"first=true",
        0x2F:f'append_local(h,l[{a}] or U)',
        0x32:"do return 0 end",0x33:"say(h)",0x3E:"push(s,item)",0x3F:"error(abort,0)",
        0x40:"h.found=true",0x42:f'push(s,effect(h,"flag_read",{{{a}}},true))',
        0x43:f'effect(h,"flag_write",{{{a},number(pop(s))~=0 and 1 or 0}},false)',
        0x44:f"push(s,{a})",0x46:f"do local i=number(pop(s)); l[{a}]=put(l[{a}] or U,i,pop(s)) end",
        0x48:"push(s,event)",0x4B:"event=number(pop(s))",
    }.get(op)


_CAMPAIGN_OPERATIONS = """
local function call_item(h,id,event,stack,nargs)
  assert(nargs>0 and #stack>=nargs,"explicit item call missing operands")
  assert(#h.frames<64,"call depth limit")
  local item=number(stack[#stack])
  local locals={}
  for i=nargs-1,0,-1 do locals[i]=pop(stack) end
  local result=functions[id](h,locals,event,item)
  h.frames[#h.frames]=nil
  if result~=nil then push(stack,result) end
end
local function divide(s,remainder)
  local b=head(pop(s))
  local a=head(pop(s))
  assert(math.type(a)=="integer" and math.type(b)=="integer"
    and a>=-32768 and a<=32767 and b>=-32768 and b<=32767,"division outside signed integer profile")
  if b==0 then push(s,32767); return end
  assert(a~=-32768 or b~=-1,"DOS signed division overflow requires reference")
  local q=a//b
  if (a<0)~=(b<0) and a%b~=0 then q=q+1 end
  push(s,remainder and a-q*b or q)
end
"""


CURRENT_GENERATOR = 4

_WORD_ARITHMETIC = """
local function arithmetic(s,op)
  local right,left=head(s[#s]),head(s[#s-1])
  if math.type(left)=="integer" and math.type(right)=="integer"
      and left>=-32768 and left<=32767 and right>=-32768 and right<=32767 then
    pop(s); pop(s)
    local value
    if op=="add" then value=left+right
    elseif op=="sub" then value=left-right
    else value=left*right end
    push(s,((value+32768)%65536)-32768)
  elseif op=="sub" then
    right=number(pop(s)); left=number(pop(s))
    local value=left-right
    assert(value>=-32768 and value<=32767,"subtraction outside verified signed range")
    push(s,value)
  else binary(s,op) end
end
"""


def compile_dialogue(program, version=2):
    if program["schema"] != 1:
        raise ValueError("unsupported dialogue program")
    lines = [Path(__file__).with_name("dialogue_runtime.lua").read_text(encoding="utf-8")]
    if version >= 3:
        lines.append(_CAMPAIGN_OPERATIONS)
    if version >= 4:
        lines.append(_WORD_ARITHMETIC)
    declared_args = {f["id"]:f["arguments"] for f in program["functions"]}
    for root in program["roots"]:
        lines.append(f"roots[{_integer(root)}]=true")
    unsupported = []
    for f in program["functions"]:
        fid = _integer(f["id"])
        base = _integer(f["base"],0,2**32-1)
        ext = [_integer(v) for v in f["externs"]]
        strings = {int(k):v for k,v in f["strings"].items()}
        nargs = max(0,_integer(f["arguments"]) - int(fid < 0x800))
        lines.extend([f"arity[{fid}]={nargs}",f"functions[{fid}]=function(h,l,event,item)",
                      f"  local frame=enter(h,{fid},{base})","  local s,first={},false"])
        for pc,op,args,dest in f["rows"]:
            _integer(pc); _integer(op,0,255)
            operands = [_integer(v,-32768) for v in args]
            if dest is not None:
                _integer(dest)
            lowered = _lower(op,operands,dest,ext,strings)
            if op == 0x0A and version >= 2:
                lowered = ('do local right=number(pop(s)); local left=number(pop(s)); local value=left-right; '
                           'assert(value>=-32768 and value<=32767,"subtraction outside verified signed range"); '
                           'push(s,value) end')
            if version >= 3:
                if op == 0x47:
                    target = operands[0]
                    lowered = f"call_item(h,{target},event,s,{declared_args[target]})"
                elif op == 0x31:
                    lowered = f"if h.found then goto pc_{dest} end; h.found=true"
                elif op in (0x0B,0x0D):
                    lowered = "divide(s,true)" if op==0x0D else "divide(s,false)"
            if version >= 4 and op in (0x09,0x0A,0x0C):
                operation = {0x09:"add",0x0A:"sub",0x0C:"mul"}[op]
                lowered = f'arithmetic(s,"{operation}")'
            if lowered is None:
                unsupported.append({"function_id":fid,"pc":pc,"opcode":op,"source_offset":base+pc})
                lowered = f'error("unsupported opcode {op:02X}")'
            lines.extend([f"  ::pc_{pc}:: at(h,frame,{pc})","  "+lowered])
        lines.append("end")
    lines.append("return {start=start}\n")
    return "\n".join(lines), unsupported


def produce_dialogue(u7_root, release_dir):
    release_dir=Path(release_dir)
    raw=(Path(u7_root)/"STATIC/USECODE").read_bytes()
    ir=json.loads((release_dir/"usecode-ir.json").read_bytes())
    program=_extract(raw,ir,set(ENTRY_POINTS.values()))
    lua,unsupported=compile_dialogue(program,CURRENT_GENERATOR)
    metadata={"schema":1,"generator_version":CURRENT_GENERATOR,"source_sha256":program["source_sha256"],"lua_sha256":_sha(lua.encode()),
              "functions_compiled":len(program["functions"]),"roots":ENTRY_POINTS,
              "instructions":sum(len(f["rows"]) for f in program["functions"]),
              "diagnostics":unsupported,"program":program,"dos_runtime_parity":"not_run"}
    (release_dir/"dialogue.lua").write_bytes(lua.encode())
    (release_dir/"dialogue.json").write_bytes(_bytes(metadata))
    return {k:v for k,v in metadata.items() if k!="program"}


def _execute(lua, scenarios, interpreter_path):
    delimiter = "="
    while "]"+delimiter+"]" in lua:
        delimiter += "="
    env = ("{math={type=math.type},table={remove=table.remove},coroutine={create=coroutine.create,"
           "resume=coroutine.resume,yield=coroutine.yield},assert=assert,error=error,type=type,tostring=tostring,"
           "ipairs=ipairs,pairs=pairs}")
    # Only the recompiled source enters this limited environment. Generated literals cannot end the argument.
    driver = f"local mod=assert(load([{delimiter}[\n{lua}]{delimiter}], '@dialogue.lua', 't', {env}))()\n"+scenarios
    try:
        result = subprocess.run([str(Path(interpreter_path).resolve()),"-E","-"], input=driver.encode(),
                                capture_output=True, timeout=8)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Lua dialogue execution failed: {exc}") from exc
    if result.returncode:
        raise ValueError("Lua dialogue verification failed: "+result.stderr.decode(errors="replace")[-900:])
    return result.stdout.decode("utf-8").splitlines()


_SCENARIOS = """
local function emit(label,row)
  local pieces={}
  for i,s in ipairs(row.args) do
    pieces[i]=s:gsub(".",function(c) return string.format("%02x",c:byte()) end)
  end
  print(label,row.kind,row.pc,table.concat(pieces,","))
end
for _,which in ipairs({1,2}) do
  local session=mod.start(0x40C,1,-12)
  local e=session:resume()
  assert(e.status=="effect" and e.kind=="intrinsic" and e.intrinsic==3 and e.pc==14)
  assert(e.args[1]==-12 and e.args[2]==0 and not e.expects_value)
  local facts={[0x5A]=0,[0x22]=-356,[0x27]="Reader",[0x1B]=-2,[0x2F]=0,[0x88]=0}
  local flags={[90]=1,[72]=0,[60]=1}
  for i=1,64 do
    local reply
    if e.status=="completed" then
      assert(which==2 and e.termination=="abort" and e.pc==0xCD)
      print(which,"complete",e.pc); break
    end
    assert(e.status=="effect" and e.sequence==i and #e.call_stack>0,e.reason or "missing effect")
    if e.kind=="flag_read" then
      reply=flags[e.args[1]]; assert(reply~=nil,"unexpected flag read")
    elseif e.kind=="flag_write" then
      assert(which==1 and e.function_id==0x40C and e.pc==0x93 and e.args[1]==72 and e.args[2]==1)
      print(which,"write",e.pc); break
    elseif e.kind=="say" then emit(which,e)
    elseif e.kind=="choice" then
      emit(which,e)
      if e.function_id==0x90A then assert(e.pc==17 and #e.args==2); reply=e.args[which]
      else assert(e.function_id==0x90B and e.pc==11 and #e.args==4); reply=e.args[4] end
    elseif e.kind=="intrinsic" and e.expects_value then
      reply=facts[e.intrinsic]; assert(reply~=nil,"unexpected fixture intrinsic")
    else assert(e.kind=="intrinsic" and e.intrinsic==3) end
    e=session:resume(reply)
  end
end
local s=mod.start(0x401,1,-1)
local e=s:resume()
assert(e.kind=="flag_write" and e.pc==1 and e.args[1]==20 and e.args[2]==1)
e=s:resume()
assert(e.kind=="intrinsic" and e.intrinsic==0x22 and e.function_id==0x908 and e.pc==0)
assert(#e.call_stack==2 and e.call_stack[1].function_id==0x401 and e.call_stack[1].pc==4)
print("3","frontier",e.function_id)
"""


def _expected_transcript(program):
    # Kitrinx's independent original listings identify these PUSH_DATA / APPEND_DATA
    # source PCs. The literal references and order give a fixture independent of Lua.
    funcs={f["id"]:f for f in program["functions"]}
    def payload(fid,*pcs):
        f=funcs[fid]
        by_pc={r[0]:r for r in f["rows"]}
        strings={int(k):v.encode() for k,v in f["strings"].items()}
        texts=[strings[by_pc[pc][2][0]] for pc in pcs]
        return _sha(b"".join(struct.pack("<I",len(p))+p for p in texts))
    first=payload(0x40C,0x3C)
    yes_no=payload(0x90A,0x07,0x04)
    findings=payload(0x40C,0x54,0x51,0x4E,0x66)
    return [
        [1,"say",0x3F,first],[1,"choice",0x11,yes_no],[1,"say",0x49,payload(0x40C,0x46)],
        [1,"choice",0x0B,findings],[1,"say",0x8A,payload(0x40C,0x87)],[1,"write",0x93],
        [2,"say",0x3F,first],[2,"choice",0x11,yes_no],[2,"say",0xCC,payload(0x40C,0xC9)],
        [2,"complete",0xCD],[3,"frontier",0x908]]


def _source_pages(text):
    """Exult's show-message and click boundaries in usecode/ucinternal.cc::say_string."""
    while text:
        if text.startswith("*"):
            yield ""
            text=text[1:]
        else:
            page,marker,text=text.partition("~")
            yield page
            if marker and text.startswith("~"):
                text=text[1:]


def _opening_vectors(lua,program,seed,interpreter_path):
    flags=seed["flags"]
    if (seed["seed_sha256"]!="c1299e499aa1cd7c6bb9d7f14044ec21dc1f98aa45eaac1f6f1a2c473223491a"
            or any(type(v) is not int or v not in (0,1) for v in flags)
            or _sha(bytes(flags))!="e17146298e7af025818823819155452e21446deb89b8bc68ceab954b8c3138c1"):
        raise ValueError("No opening dialogue reference for this flaginit")
    actor_rows={n:seed["actors"][str(n)] for n in (1,2,11,12)}
    def literal(fid,pc):
        f=next(f for f in program["functions"] if f["id"]==fid)
        row=next(r for r in f["rows"] if r[0]==pc)
        return {int(k):s for k,s in f["strings"].items()}[row[2][0]]
    def say(expected,pc,*content):
        for page in _source_pages("".join(content)):
            expected.append(["say",pc,_sha(page.encode())])
    cases=[]
    # Both fixture viewports contain Finnigan and Petre. Only the second contains Iolo.
    for left,answer in [(1029,1),(1030,2)]:
        box=[left,2203,left+39,2227]
        observed={}
        for n,row in actor_rows.items():
            x,y,_=row["source_position"]
            observed[n]=[int(left<=x<=box[2] and box[1]<=y<=box[3] and row["can_act"]),
                         int(row["item_flags"]["0"])]
        npc="{"+",".join(f"[{-n}]={{{near},{flag}}}" for n,(near,flag) in observed.items())+"}"
        header=f"local flags={{{','.join(map(str,flags))}}}; local npc={npc}; local answer={answer}\n"
        lines=_execute(lua,header+_OPENING_DRIVER,interpreter_path)
        events=[]
        for line in lines:
            cols=line.split("\t")
            if cols[0]=="say":
                events.append(["say",int(cols[1]),_sha(bytes.fromhex(cols[2]))])
            elif cols[0]=="choice":
                events.append(["choice",int(cols[1]),*[_sha(bytes.fromhex(c)) for c in cols[2:]]])
            else:
                events.append([cols[0],*[int(c) for c in cols[1:]]])
        expected=[["face",0x0E,-12,0],["halt_requested",0x127,-12],["schedule_requested",0x135,-12,11]]
        def line(pc,literal_pc):
            say(expected,pc,literal(0x40C,literal_pc))
        line(0x13C,0x139)
        expected.append(["flag_write",0x13E,76,1])
        if observed[1][0] and not observed[1][1]:
            line(0x153,0x150); expected.append(["face",0x15A,-1,0])
            say(expected,0x167,literal(0x40C,0x15E),"Reader",literal(0x40C,0x164))
            line(0x178,0x175); expected.append(["face",0x17F,-12,0])
            line(0x186,0x183); expected.append(["face",0x18D,-1,0])
            line(0x194,0x191)
            expected.extend([["remove",0x198,-1],["face",0x1A2,-12,0]])
        else:
            line(0x1AC,0x1A9)
        for text_pc in [0x1AD,0x1B1,0x1B5,0x1B9]:
            line(text_pc+3,text_pc)
        expected.append(["choice",0x11,*[_sha(literal(0x90A,pc).encode()) for pc in (7,4)]])
        if answer==1:
            if observed[11][0] and not observed[11][1]:
                line(0x1DB,0x1D8)
            else:
                expected.append(["face",0x1FA,-12,0]); line(0x201,0x1FE)
        else:
            line(0x219,0x216)
            expected.extend([["flag_write",0x21B,89,1],["abort",0x21E]])
        if events!=expected:
            raise ValueError(f"Opening dialogue differs from original PC sequence in viewport {box}, answer {answer}")
        cases.append({"viewport_inclusive":box,"npc_nearby_replies":{str(-n):v[0] for n,v in observed.items()},
                      "answer_one_based":answer,"events":events})
    return {"status":"passed","cases":cases,"flaginit_sha256":_sha(bytes(flags)),
            "original_flags_read":{str(i):flags[i] for i in [90,72,89,76]},
            "source_seed_sha256":seed["seed_sha256"],"player_fixture":{"name":"Reader","female":0},
            "first_choice":{"function_id":0x90A,"pc":0x11,"called_from":{"function_id":0x40C,"pc":0x1BD}},
            "scope":"Seeded source flags and NPCs. Viewports and player identity are explicit fixtures. "
                    "Schedule and face requests are acknowledged by the test host."}


_OPENING_DRIVER = """
local function hex(s) return (s:gsub(".",function(c) return string.format("%02x",c:byte()) end)) end
local session=mod.start(0x40C,1,-12)
local e=session:resume()
local chosen=false
for i=1,120 do
  if e.status=="completed" then
    assert(chosen and answer==2 and e.termination=="abort")
    print("abort",e.pc); break
  end
  assert(e.status=="effect" and e.sequence==i,e.reason or "invalid effect")
  local r
  if e.kind=="flag_read" then r=flags[e.args[1]+1]; assert(r~=nil)
  elseif e.kind=="flag_write" then
    print("flag_write",e.pc,e.args[1],e.args[2]);flags[e.args[1]+1]=e.args[2]
  elseif e.kind=="say" then
    print("say",e.pc,hex(e.args[1]))
    if chosen and answer==1 then break end
  elseif e.kind=="choice" then
    assert(not chosen and #e.args==2 and e.function_id==0x90A and e.pc==0x11)
    assert(#e.call_stack==2 and e.call_stack[1].function_id==0x40C and e.call_stack[1].pc==0x1BD)
    print("choice",e.pc,hex(e.args[1]),hex(e.args[2]))
    chosen=true;r=e.args[answer]
  else
    assert(e.kind=="intrinsic")
    local id=e.intrinsic;local a=e.args
    if id==0x03 then print("face",e.pc,a[1],a[2])
    elseif id==0x04 then print("remove",e.pc,a[1])
    elseif id==0x5A then r=0
    elseif id==0x22 then r=-356
    elseif id==0x27 then assert(a[1]==-356);r="Reader"
    elseif id==0x1B then assert(npc[a[1]]);r=a[1]
    elseif id==0x2F then r=npc[a[1]][1]
    elseif id==0x88 then assert(a[2]==0);r=npc[a[1]][2]
    elseif id==0x5C then print("halt_requested",e.pc,a[1])
    elseif id==0x1D then print("schedule_requested",e.pc,a[1],a[2])
    else error("unexpected opening intrinsic "..id) end
  end
  e=session:resume(r)
end
assert(chosen,"first source menu not reached")
"""


def verify_dialogue(release_dir, interpreter_path):
    release_dir=Path(release_dir)
    info=json.loads((release_dir/"dialogue.json").read_bytes())
    program=info["program"]
    lua,issues=compile_dialogue(program, info.get("generator_version", 1))
    if ((release_dir/"dialogue.lua").read_bytes()!=lua.encode() or _sha(lua.encode())!=info["lua_sha256"]
            or issues!=info["diagnostics"] or info["source_sha256"]!=program["source_sha256"]):
        raise ValueError("Dialogue artifacts differ from recompilation")
    if (info["source_sha256"]!=STEAM_FORGE_USECODE or
            _sha(_bytes(program)) not in {"b94b869a2cb793da18c4dc9e003dcbd8fd9132e027521476441499a87b1204b9",
                                          "1f27911b9ed147f8c27884c9756d7ca894b482e2c3554e22f1388840960c17e2",
                                          "d83ddb6d3dd1f0f4201fcdd34d001a1f222d41c51c77182c1beff3b6c5e21f46",
                                          "0028ada899babcfc7431d0a3205c46cd86635cdd9d9a88440372c151e5c40dc6",
                                          "12793568847e28f2156a9670da8975f90ddcb89b824fdd0d9dff4b26c4cc456e",
                                          "a6d198c52e322a991faa9f786b19b5b6ded6ce1822ce74b00f9f3e428ad673d1",
                                          "a80c22d7e9454f2e0222b0cefe3c9105ff9ae76e1de848fa11316dc2a61a14e2",
                                          "fe447a7fc751c94f74ce6d946583059caa6acdc0953924ad067106a0f8d219a1",
                                          "e3ff5b841c8fbef8b857bcfd2067cccaca7c809b7c7d6c96c807ec0ade644031"}):
        raise ValueError("No registered conversation vectors matching this exact input and source program")
    transcript=[]
    for line in _execute(lua,_SCENARIOS,interpreter_path):
        row=line.split("\t")
        if len(row)==4 and row[1] in {"say","choice"}:
            # Source strings remain private. Qualification records compare ordered, length-delimited payloads.
            payloads=[bytes.fromhex(v) for v in row[3].split(",")]
            digest=_sha(b"".join(struct.pack("<I",len(p))+p for p in payloads))
            transcript.append([int(row[0]),row[1],int(row[2]),digest])
        elif len(row)==3 and row[1] in {"write","complete","frontier"}:
            transcript.append([int(row[0]),row[1],int(row[2])])
        else:
            raise ValueError("Unexpected Lua qualification output")
    if transcript!=_expected_transcript(program):
        raise ValueError("Dialogue transcript differs from the source branch and menu references")
    seed_path=release_dir/"story-seed.json"
    opening=_opening_vectors(lua,program,json.loads(seed_path.read_bytes()),interpreter_path) if seed_path.is_file() else None
    stables = 0x06A4 in program["roots"]
    if stables:
        _execute(lua, """
for _,event in ipairs({1,2,3}) do
  local vm=mod.start(0x06A4,event,1048600)
  local e=vm:resume()
  if event==3 then
    assert(e.status=="effect" and e.kind=="flag_write" and e.pc==9 and e.source_offset==1243607)
    assert(e.args[1]==60 and e.args[2]==1)
    e=vm:resume()
  end
  assert(e.status=="completed" and e.termination=="return")
end
""", interpreter_path)
    gate = 0x0607 in program["roots"] and 0x0609 in program["roots"]
    if gate:
        _execute(lua, """
for _,case in ipairs({{0x607,0,1},{0x607,3,4},{0x609,4,3},{0x609,1,0}}) do
  local vm=mod.start(case[1],2,0x300123)
  local e=vm:resume()
  assert(e.status=="effect" and e.intrinsic==0x42 and e.args[1]==0x300123 and e.expects_value)
  e=vm:resume(case[2])
  assert(e.status=="effect" and e.intrinsic==0x43 and e.args[1]==0x300123 and e.args[2]==case[3])
  assert(vm:resume().status=="completed")
end
""", interpreter_path)
    estate = 641 in program["roots"] and 522 in program["roots"]
    if estate:
        _execute(lua, """
for _,test in ipairs({{522,253,800,1},{522,252,522,0},{800,253,522,0}}) do
  local shape,keyQuality,chestQuality=test[1],253,test[2]
  local s=mod.start(641,1,101)
  local e=s:resume()
  local writes,cursors=0,0
  for step=1,32 do
    if e.status=="completed" then break end
    assert(e.status=="effect")
    local i=e.intrinsic
    local a=e.args[1]
    if type(a)=="table" then a=a[1] end
    local result
    if i==0x33 then cursors=cursors+1;result={102,972,2132,6}
    elseif i==0x86 then assert(a==27 and e.args[2]==101)
    elseif i==0x11 then assert(a==102);result=shape
    elseif i==0x14 then assert(a==101 or a==102);result=a==101 and keyQuality or chestQuality
    elseif i==0x40 or i==0x80 then assert(a==102)
    elseif i==0x0d then assert(a==102);shape=e.args[2]
    elseif i==0x2a then assert(a==102 and e.args[2]==641 and e.args[3]==253);result={}
    else assert(e.kind=="flag_write" and e.pc==0x93 and a==62 and e.args[2]==1);writes=writes+1 end
    e=s:resume(result)
  end
  assert(e.status=="completed" and cursors==1 and shape==test[3] and writes==test[4])
end
""",interpreter_path)
    return {"status":"passed","scenarios_passed":3+(len(opening["cases"]) if opening else 0)+(3 if stables else 0)+(4 if gate else 0)+(3 if estate else 0),
            "estate_key_vectors":["matching unlock","wrong quality","relock with key outside"] if estate else [],
            "gate_lift_vectors": [[0,1],[3,4],[4,3],[1,0]] if gate else [],
            "stables_event_vectors": [1,2,3] if stables else [], "source_sha256":info["source_sha256"],
            "interpreter_sha256":_sha(Path(interpreter_path).read_bytes()),"transcript":transcript,
            "fixture_inputs":{"flags":{"90":1,"72":0,"60":1},"female":0,"spark_nearby":0,"spark_flag_0":0,
                              "avatar_reference":-356,"spark_reference":-2,"avatar_name":"Reader"},
            "scenarios":["Finnigan acceptance through flag 72 write request","Finnigan refusal through source abort",
                         "Iolo event 1 through first helper request"],
            "seeded_opening":opening,"fresh_campaign_state_used":bool(opening),"dos_runtime_parity":"not_run"}
