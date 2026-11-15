"""Exercise original optional Trinsic scripts through the ClassicUO controls.

Each case owns a disposable save. Native debug operations only prepare stated
preconditions before the client connects; actions under test use UO handlers.
No quest flags, eggs, Usecode or NPC schedules are replaced by these tests.
"""
import argparse
import array
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import runpy
import shutil
import struct
import time
import traceback

from baseline import actor
from investigation import Walkthrough
from play import ROOT, BIN, HOST, client, session
from reference import members, sha, stage

HERE = Path(__file__).resolve().parent
audit = runpy.run_path(str(HERE/'item-use-audit.py'))
debug = runpy.run_path(str(HERE/'developer-wand.py'))
FrontendPipe = runpy.run_path(str(HERE/'trinsic-playtest.py'))['FrontendPipe']


class SidePipe(FrontendPipe):
    def __init__(self, *args):
        self.observations = []
        super().__init__(*args)

    def action(self, *args, **kwargs):
        result = super().action(*args, **kwargs)
        self.observations.append(self.frame)
        return result


class SideChecks:
    def __init__(self, p, folder, case):
        self.p, self.folder, self.case, self.evidence = p, folder, case, []
        self.walk = Walkthrough(p, folder)

    def note(self, case, **evidence):
        self.evidence.append(dict(case=case, **evidence))
        print('PASS', case, json.dumps(evidence), flush=True)
        (self.folder/'side-checks.json').write_text(json.dumps(self.evidence, indent=2)+'\n')

    def wait(self, predicate, seconds=15):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            self.p.sync()
            if predicate(): return
            time.sleep(.025)
        raise TimeoutError((self.p.head, self.p.frame[:1000]))

    def total(self, shape, frame=None):
        owners = {r[0] for r in self.p.rows if r[7] in (0,1,2)}
        while True:
            children = {r[0] for r in self.p.rows if r[6] in owners}
            if children <= owners: break
            owners |= children
        return sum(r[9] for r in self.p.rows if r[1]==shape and
                   r[6] in owners and (frame is None or r[2]==frame))

    def text(self):
        return ' '.join(bytes.fromhex(line[2:]).decode('cp437') for line in
                        self.p.frame.splitlines() if line.startswith('T '))

    def talk(self, slot, choices, numbers=(), targets=(), *, optional=()):
        npc = self.walk.actor(slot)
        assert npc, ('NPC outside view', slot, self.walk.xy())
        self.walk.go(npc[3:5], near=2, npc=slot)
        assert self.p.send('USE', npc[0])=='using'
        return self.dialogue(choices, numbers, targets, optional=optional)

    def dialogue(self, choices=(), numbers=(), targets=(), *, optional=()):
        pending, nums, target_ids = list(choices), list(numbers), list(targets)
        seen, picked, visited, quiet = [], [], False, None
        end=time.monotonic()+65
        while time.monotonic()<end:
            self.p.sync()
            mode, token=map(int,self.p.head[9:11])
            if not mode:
                if visited:
                    if quiet is None: quiet=time.monotonic()
                    if time.monotonic()-quiet>.2: break
                time.sleep(.025); continue
            visited=True;quiet=None
            words=self.text()
            if words and (not seen or words!=seen[-1]):seen.append(words)
            if mode==1:self.p.send('ANSWER',token,0)
            elif mode==2:
                word=pending[0] if pending and pending[0] in self.p.choices else None
                required=word is not None
                if word is None:word=next((w for w in optional if w in self.p.choices),None)
                assert word is not None, ('Unexpected choices',self.p.choices,pending,seen[-2:])
                if required:pending.pop(0)
                picked.append(word)
                self.p.send('ANSWER',token,self.p.choices.index(word))
            elif mode==3:
                assert nums, ('Unexpected number prompt',seen[-2:])
                self.p.send('NUMBER',token,nums.pop(0))
            elif mode==4:
                assert target_ids, ('Unexpected target',seen[-2:])
                self.p.send('TARGET',token,target_ids.pop(0))
            else:raise AssertionError(('Unexpected native view',mode,seen[-2:]))
        else:raise TimeoutError(('Dialogue',self.p.head,pending,seen[-2:]))
        assert not (pending or nums or target_ids),(pending,nums,target_ids,picked,seen[-2:])
        return ' '.join(seen),picked

    def recover(self):
        self.wait(lambda: self.p.head[9]=='0' and all(
            int(next(l for l in self.p.frame.splitlines() if l.startswith('H ')).split()[i+1])==0
            for i in (0,3,4,5,7)))
        audit['movement'](self.p)

    def checkpoint(self, name):
        assert self.p.send('SAVE')=='ok'
        shutil.copyfile(self.folder/'GAME00.U7',self.folder/(name+'.U7'))
        self.p.capture()
        return members(self.folder/'GAME00.U7')


