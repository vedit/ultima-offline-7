"""Exercise native gameplay against the isolated named playable fixture and reopen both the save and pipe."""
import json,time
from play import Pipe,session,ROOT
history=[]
with session('room-exercise','Trinsic-room',True) as (folder,env,host):
    p=Pipe(env['TRINSIC_PIPE'],host)
    def row(i):return next(r for r in p.rows if r[0]==i)
    def action(op,a=0,b=0):
        result=p.send(op,a,b)
        history.append([op,a,b,result,p.head[:],row(56)[3:6],row(9968)[6]])
        print(op,a,b,result,'avatar',row(56)[3:6],'tongs parent',row(9968)[6],flush=True)
        return result
    def navigate(target,limit=55):
        import heapq
        blocked=set()
        for _ in range(limit):
            here=tuple(row(56)[3:5])
            if here==target:return True
            q=[(0,0,here,[])]; seen=set()
            while q:
                _,d,xy,route=heapq.heappop(q)
                if xy in seen:continue
                seen.add(xy)
                if xy==target:break
                for dir,(x,y) in enumerate(((0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1))):
                    nxt=(xy[0]+x,xy[1]+y)
                    if (xy,nxt) in blocked or nxt in seen:continue
                    h=max(abs(nxt[0]-target[0]),abs(nxt[1]-target[1]))
                    if h>35:continue
                    heapq.heappush(q,(d+1+h,d+1,nxt,route+[(dir,nxt)]))
            if not route:return False
            dir,nxt=route[0];action('STEP',dir)
            if tuple(row(56)[3:5])!=nxt:blocked.add((here,nxt))
        return False
    assert navigate((986,2215))
    action('USE',21920);p.sync();print('opened',p.head,flush=True)
    action('MOVE',9968,21920)
    action('CLOSE')
    action('MOVE',9968,13736)
    assert row(9968)[6]==21920
    door=min((r for r in p.rows if r[1] in (270,376,432,433)),key=lambda r:max(abs(r[3]-989),abs(r[4]-2217)))
    print('door',door,flush=True)
    assert navigate((990,2216))
    action('USE',door[0]);p.sync();print('door now',row(door[0]),flush=True)
    assert navigate((990,2217))
    action('STEP',2)
    action('USE',door[0]);p.sync();print('door reopened',row(door[0]),flush=True)
    assert navigate((991,2216))
    action('STEP',4)
    print('crossed to',row(56)[3:6],flush=True)
    assert row(56)[3]>=991 and row(56)[4]>=2217
    assert navigate((990,2216))
    fin=row(824); print('mayor',fin,flush=True)
    assert navigate((fin[3],fin[4]+1))
    action('USE',824)
    used=set()
    for i in range(120):
        p.sync()
        text=next((bytes.fromhex(l[2:]).decode('latin1') for l in p.frame.splitlines() if l.startswith('T ')),'')
        print('prompt',p.head[9:12],p.choices,text[:130],flush=True)
        mode=int(p.head[9]); choices=p.choices[:]
        if not mode: break
        if mode==1:idx=0
        else:
            ranked=['a key','key','murder','investigation','yes','report','Christopher','bye']
            selected=next((c for k in ranked for c in choices if k.lower()==c.lower() and (c not in used or c.lower() in ('yes','bye'))),None)
            if selected is None:selected=next((c for c in choices if c not in used),choices[0])
            if p.head[14]=='1' and 'bye' in choices:selected='bye'
            idx=choices.index(selected);used.add(selected)
        action('ANSWER',int(p.head[10]),idx)
    assert p.head[14]=='1'
    action('SAVE')
    snap=(row(56)[3:6],row(9968)[6],p.head[14])
    action('LOAD')
    assert p.raw('1 1 MOVE 9968 21920')=='stale'
    p.close();p=Pipe(env['TRINSIC_PIPE'],host)
    assert snap==(row(56)[3:6],row(9968)[6],p.head[14])
    p.close()
with session('room-exercise','Trinsic-room') as (folder,env,host):
    p=Pipe(env['TRINSIC_PIPE'],host)
    print('restart',p.head,row(56),row(9968),flush=True)
    assert snap==(row(56)[3:6],row(9968)[6],p.head[14])
    (folder/'exercise.json').write_text(json.dumps(dict(history=history,restarted=p.frame.splitlines()[0],avatar=row(56),tongs=row(9968)),indent=2))
    p.close()


