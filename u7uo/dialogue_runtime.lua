-- Shared Lua 5.4 runtime for generated DOS Black Gate conversation code.
local functions, arity, roots = {}, {}, {}
local U, abort = {}, {}
local function arr(v) return type(v) == "table" and v ~= U end
local function head(v) if arr(v) then return v[1] or 0 end return v end
local function number(v)
  v = head(v)
  if v == U then return 0 end
  assert(math.type(v) == "integer", "numeric coercion outside verified value profile")
  return v
end
local function truth(v)
  if arr(v) then return #v > 0 end
  return v ~= 0 and v ~= U
end
local function equal(a,b)
  if arr(a) and arr(b) then
    if #a ~= #b then return false end
    for i=1,#a do if not equal(a[i],b[i]) then return false end end
    return true
  end
  if (arr(a) and type(b)=="string") or (arr(b) and type(a)=="string") then return false end
  a,b = head(a),head(b)
  return (a == U and 0 or a) == (b == U and 0 or b)
end
local function copy(v)
  if v == U then return 0 end
  if not arr(v) then return v end
  local a = {}
  for i=1,#v do a[i] = copy(v[i]) end
  return a
end
local function push(stack,v) stack[#stack+1] = v end
local function pop(stack)
  local n = #stack
  assert(n > 0,"operand stack underflow")
  local v = stack[n]; stack[n] = nil
  return v
end
local function take(stack,n)
  local a = {}
  for i=1,n do a[i] = pop(stack) end
  return a
end
local function append(a,v)
  if arr(v) then for i=1,#v do push(a,v[i]) end else push(a,v) end
  assert(#a <= 4096,"array limit")
end
local function construct(stack,n)
  local a = {}
  for i=1,n do append(a,pop(stack)) end
  push(stack,a)
end
local function binary(s,op)
  local b = pop(s)
  local a = pop(s)
  local v
  if op == "eq" then v=equal(a,b)
  elseif op == "not_equal" then v=not equal(a,b)
  elseif op == "and" then v=truth(a) and truth(b)
  elseif op == "or" then v=truth(a) or truth(b)
  elseif op == "gt" then v=number(a)>number(b)
  elseif op == "lt" then v=number(a)<number(b)
  elseif op == "ge" then v=number(a)>=number(b)
  elseif op == "le" then v=number(a)<=number(b)
  elseif op == "append" then local list={}; append(list,a); append(list,b); v=list
  elseif op == "in" then
    v=false
    if arr(b) then for i=1,#b do if equal(head(a),b[i]) then v=true; break end end end
  elseif op == "add" and (a == U or b == U) then v=a == U and b or a
  elseif op == "add" and (type(a) == "string" or type(b) == "string") then
    assert(not arr(a) and not arr(b),"array/string addition outside profile")
    v=tostring(a)..tostring(b)
  elseif op == "add" or op == "mul" then
    assert(not arr(a) and not arr(b),"array arithmetic outside profile")
    v=op=="add" and number(a)+number(b) or number(a)*number(b)
    assert(v>=-2147483648 and v<=2147483647,"integer overflow")
  else error("unimplemented binary operation") end
  if type(v)=="boolean" then v=v and 1 or 0 end
  push(s,v)
end
local function get(v,i)
  if i<1 then return 0 end
  if arr(v) then return v[i] or 0 end
  return i==1 and v or 0
end
local function put(v,i,value)
  assert(i>=-32767 and i<=4096,"array index outside profile")
  if i<1 then return v end
  local a={}
  if arr(v) then for k=1,#v do a[k]=v[k] end else a[1]=v end
  for k=#a+1,i do a[k]=U end
  a[i]=value
  return a
end
local function loop(l,i,n,v,a,first)
  local list=l[a] or U
  if first and list==U then return false end
  local count=arr(list) and #list or 1
  local next_index=first and 0 or number(l[i] or U)
  if not first then assert(count==number(l[n] or U),"loop collection changed length") end
  l[n]=count
  if next_index>=count then return false end
  l[v]=arr(list) and list[next_index+1] or list
  l[i]=next_index+1
  return true
end
local function at(h,frame,pc)
  frame.pc=pc
  h.steps=h.steps+1
  assert(h.steps<=100000,"instruction budget exceeded")
end
local function effect(h,kind,args,expect,intrinsic)
  h.count=h.count+1
  assert(h.count<=4096,"effect budget exceeded")
  local frames={}
  for i,f in ipairs(h.frames) do
    frames[i]={function_id=f.id,pc=f.pc,source_offset=f.base+f.pc}
  end
  local f=frames[#frames]
  return coroutine.yield({status="effect",kind=kind,args=copy(args),expects_value=expect,
    intrinsic=intrinsic,function_id=f.function_id,pc=f.pc,source_offset=f.source_offset,
    call_stack=frames,sequence=h.count,steps=h.steps})
end
local function say(h)
  local text=h.text
  h.text=""
  local i=1
  while i<=#text do
    if text:sub(i,i)=="*" then effect(h,"say",{""},false); i=i+1
    else
      local e=text:find("~",i,true)
      effect(h,"say",{text:sub(i,e and e-1 or #text)},false)
      if not e then break end
      i=e+1
      if text:sub(i,i)=="~" then i=i+1 end
    end
  end
end
local function append_local(h,v)
  if type(v)=="string" then h.text=h.text..v
  elseif v==U or (arr(v) and #v==0) then return
  elseif arr(v) then h.text=h.text.."0"
  elseif number(v)>=0 then h.text=h.text..number(v) end
end
local function answers(h,v,add)
  if arr(v) then for i=1,#v do answers(h,v[i],add) end; return end
  if type(v)~="string" then return end
  for i=1,#h.answers do
    if h.answers[i]==v then table.remove(h.answers,i); break end
  end
  if add then push(h.answers,v) end
end
local function choose(h,intrinsic)
  if #h.answers==0 then return nil end
  local r=effect(h,"choice",h.answers,true,intrinsic)
  for i,s in ipairs(h.answers) do if s==r then return r,i end end
  error("reply outside active choices")
end
local function ask(h)
  h.found=false
  h.choice=choose(h)
  return h.choice~=nil
end
local function matches(h,s,n)
  local matched=false
  for i=1,n do
    local option=pop(s)
    if not h.found and h.choice==option then matched=true; h.found=true end
  end
  return matched
end
local function intrinsic(h,s,id,n,keep)
  local args=take(s,n)
  local result=0
  if id==5 or id==6 then answers(h,args[1],id==5)
  elseif id==7 then push(h.answer_stack,h.answers); h.answers={}
  elseif id==8 then if #h.answer_stack>0 then h.answers=pop(h.answer_stack); h.choice=nil end
  elseif id==9 then h.answers={}
  elseif id==10 or id==11 then
    local a,i=choose(h,id)
    assert(a,"empty answer menu")
    result=id==10 and a or i
    h.choice=nil
  else result=effect(h,"intrinsic",args,keep,id) end
  if keep then assert(result~=nil,"missing intrinsic response"); push(s,result) end
end
local function invoke(h,id,event,item,stack)
  assert(functions[id],"unresolved direct function")
  assert(#h.frames<64,"call depth limit")
  local n=arity[id]
  while #stack<n do push(stack,0) end
  local locals={}
  for i=n-1,0,-1 do locals[i]=pop(stack) end
  local result=functions[id](h,locals,event,item)
  h.frames[#h.frames]=nil
  if result~=nil then push(stack,result) end
end
local function enter(h,id,base)
  local f={id=id,base=base,pc=0}
  push(h.frames,f)
  return f
end
local function valid(v,depth)
  if math.type(v)=="integer" then return v>=-2147483648 and v<=2147483647 end
  if type(v)=="string" then return #v<=65535 end
  if not arr(v) or depth>4 or #v>4096 then return false end
  for k,item in pairs(v) do
    if math.type(k)~="integer" or k<1 or k>#v or not valid(item,depth+1) then return false end
  end
  for i=1,#v do if v[i]==nil then return false end end
  return true
end
local function start(id,event,item)
  assert(roots[id] and math.type(event)=="integer" and math.type(item)=="integer","invalid dialogue dispatch")
  local h={steps=0,count=0,frames={},answers={},answer_stack={},text="",found=false}
  local co=coroutine.create(function()
    invoke(h,id,event,item,{})
    return {status="completed",termination="return",steps=h.steps}
  end)
  local pending,finished
  return {resume=function(self,reply)
    if finished then return finished end
    if pending and pending.expects_value then
      assert(valid(reply,0),"host response outside value profile")
      if pending.kind=="flag_read" then assert(reply==0 or reply==1,"invalid flag read") end
      if pending.kind=="choice" then
        local ok=false
        for _,c in ipairs(pending.args) do if c==reply then ok=true end end
        assert(ok,"reply outside active choices")
      end
    else assert(reply==nil,"unexpected host response") end
    local ok,val=coroutine.resume(co,copy(reply))
    if not ok then
      local f=h.frames[#h.frames] or {id=id,pc=0,base=0}
      if val==abort then
        finished={status="completed",termination="abort",function_id=f.id,pc=f.pc,source_offset=f.base+f.pc,steps=h.steps}
      else
        finished={status="blocked",reason=tostring(val),function_id=f.id,pc=f.pc,source_offset=f.base+f.pc,steps=h.steps}
      end
      return finished
    end
    if val.status~="effect" then finished=val
    else pending={kind=val.kind,expects_value=val.expects_value,args=copy(val.args)} end
    return val
  end}
end