def prepare(p, folder, case):
    q=debug['Checks'](p)
    def visit(x,y,z=0):
        q.send('AUDITVISIT',x,y,str(z))
    if case=='haunted':
        # Attribute setup exercises failed rolls; this is a stress case,
        # not a claim that the unmodified party always becomes sick/frightened.
        q.setstats(strength=1,hp=1)
        q.setstats(184,strength=1,hp=1,intelligence=1)
        visit(973,2303)
    elif case in ('healer','inn','shop','training','ship','sextant','carriage','closed','resurrection') or case.endswith(('-poor','-closed','-untrained','-capped','-full')):
        service=case.split('-')[0]
        slot={'healer':17,'inn':19,'shop':18,'training':20,'ship':21,'sextant':21,'carriage':11,'closed':18,'resurrection':17}[service]
        if case=='healer':
            q.setstats(hp=2)
            q.create(340,3)  # Original poison potion for the paid cure branch.
        if case in ('healer','inn','shop','training','carriage','sextant'):q.create(644,6,100)
        if case in ('training-untrained','training-capped','inn-full'):q.create(644,6,100)
        if case=='training-untrained':q.setstats(training=0)
        if case=='training-capped':q.setstats(combat=30)
        if case=='inn-full':
            q.setstats(strength=1,hp=1);q.setstats(184,strength=1,hp=1)
        if case=='resurrection':
            for _ in range(5):q.create(644,6,100)
        if case=='ship':
            for _ in range(6):q.create(644,6,100)
        if case=='closed':q.send('DBGTIME',21,0)
        # Apollonia's original overnight shift ends at 03:00, unlike the shops.
        elif case.endswith('-closed'):q.send('DBGTIME',4 if service=='inn' else 1,0)
        elif case!='carriage':q.send('DBGTIME',12,0)
        assert p.send('SAVE')=='ok'
        x,y,z=actor(members(folder/'GAME00.U7'),slot)['xyz']
        visit(x+1,y,z)
        audit['settle'](p)
        if case.endswith('-poor'):
            av=next(r for r in p.rows if r[7]==0)
            owners={r[0] for r in p.rows if r[7] in (0,1,2)}
            while True:
                children={r[0] for r in p.rows if r[6] in owners}
                if children<=owners:break
                owners|=children
            for coin in [r for r in p.rows if r[1]==644 and r[6] in owners]:
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1)):
                    q.send('GROUND',coin[0],av[3]+dx,f'{av[4]+dy} {av[5]} -1',expected=('ok','blocked','unreachable'))
                    if p.head[5]=='ok':break
                else:raise AssertionError('No reachable floor for setting aside test coins')
        if case=='resurrection':
            q.setstats(184,hp=1,intelligence=1)
            before={r[0] for r in p.rows if r[1] in (400,414)}
            contents=[r[0] for r in p.rows if r[6] in (184,200)]
            # Produce a genuine actor-linked corpse with original Death Bolt.
            # Only this disposable setup bypasses spell costs.
            for _ in range(4):
                q.send('AUDITCAST',57)
                q.wait(lambda:p.head[9]=='4')
                assert p.send('TARGET',int(p.head[10]),184)=='ok'
                end=time.monotonic()+4
                while time.monotonic()<end:
                    p.sync();time.sleep(.03)
                bodies=[r for r in p.rows if r[1] in (400,414) and r[0] not in before]
                if bodies:break
            assert bodies,'Original spell did not create an actor-linked corpse'
            audit['settle'](p)
            (folder/'resurrection-setup.json').write_text(json.dumps(dict(body=bodies[0],possessions=contents),indent=2))
    elif case=='cleanup':
        assert members(folder/'GAME00.U7')['FLAGINIT'][87], 'Requires an earned gate-exit checkpoint'
    elif case.startswith('well-'):
        x,y={'well-west':(987,2303),'well-north':(1005,2131),'well-south':(1023,2287)}[case]
        q.create(810)
        visit(x-6,y+3)
    elif case.removesuffix('-audio') in ('speech-house','speech-south','music','music-pub','bucket','forge'):
        visit(*{'speech-house':(973,2303),'speech-south':(1005,2346),
                'music':(1078,2209),'music-pub':(1090,2255),
                'bucket':(1076,2201),'forge':(972,2291)}[case.removesuffix('-audio')])
    assert p.send('SAVE')=='ok'
    shutil.copyfile(folder/'GAME00.U7',folder/'prepared.U7')
    return q


def haunted(q):
    p=q.p
    chairs={r[0]:r[2] for r in p.rows if r[1]==873 and 961<=r[3]<=975 and 2285<=r[4]<=2315}
    doors={r[0]:r[2] for r in p.rows if r[1] in (270,376) and 961<=r[3]<=975 and 2285<=r[4]<=2315}
    print('HAUNTED initial',chairs,doors,flush=True)
    q.checkpoint('outside')
    fear_work=[]
    for xy in ((970,2302),(968,2302),(968,2305),(968,2306),(968,2307),(968,2308),(968,2311),(968,2308),(966,2305),(968,2303),
               (966,2300),(968,2297),(965,2296),(970,2294),(972,2291),(973,2294)):
        print('WALK',xy,flush=True)
        crossing_fear=xy[0]==968 and 2305<=xy[1]<=2308
        q.walk.go(xy,near=0 if crossing_fear else 1)
        if crossing_fear:
            # Fear's original recovery is posted only ten ticks later. Save
            # immediately at its boundary to observe the temporary work change.
            assert p.send('SAVE')=='ok'
            fear_work.append(actor(members(q.folder/'GAME00.U7'),1)['work'])
        p.action(['WAIT 350'],observation=True)
        if xy in ((968,2311),(968,2297),(973,2294)):q.checkpoint('house-'+str(xy[1]))
    q.recover()
    after=q.checkpoint('haunted-finished')
    seen_frames={id:{frame} for id,frame in chairs.items()}
    seen_doors={id:{frame} for id,frame in doors.items()}
    poses={0:set(),1:set()};barks=set();blood=set()
    for frame in p.observations:
        for line in frame.splitlines():
            if line.startswith('E '):
                r=list(map(int,line.split()[1:]))
                if r[0] in seen_frames:seen_frames[r[0]].add(r[2])
                if r[0] in seen_doors:seen_doors[r[0]].add(r[2])
                if r[7] in poses:poses[r[7]].add(r[2]&15)
                if r[1]==912 and 960<=r[3]<=975 and 2285<=r[4]<=2315:blood.add(r[0])
            if line.startswith('B '):barks.add(line)
    changed={str(k):sorted(v) for k,v in seen_frames.items() if len(v)>1}
    assert changed, ('No haunted chair changed frame',seen_frames)
    assert any(len(v)>1 for v in seen_doors.values()),seen_doors
    assert actor(after,1)['work']==31, actor(after,1)
    def eggs(saved):
        data=saved['U7IBUF.DAT'];found=[]
        for at in range(0,len(data)-8,8):
            _,xy,tf,extra=struct.unpack_from('<4H',data,at)
            if tf&1023!=275 or extra+8>len(data):continue
            flags=struct.unpack_from('<H',data,extra)[0]
            function=struct.unpack_from('<H',data,extra+6)[0]
            if flags&15==5 and function in (1717,1718,1722,1723):
                found.append(dict(handle=at,xy=[xy&255,xy>>8],function=function))
        return found
    before_eggs=eggs(members(q.folder/'prepared.U7'))
    assert len(before_eggs)==11 and not eggs(after),(before_eggs,eggs(after))
    nauseated=any(v & {11,12,13} for v in poses.values())
    if nauseated:
        assert blood,'Nausea had poses but no original temporary blood'
        assert 'NATIVEPOSE ' in (q.folder/'controls.txt.log').read_text(), 'Native bend/kneel never reached UO animation'
    q.note('haunted traversal and recovery',chairs=changed,doors={str(k):sorted(v) for k,v in seen_doors.items()},
           poses={str(k):sorted(v) for k,v in poses.items()},barks=sorted(barks),temporary_blood=sorted(blood),
           iolo_schedule=actor(after,1)['work'],fear_work=fear_work,fear_observed=0 in fear_work,
           all_eleven_eggs_consumed=True,nausea_presented=nauseated)
    p.action(['U7LOADKEY']);p.sync();q.recover()
    q.note('haunted save/load movement recovery')


def healer(q):
    p=q.p
    gold=q.total(644)
    words,_=q.talk(17,['services','Yes','heal','hexen','Yes','bye'])
    assert 'wounds have been healed' in words,words
    values=list(map(int,next(l[2:] for l in p.frame.splitlines() if l.startswith('V ')).split()))
    assert values[3]==values[0] and q.total(644)==gold-30,(values,gold,q.total(644))
    q.note('paid healing',price=30,hp=values[3],max_hp=values[0])
    gold=q.total(644)
    words,_=q.talk(17,['services','Yes','heal','hexen','Yes','bye'])
    assert 'healthy' in words and q.total(644)==gold,words
    q.note('healthy actor not charged')
    poison=next(r for r in p.rows if r[1]==340 and r[2]==3 and r[6])
    assert p.send('USE',poison[0])=='using'
    q.wait(lambda:p.head[9]=='4')
    assert p.send('TARGET',int(p.head[10]),56)=='ok'
    q.wait(lambda:any(l.startswith('C 56 ') and int(l.split()[5])&0x2000 for l in p.frame.splitlines()))
    words,_=q.talk(17,['services','Yes','cure poison','hexen','Yes','bye'])
    assert q.total(644)==gold-50 and not int(next(l for l in p.frame.splitlines() if l.startswith('C 56 ')).split()[5])&0x2000
    q.note('paid native poison cure',price=50,potion_consumed=not any(r[0]==poison[0] for r in p.rows))
    gold=q.total(644)
    for choices in (['services','No','bye'],['services','Yes','heal','Nobody','bye'],
                    ['services','Yes','cure poison','hexen','No','bye']):
        q.talk(17,choices)
        assert q.total(644)==gold
    words,_=q.talk(17,['services','Yes','resurrect'])
    assert 'do not see anyone' in words,words
    q.recover();q.checkpoint('healer-finished')
    q.note('healer cancellation, price refusal and absent corpse recover',gold=gold)


def inn(q):
    p=q.p;gold=q.total(644);bread=q.total(377,0)
    words,_=q.talk(19,['buy','bread','Yes','No','bye'],numbers=[3])
    assert q.total(644)==gold-6 and q.total(377,0)==bread+3,(gold,q.total(644),bread,q.total(377,0),words)
    q.note('pub food quantity controls',loaves=3,price=6)
    gold=q.total(644);drinks=q.total(616,3)
    q.talk(19,['buy','ale','Yes','No','bye'])
    assert q.total(644)==gold-2 and q.total(616,3)==drinks+1
    q.note('pub drink purchase',price=2)
    gold=q.total(644);keys=q.total(641)
    saved=q.checkpoint('before-rental');party_count=saved['PARTY'][16]
    words,_=q.talk(19,['room','Yes','bye'])
    assert 'room key' in words and q.total(641)==keys+1 and q.total(644)==gold-party_count*6,(words,gold,q.total(644),party_count)
    q.checkpoint('rented-room')
    q.note('inn rental',party_count=party_count,price=party_count*6,keys_received=1)
    p.action(['U7LOADKEY']);p.sync()
    assert q.total(641)==keys+1
    q.recover();q.note('rental persists through load')
    q.walk.go((1083,2256))
    door=next(r for r in p.rows if r[1]==270 and r[3:5]==[1083,2258])
    key=next(r for r in p.rows if r[1]==641 and r[6] and r[0] not in
             {int(l.split()[1]) for l in p.observations[0].splitlines() if l.startswith('E ') and int(l.split()[2])==641})
    assert door[2]%4==2,door
    p.send('USE',key[0]);q.wait(lambda:p.head[9]=='4')
    p.send('TARGET',int(p.head[10]),door[0]);p.sync()
    assert next(r for r in p.rows if r[0]==door[0])[2]%4==0
    p.send('USE',door[0]);p.sync()
    q.walk.go((1085,2269))
    # The visible blanket sits one native lift above the base. Original bed
    # Usecode resolves that clicked blanket to its corresponding bed beneath.
    bed=next(r for r in p.rows if r[1]==696 and r[5]==1 and r[3:5]==[1084,2269])
    ticks=int(p.head[3]);p.action(['WAIT 150',f'PIXELUSE {bed[0]}'])
    hours=False;quiet=None;wake_text=[];rejected_during_rest=False;end=time.monotonic()+40
    while time.monotonic()<end:
        p.sync();mode,token=map(int,p.head[9:11])
        health=next(l.split()[1:] for l in p.frame.splitlines() if l.startswith('H '))
        advancing=int(health[8]) if len(health)>8 else 0
        if advancing and not rejected_during_rest:
            before=q.walk.actor(0)[3:6]
            assert p.send('STEP',0)=='busy'
            assert q.walk.actor(0)[3:6]==before
            rejected_during_rest=True
            continue
        if mode==3:
            assert not hours,'Unexpected repeated rest-hours prompt'
            p.send('NUMBER',token,1);hours=True;quiet=None
        elif mode==1:
            wake_text.append(q.text());p.capture()
            p.send('ANSWER',token,0);quiet=None
        elif mode:raise AssertionError(('Unexpected rest prompt',mode,q.text()))
        elif (hours and not advancing and int(p.head[3])-ticks>=1500
              and q.walk.actor(0)[2]&15!=13
              and not int(next(l for l in p.frame.splitlines() if l.startswith('P ')).split()[11])&0x80):
            # Original wake-up dialogue is posted after the clock advance.
            # Observe a quiet interval instead of racing its next native tick.
            if quiet is None:quiet=time.monotonic()
            if time.monotonic()-quiet>.5:break
        else:quiet=None
    else:raise TimeoutError(('Rest did not finish',p.head,wake_text))
    q.recover();q.checkpoint('rented-rested')
    q.note('rental key unlocks room and native one-hour rest wakes',elapsed_ticks=int(p.head[3])-ticks,wake_text=wake_text,
           bridge_observed_rest=rejected_during_rest,movement_refused_during_native_advance=rejected_during_rest)


def shop(q):
    gold=q.total(644);arrows=q.total(722)
    q.talk(18,['Avatar','job','buy','weapons','arrows','Yes','No','bye'],numbers=[2],optional=['hexen'])
    assert q.total(644)==gold-20 and q.total(722)==arrows+24,(gold,q.total(644),arrows,q.total(722))
    q.note('Dell sells two dozen arrows',price=20,arrows=24)
    gold=q.total(644);buckets=q.total(810)
    q.talk(18,['job','buy','provisions','bucket','Yes','No','bye'])
    assert q.total(644)==gold-2 and q.total(810)==buckets+1
    q.note('Dell provisions',price=2,buckets=1)
    q.recover();q.checkpoint('shop-finished')


def training(q):
    p=q.p;gold=q.total(644)
    before=list(map(int,next(l[2:] for l in p.frame.splitlines() if l.startswith('P ')).split()))
    q.talk(20,['job','train','No','hexen','bye'])
    after=list(map(int,next(l[2:] for l in p.frame.splitlines() if l.startswith('P ')).split()))
    expected=(before[1]+int(next(l.split()[2] for l in p.frame.splitlines() if l.startswith('V ')))+1)//2
    assert q.total(644)==gold-20 and after[1]==expected and after[4]==before[4]-1,(before,after,expected)
    q.note('training updates native combat and points',gold_spent=20,combat=[before[1],after[1]],training=[before[4],after[4]])
    gold=q.total(644)
    q.talk(20,['job','train','Yes','bye'])
    q.talk(20,['job','train','No','Nobody','bye'])
    assert q.total(644)==gold
    q.recover();q.checkpoint('training-finished');q.note('training decline and no student recover')


def ship(q):
    p=q.p;gold=q.total(644);scrolls=q.total(797)
    words,_=q.talk(21,['job','ship','deed','Yes','bye'])
    assert q.total(644)==gold-600 and q.total(797)==scrolls+1,words
    saved=q.checkpoint('ship-purchased');assert saved['FLAGINIT'][88]
    q.note('Scaly Eel deed',price=600,flag=88)
    gold=q.total(644)
    words,_=q.talk(21,['job','ship','deed','bye'])
    assert 'already sold' in words and q.total(644)==gold and q.total(797)==scrolls+1,words
    q.note('second ship purchase refused')
    q.recover()


def carriage(q):
    gold=q.total(644);scrolls=q.total(797)
    words,_=q.talk(11,['job','stables','carriage','Yes','bye'],optional=['Yes'])
    assert q.total(644)==gold-60 and q.total(797)==scrolls+1,words
    q.recover();q.checkpoint('carriage-purchased')
    q.note('horse and carriage title',price=60)


def sextant(q):
    p=q.p;gold=q.total(644);count=q.total(650)
    words,_=q.talk(21,['job','sextant','Yes','bye'])
    # Retail Gargan checks the quoted 80 gold, but never calls TakeGold here.
    # Keep that original behavior; the frontend must not invent a charge.
    assert 'Here ye are' in words and q.total(650)==count+1 and q.total(644)==gold,words
    item=next(r for r in p.rows if r[1]==650 and r[6])
    prior={l for l in p.frame.splitlines() if l.startswith('B ')}
    p.send('USE',item[0])
    def output():
        return ' '.join(bytes.fromhex(l.split()[3]).decode('cp437') for l in p.frame.splitlines()
                        if l.startswith('B ') and l not in prior)
    q.wait(lambda:'under a roof' in output() or ' East' in output() or ' West' in output())
    words=output()
    q.recover();q.checkpoint('sextant-used')
    q.note('native sextant sale and activation',quoted_price=80,original_charge=0,native_output=words)


def forge(q):
    p=q.p
    bellows=next(r for r in p.rows if r[1]==431 and r[3:5]==[971,2291])
    fire=next(r for r in p.rows if r[1]==739 and r[3:5]==[968,2292])
    assert fire[2]==0
    p.action(['WAIT 150',f'PIXELUSE {bellows[0]}']);seen=[]
    end=time.monotonic()+15
    while time.monotonic()<end:
        p.sync()
        pair=[next(r[2] for r in p.rows if r[0]==id) for id in (bellows[0],fire[0])]
        if not seen or pair!=seen[-1]:seen.append(pair)
        if any(f==3 for b,f in seen) and pair==[0,0]:break
    assert any(b>0 for b,f in seen) and any(f==3 for b,f in seen) and seen[-1]==[0,0],seen
    q.recover();q.checkpoint('forge-cooled')
    q.note('native bellows heating and cooldown in UO',frames=seen)


def closed(q):
    gold=q.total(644)
    words,_=q.talk(18,[])
    assert 'meeting' in words and q.total(644)==gold,words
    q.recover();q.checkpoint('closed-finished')
    q.note('Dell Fellowship meeting refusal recovers',gold_unchanged=True)


def resurrection(q):
    p=q.p;setup=json.loads((q.folder/'resurrection-setup.json').read_text())
    body=setup['body'][0];gold=q.total(644)
    purse=lambda:int(next(l for l in p.frame.splitlines() if l.startswith('P ')).split()[8])
    avatar_gold=purse()
    q.p.capture()
    words,_=q.talk(17,['services','Yes','resurrect','No','bye'])
    assert 'departed this life' in words and q.total(644)==gold
    assert any(r[0]==body for r in p.rows)
    q.note('resurrection price refusal preserves corpse and gold')
    words,_=q.talk(17,['services','Yes','resurrect','Yes','bye'])
    # Iolo's own coins rejoin the party after resurrection; compare the paying
    # Avatar's purse so recovered possessions are not mistaken for a refund.
    assert 'comrade is alive' in words and purse()==avatar_gold-400,(words,avatar_gold,purse())
    q.wait(lambda:any(r[7]==1 for r in p.rows))
    state=next(l.split() for l in p.frame.splitlines() if l.startswith('C 184 '))
    assert int(state[2])>0 and not int(state[5])&0x8000,state
    assert not any(r[0]==body for r in p.rows)
    present={r[0] for r in p.rows}
    assert set(setup['possessions'])<=present,(setup['possessions'],present)
    saved=q.checkpoint('resurrected')
    q.note('Chantu paid companion resurrection',price=400,health=int(state[2]),possessions_retained=True,
           native_work=actor(saved,1)['work'])
    p.action(['U7LOADKEY']);p.sync();q.recover()
    q.note('resurrected companion persists through load')


def poor(q):
    assert q.total(644)==0
    case=q.case.removesuffix('-poor')
    choices={
        'healer':(17,['services','Yes','heal','hexen','Yes','bye'],()),
        'inn':(19,['room','Yes','buy','bread','Yes','No','bye'],[1]),
        'shop':(18,['Avatar','job','buy','provisions','bucket','Yes','No','bye'],()),
        'training':(20,['job','train','No','hexen','bye'],()),
        'ship':(21,['job','ship','deed','Yes','bye'],()),
        'carriage':(11,['job','stables','carriage','Yes','bye'],()),
    }
    slot,topics,nums=choices[case]
    before={s:q.total(s) for s in (641,377,810,797)}
    words,_=q.talk(slot,topics,nums,optional=['hexen','Yes'] if case=='carriage' else ['hexen'])
    assert 'enough gold' in words or 'not have any gold' in words,words
    assert q.total(644)==0 and before=={s:q.total(s) for s in before}
    q.recover();q.checkpoint('refused')
    q.note(case+' insufficient funds refusal',inventory_unchanged=True)


def cleanup(q):
    # Resume the real completed investigation. Re-enter through the original
    # stable door; the original cleanup egg owns deletion and its prerequisites.
    q.walk.go((1070,2208))
    door=next(r for r in q.p.rows if r[1] in (270,376) and r[3:5]==[1071,2207])
    if door[2]%4!=1:q.p.send('USE',door[0]);q.p.sync()
    q.walk.go((1070,2205));q.walk.go((1069,2197))
    q.p.action(['WAIT 900'],observation=True)
    remaining=[r[:6] for r in q.p.rows if r[1] in (867,414,912,810) and not r[6]
               and 1064<=r[3]<=1083 and 2182<=r[4]<=2208]
    assert not remaining,remaining
    q.recover();saved=q.checkpoint('cleaned-stables')
    assert saved['FLAGINIT'][87]
    q.note('native post-investigation murder cleanup',removed_in_uo=True,original_flag=87)


def service_closed(q):
    service=q.case.split('-')[0];gold=q.total(644)
    slots={'shop':18,'inn':19,'training':20,'ship':21}
    topics={'shop':['Avatar','job','buy','bye'],'inn':['job','bye'],
            'training':['job','train','bye'],'ship':['job','sextant','ship','deed','bye']}
    words,_=q.talk(slots[service],topics[service],optional=['hexen'])
    assert any(t in words for t in ('business hours','daylight hours','when it is open','when it is is open')),words
    assert q.total(644)==gold
    q.recover();saved=q.checkpoint('closed')
    q.note(service+' outside business hours',native_work=actor(saved,slots[service])['work'])


def training_refused(q):
    gold=q.total(644)
    words,_=q.talk(20,['job','train','No','hexen','bye'])
    expected='practical experience' if q.case.endswith('untrained') else 'already as proficient'
    assert expected in words and q.total(644)==gold,words
    q.recover();q.checkpoint('training-refused')
    q.note(q.case,gold_unchanged=True)


def full(q):
    gold=q.total(644);keys=q.total(641)
    words,_=q.talk(19,['room','Yes','bye'])
    assert 'carrying too much' in words and q.total(644)==gold and q.total(641)==keys,words
    q.recover();q.checkpoint('room-full');q.note('inn overloaded party refusal',inventory_unchanged=True)


def speech(q):
    p=q.p
    sound=int(q.case.endswith('-audio'))
    p.action(['U7OPTIONS','U7AUDIO','WAIT 200',f'U7AUDIOSET 0 0 {sound} 100 100 100',
              'WAIT 350',f'U7AUDIOACK 0 0 {sound} 100 100 100 0','U7AUDIOCLOSE','U7OPTION 4'],observation=True)
    if sound:
        p.action(['WAIT 1000'],observation=True)
        audio_start=(q.folder/'audio.raw').stat().st_size
    if q.case.startswith('speech-house'):
        for xy in ((970,2302),(968,2302),(968,2298),(973,2295)):
            q.walk.go(xy,near=1)
        expected='Ha ha ha ha ha ha!';track=31
    else:
        q.walk.go((1008,2346));expected='wrong direction';track=24
    p.action(['WAIT 500'],observation=True)
    words=' '.join(bytes.fromhex(l[2:]).decode('cp437') for frame in p.observations
                   for l in frame.splitlines() if l.startswith('T '))
    if not sound:assert expected in words,words[-2000:]
    else:
        p.action(['WAIT 5000'],observation=True)
        data=(q.folder/'audio.raw').read_bytes()[audio_start:]
        samples=array.array('h');samples.frombytes(data[:len(data)//2*2])
        rms=math.sqrt(sum(float(v)*v for v in samples)/max(1,len(samples)))
        assert rms>1,('Speech-only output is silent',track,rms)
    if p.head[9]!='0':q.dialogue()
    q.recover();q.checkpoint('speech-finished')
    q.note('Guardian speech '+str(track)+(' original audio' if sound else ' native text fallback'),
           expected=expected,**(dict(rms=round(rms,3),bytes=len(data),pcm_start=audio_start) if sound else {}))


def music(q):
    p=q.p
    p.action(['U7OPTIONS','U7AUDIO','U7AUDIOSET 1 0 0 100 100 100','WAIT 350',
              'U7AUDIOACK 1 0 0 100 100 100 0','U7AUDIOCLOSE','U7OPTION 4'],observation=True)
    audio_start=(q.folder/'audio.raw').stat().st_size
    expected={19} if q.case=='music-pub' else {27,35}
    route=((1088,2255),) if q.case=='music-pub' else (
        (1070,2205),(1071,2195),(1070,2208),(1032,2228),(1031,2215))
    for xy in route:
        print('MUSIC WALK',xy,flush=True)
        q.walk.go(xy,near=0 if q.case=='music-pub' else 2)
        p.action(['WAIT 300'],observation=True)
        observed={int(l.split()[2]) for frame in p.observations for l in frame.splitlines() if l.startswith('AU ')}
        if expected<=observed:break
    observed={int(l.split()[2]) for frame in p.observations for l in frame.splitlines() if l.startswith('AU ')}
    assert expected<=observed,observed
    p.action(['WAIT 1200'],observation=True)
    data=(q.folder/'audio.raw').read_bytes()[audio_start:];samples=array.array('h');samples.frombytes(data[:len(data)//2*2])
    rms=math.sqrt(sum(float(v)*v for v in samples)/max(1,len(samples)))
    assert rms>1,('Native music output is silent',rms)
    q.recover();q.checkpoint('music-tour')
    q.note('original regional music',tracks=sorted(observed),expected=sorted(expected),rms=round(rms,3),pcm_start=audio_start)


def bucket(q):
    p=q.p
    item=next(r for r in p.rows if r[1]==810 and r[2]==2 and not r[6])
    assert p.send('MOVE',item[0],88)=='ok'
    p.send('USE',item[0]);q.wait(lambda:p.head[9]=='4');p.send('TARGET',int(p.head[10]),56)
    q.recover()
    assert next(r for r in p.rows if r[0]==item[0])[2]==2
    q.note('blood bucket refuses drinking through native target')
    q.walk.go((1078,2238));bucket=next(r for r in p.rows if r[1]==810 and not r[6] and r[3:5]==[1078,2237])
    assert p.send('MOVE',bucket[0],88)=='ok'
    well=next(r for r in p.rows if r[1]==470 and not r[6])
    previous={l for l in p.frame.splitlines() if l.startswith('R ')}
    p.send('USE',bucket[0]);q.wait(lambda:p.head[9]=='4')
    assert p.send('TARGET',int(p.head[10]),well[0])=='ok'
    q.wait(lambda:any(l.startswith('R ') and l not in previous for l in p.frame.splitlines()))
    assert next(r for r in p.rows if r[0]==bucket[0])[2]==0
    q.recover();q.checkpoint('east-well-refusal')
    q.note('east well native path refusal is presented and releases movement',
           known_issue=True,well=well[3:6],scripted_standing_point=[1071,2235,0],
           reason='Original standing point intersects the neighboring wall; no frontend or map bypass applied')


def well(q):
    p=q.p
    xy={'well-west':(987,2303),'well-north':(1005,2131),'well-south':(1023,2287)}[q.case]
    bucket=next(r for r in p.rows if r[1]==810 and r[6])
    well=next(r for r in p.rows if r[1]==470 and r[3:5]==list(xy))
    p.send('USE',bucket[0]);q.wait(lambda:p.head[9]=='4')
    assert p.send('TARGET',int(p.head[10]),well[0])=='ok'
    q.wait(lambda:any(r[0]==bucket[0] and r[2]==1 for r in p.rows))
    p.send('USE',bucket[0]);q.wait(lambda:p.head[9]=='4');p.send('TARGET',int(p.head[10]),56)
    q.wait(lambda:any(r[0]==bucket[0] and r[2]==0 for r in p.rows))
    q.recover();q.checkpoint('bucket-finished')
    q.note('UO targeting and native walk fill bucket, then drink water',well=list(xy))


CASES={'haunted':haunted,'healer':healer,'inn':inn,'shop':shop,'training':training,
       'ship':ship,'sextant':sextant,'carriage':carriage,'closed':closed,'resurrection':resurrection,'cleanup':cleanup,
       'training-untrained':training_refused,'training-capped':training_refused,'inn-full':full,
       'speech-house':speech,'speech-south':speech,'music':music,'music-pub':music,'bucket':bucket,'forge':forge,
       'speech-house-audio':speech,'speech-south-audio':speech,
       **{case:well for case in ('well-west','well-north','well-south')},
       **{case+'-closed':service_closed for case in ('shop','inn','training','ship')},
       **{case+'-poor':poor for case in ('healer','inn','shop','training','ship','carriage')}}


def run(case,name,checkpoint=None):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',name):
        raise ValueError('Run names may contain only letters, numbers, hyphens and underscores')
    folder=ROOT/'runs'/name
    if folder.exists():raise FileExistsError('Use a fresh side-activity run: '+name)
    if checkpoint:
        stage(name);shutil.copyfile(checkpoint,folder/'GAME00.U7')
    start=time.time()
    result=dict(case=case,run=name,status='failed',preconditions='See prepared.U7 and native-setup.jsonl',
                host_sha256=sha(HOST),client_sha256=sha(BIN/'cuo.dll'))
    extra={'TRINSIC_PREPARE':'interaction-audit','TRINSIC_DEBUG':'1','U7_ENABLE_AUDIO':'1'}
    if case.startswith('music') or case.endswith('-audio'):extra['U7_AUDIO_DUMP']=str(folder/'audio.raw')
    with session(name,'Investigation',False,extra) as (folder,env,host):
        native=audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
        original=native.raw
        def logged(command):
            answer=original(command)
            with (folder/'native-setup.jsonl').open('a') as out:
                out.write(json.dumps(dict(command=command,outcome=answer))+'\n')
            return answer
        native.raw=logged
        try:prepare(native,folder,case)
        except Exception:
            result.update(error=traceback.format_exc(),seconds=round(time.time()-start,2),images=[])
            (folder/'side-result.json').write_text(json.dumps(result,indent=2)+'\n')
            raise
        finally:native.close()
        path=folder/'controls.txt';path.write_text('')
        env.update(TRINSIC_REPLAY=str(path),TRINSIC_REPLAY_LIVE='1',TRINSIC_ZOOM='1')
        with ThreadPoolExecutor(max_workers=1) as executor:
            running=executor.submit(client,folder,env,host,1200)
            p=None
            try:
                p=SidePipe(folder,running,host)
                checks=SideChecks(p,folder,case)
                CASES[case](checks)
                assert 'TRINSIC interaction timeout/error' not in (folder/'client.log').read_text(), 'Frontend lost the native connection during the activity'
                result.update(status='passed',checks=checks.evidence,batches=p.batch)
            except Exception:
                result['error']=traceback.format_exc()
                raise
            finally:
                if p is not None:
                    (folder/'side-last-state.txt').write_text(p.frame)
                    (folder/'side-observations.txt').write_text('\n---\n'.join(p.observations))
                    p.close()
                if not running.done():
                    try:running.result(timeout=12)
                    except Exception:
                        if host.poll() is None:host.terminate()
                result['seconds']=round(time.time()-start,2)
                result['images']=[]
                for picture in sorted((BIN/'Data/Client/Screenshots').glob('*.png')):
                    if picture.stat().st_mtime<start:continue
                    dest=folder/f'side-{len(result["images"]):02d}.png'
                    shutil.copyfile(picture,dest);result['images'].append(dest.name)
                (folder/'side-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return result


def qualify(case,name,checkpoint=None):
    result=run(case,name,checkpoint)
    if case in ('haunted','inn'):
        # Original saving throws are random. Observe both the script completion
        # and nausea/fear, or the randomly selected sleep speech that used to
        # time out, using at most four independent disposable attempts.
        observed=lambda:any((c.get('nausea_presented') and c.get('fear_observed')) if case=='haunted'
                            else c.get('bridge_observed_rest') for c in result['checks'])
        for attempt in range(1,4):
            if observed():break
            result=run(case,name+'-roll-'+str(attempt),checkpoint)
        assert observed(), f'{case}: required random outcome not observed in four native attempts'
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--case',choices=CASES)
    selection.add_argument('--all',action='store_true')
    parser.add_argument('--run',default='trinsic-side-'+time.strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--checkpoint',type=Path,
                        help='Earned murder-to-gate save; required for cleanup/carriage and --all')
    args=parser.parse_args()
    needs_checkpoint={'carriage','carriage-poor','cleanup'}
    if (args.all or args.case in needs_checkpoint) and (not args.checkpoint or not args.checkpoint.is_file()):
        parser.error('Supply --checkpoint from a completed original investigation (no granted flags)')
    if not args.all:qualify(args.case,args.run,args.checkpoint)
    else:
        results=[]
        for case in CASES:
            name=args.run+'-'+case
            try:result=qualify(case,name,args.checkpoint if case in needs_checkpoint else None)
            except Exception:result=dict(case=case,run=name,status='failed',error=traceback.format_exc())
            results.append(result)
            (ROOT/'runs'/(args.run+'-results.json')).write_text(json.dumps(results,indent=2)+'\n')
        assert all(r['status']=='passed' for r in results),[r['case'] for r in results if r['status']!='passed']
