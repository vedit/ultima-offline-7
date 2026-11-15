"""Exercise the development toolbox through native commands in disposable saves."""
import argparse
import hashlib
import json
import runpy
import struct
import time
from collections import Counter
from pathlib import Path
from play import session,copy_test_save,ROOT,members

audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
Pipe=audit['BoundedPipe']


def hextext(value):return value.encode('cp437').hex() if value else '-'
def decode(value):return bytes.fromhex(value).decode('cp437') if value!='-' else ''
def lines(p,prefix):return [line.split() for line in p.frame.splitlines() if line.startswith(prefix+' ')]
def cap(p):return list(map(int,lines(p,'DEVCAP')[0][1:]))
def message(p):return decode(lines(p,'DM')[0][1]) if lines(p,'DM') else p.head[5]
def created(p):return [int(i) for row in lines(p,'DN') for i in row[1:]]
def inspected(p):
    row=lines(p,'DX')[0]
    names=('id','shape','frame','x','y','z','parent','quantity','weight','class','quality','flags','caps','npc','created')
    return dict(zip(names,map(int,[row[1],*row[3:]])),name=decode(row[2]))
def stats(p):
    keys=('id','strength','dexterity','intelligence','combat','magic','hp','mana','xp','training','food',
          'effective_strength','effective_dexterity','effective_intelligence','effective_combat','level','max_hp','max_mana','status','extra_flags')
    return dict(zip(keys,map(int,lines(p,'DS')[0][1:])))

def live_health(p):
    """Debug inspection must agree with live combat/status HP, not an NPC cache."""
    inspected=stats(p)
    combat=next(row for row in lines(p,'C') if int(row[1])==inspected['id'])
    assert int(combat[2])==inspected['hp'],(combat,inspected)
    if inspected['id']==56:
        assert int(lines(p,'V')[0][4])==int(lines(p,'P')[0][1])==inspected['hp']
    return inspected


class Checks:
    def __init__(self,p):self.p=p;self.evidence=[];self.last=''
    def send(self,op,a=0,b=0,extra='',expected='ok',retry=True):
        end=time.monotonic()+6
        while True:
            self.last=f'{int(self.p.head[4])+1} {self.p.head[2]} {op} {a} {b}'+(' '+extra if extra else '')
            result=self.p.raw(self.last)
            if result!='busy' or expected=='busy' or not retry or time.monotonic()>end:break
            time.sleep(.03)
        allowed=(expected,) if isinstance(expected,str) else expected
        assert result in allowed,(self.last,result,message(self.p),self.p.head)
        return result
    def inspect(self,id):self.send('DBGINSPECT',id);return inspected(self.p)
    def actor(self,id=56):self.inspect(id);return stats(self.p)
    def setstats(self,id=56,**changes):
        current=self.actor(id);current.update(changes)
        values=' '.join(str(current[k]) for k in ('strength','dexterity','intelligence','combat','magic','hp','mana','xp','training','food'))
        self.send('DBGSET',id,extra=values);return live_health(self.p)
    def create(self,shape,frame=0,quantity=1,destination=-1,point=(0,0,0)):
        self.send('DBGI',shape,frame,f'{quantity} {destination} '+' '.join(map(str,point)))
        return created(self.p)[0]
    def duplicate(self,source,destination=-1,point=(0,0,0)):
        self.send('DBGDUP',source,destination,' '.join(map(str,point)))
        return created(self.p)
    def creature(self,shape,center,source=None):
        # Probe adjacent cells through the same native placement validation as the UI.
        # NPC schedule movement makes a single hard-coded empty cell unreliable.
        for radius in range(2,6):
            for dx,dy in ((0,radius),(radius,0),(0,-radius),(-radius,0),(radius,radius),(-radius,-radius)):
                point=(center[0]+dx,center[1]+dy,0)
                if source is None:self.send('DBGC',shape,0,'1 '+' '.join(map(str,point)),expected=('ok','blocked'))
                else:self.send('DBGDUP',source,0,' '.join(map(str,point)),expected=('ok','blocked'))
                if self.p.head[5]=='ok':return created(self.p)[0]
        raise AssertionError('No native creature placement available near '+str(center))
    def wait(self,predicate,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.p.sync()
            if predicate():return
            time.sleep(.03)
        raise AssertionError(('native wait expired',self.p.head,self.p.frame[-1000:]))
    def book(self,id):
        self.p.send('USE',id);self.wait(lambda:int(self.p.head[9])==6)
        return int(self.p.head[10])
    def closebook(self):
        self.p.send('DISMISS',int(self.p.head[10]));audit['settle'](self.p)
    def cast(self,book,spell,target):
        token=self.book(book)
        result=self.p.send('BOOKCAST',token,spell)
        assert result=='ok',(result,self.p.head)
        self.wait(lambda:int(self.p.head[9])==4)
        self.p.send('TARGET',int(self.p.head[10]),target)
        audit['settle'](self.p)
    def note(self,text):self.evidence.append(text);print(text,flush=True)


def native():
    with session('developer-wand-disabled','Investigation',True) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);q=Checks(p)
        assert env['TRINSIC_DEBUG']=='0' and not lines(p,'DEVCAP')
        before={r[0]:r[1:3]+r[6:7] for r in p.rows if r[6] in (56,88,184,200)}
        for op,a,b,extra in [('DBGSUP',0,0,''),('DBGCAT',0,0,'- -'),('DBGINSPECT',56,0,''),
                             ('DBGTIME',12,0,''),('DBGWEATHER',2,0,''),('DBGI',802,0,'1 -1 0 0 0'),
                             ('DBGCLEAN',0,0,''),('DBGREFILL',56,0,''),('DBGSAVE',0,0,'')]:
            q.send(op,a,b,extra,expected='disabled')
        assert before=={r[0]:r[1:3]+r[6:7] for r in p.rows if r[6] in (56,88,184,200)}
        audit['movement'](p);p.close()
        (folder/'checks.json').write_text(json.dumps(['Developer capability and all tested commands absent/disabled; inventory unchanged.'],indent=2))

    with session('developer-wand-native','Investigation',True,{'TRINSIC_DEBUG':'1'}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);q=Checks(p)
        assert cap(p)[0]==1 and cap(p)[-1]==0
        q.send('DBGSAVE');assert (folder/'GAME00.U7').is_file()

        q.send('DBGCAT',0,0,'- -')
        total=int(lines(p,'DC')[0][1]);assert total>1000 and len(lines(p,'DI'))==40,total
        q.send('DBGCAT',0,0,'- '+hextext('garlic'))
        garlic=lines(p,'DI');assert garlic and all('garlic' in decode(r[4]).lower() for r in garlic),garlic
        category=garlic[0][3]
        q.send('DBGCAT',0,0,category+' -');assert all(r[3]==category for r in lines(p,'DI'))
        q.send('DBGCAT',1,0,'- '+hextext('rat'))
        rat_entries=lines(p,'DI');pages=int(lines(p,'DC')[0][3])
        for page in range(1,pages):
            q.send('DBGCAT',1,page,'- '+hextext('rat'));rat_entries.extend(lines(p,'DI'))
        assert any(int(r[1])==523 for r in rat_entries),rat_entries
        count=cap(p)[-1]
        for shape,frame,quantity in ((1024,0,1),(842,999,1),(842,0,0),(842,0,128)):
            q.send('DBGI',shape,frame,f'{quantity} -1 0 0 0',expected='invalid')
            assert cap(p)[-1]==count
        maximum=q.create(842,0,127);assert q.inspect(maximum)['quantity']==127
        q.send('DBGCLEAN',maximum)
        q.note('Full native catalogs, frame-specific name/category search, creature search and invalid creation validation passed.')

        tables=[r for r in p.rows if r[1] in (407,633,847,890,971,1000,1003,1018) and r[6]==0]
        surface=None
        for table in tables:
            q.send('DBGI',644,6,f'1 {table[0]} 0 0 0',expected=('ok','blocked'))
            if p.head[5]=='ok':surface=created(p)[0];break
        assert surface is not None,'No available native table surface'
        placed=q.inspect(surface)
        assert (placed['x'],placed['y'])==tuple(table[3:5]) and placed['z']>table[5] and placed['parent']==0
        count=cap(p)[-1]
        q.send('DBGDUP',surface,table[0],'0 0 0',expected='blocked')
        assert cap(p)[-1]==count
        surface_source=q.duplicate(surface)[0];q.send('DBGCLEAN',surface)
        duplicate_surface=q.duplicate(surface_source,table[0])[0]
        assert q.inspect(duplicate_surface)['z']==placed['z']
        q.send('DBGCLEAN',duplicate_surface);q.send('DBGCLEAN',surface_source)
        q.send('DBGI',644,6,'1 104 0 0 0',expected='blocked')
        q.note('Items and duplicates target original table surfaces at native top elevation; unsupported prop destinations are refused.')

        q.send('DBGSUP',0);bag=created(p)[0];supplies=created(p)[1:]
        assert len(supplies)==8 and q.inspect(bag)['shape']==802
        found=[q.inspect(id) for id in supplies]
        assert {(r['shape'],r['frame'],r['quantity'],r['parent']) for r in found}=={(842,i,30,bag) for i in range(8)}
        q.send('DBGSUP',0);duplicate_command=q.last;second=created(p);before_count=cap(p)[-1]
        assert p.raw(duplicate_command)=='ok'
        assert cap(p)[-1]==before_count and created(p)==second
        q.send('DBGCLEAN',second[0])
        inner=q.create(802,destination=bag);gold=q.create(644,6,17,inner)
        duplicate=q.duplicate(bag);copy=duplicate[0]
        assert len(duplicate)==11 and len(set(duplicate))==11 and not set(duplicate)&{bag,inner,gold,*supplies}
        copied=[q.inspect(id) for id in duplicate]
        assert len([r for r in copied if r['shape']==842 and r['quantity']==30])==8
        copied_inner=next(r for r in copied if r['shape']==802 and r['id']!=copy)
        copied_gold=next(r for r in copied if r['shape']==644)
        assert copied_inner['parent']==copy and copied_gold['parent']==copied_inner['id'] and copied_gold['quantity']==17
        before_count=cap(p)[-1]
        for protected in (56,184,824):q.send('DBGDUP',protected,-1,'0 0 0',expected=('blocked','invalid'))
        q.send('DBGDUP',bag,0,'1102 2217 0',expected='blocked')  # Closed east portcullis.
        assert cap(p)[-1]==before_count and q.inspect(gold)['parent']==inner
        chain=[q.create(802)]
        for _ in range(15):chain.append(q.create(802,destination=chain[-1]))
        deepest=q.duplicate(chain[0]);assert len(deepest)==16
        q.send('DBGCLEAN',deepest[0])
        chain.append(q.create(802,destination=chain[-1]))
        before_count=cap(p)[-1]
        q.send('DBGDUP',chain[0],-1,'0 0 0',expected='blocked')
        assert cap(p)[-1]==before_count
        for id in reversed(chain):q.send('DBGCLEAN',id)
        q.note('Eight reagent stacks, duplicate-command suppression, recursive contents and protected targets passed; blocked placement leaves original contents and created count unchanged.')

        q.send('DBGSUP',1);book=created(p)[0]
        token=q.book(book);assert len(lines(p,'L'))==72 and all(r[2]=='1' for r in lines(p,'L'))
        frozen=(p.head[3],p.head[12]);q.send('DBGCAT',0,0,'- '+hextext('bread'));q.inspect(56)
        assert (p.head[3],p.head[12])==frozen and int(p.head[9])==6
        q.send('DBGSUP',0,expected='busy',retry=False);assert int(p.head[9])==6
        assert p.send('BOOKSELECT',token,23)=='ok';q.closebook()
        copied_book=q.duplicate(book)[0];token=q.book(copied_book)
        assert len(lines(p,'L'))==72 and all(r[2]=='1' for r in lines(p,'L'))
        assert lines(p,'K')[0][-1]=='23';q.closebook()
        q.setstats(strength=30,dexterity=30,intelligence=30,combat=30,magic=30,hp=2,mana=30,xp=999999)
        all_reagents=supplies+[r['id'] for r in copied if r['shape']==842]
        before_reagents=sum(q.inspect(id)['quantity'] for id in all_reagents)
        q.cast(book,25,56)
        q.wait(lambda:next(int(r[2]) for r in lines(p,'C') if r[1]=='56')>2)
        assert q.actor()['mana']<30
        assert sum(q.inspect(id)['quantity'] for id in all_reagents)<before_reagents
        stone=q.create(330)
        q.inspect(stone);unmarked=lines(p,'DV')[0][2:]
        q.send('DBGREFILL',56);q.cast(book,34,stone)
        q.inspect(stone);marked=lines(p,'DV')[0][2:];assert marked!=unmarked,(unmarked,marked)
        copied_stone=q.duplicate(stone)[0];q.inspect(copied_stone)
        assert lines(p,'DV')[0][2:]==marked
        q.note('Read-only inspection/catalog preserve paused native clock/RNG and book prompt; learned spells/bookmark and marked-stone destination copy correctly; original casting consumes supplied reagents.')

        changed=q.setstats(strength=42,dexterity=25,intelligence=24,combat=45,magic=20,hp=7,mana=9,xp=98765,training=7,food=13)
        assert [changed[k] for k in ('strength','dexterity','intelligence','combat','magic','hp','mana','xp','training','food')]==[42,25,24,45,20,7,9,98765,7,13]
        values=[42,25,24,45,20,7,9,98765,7,13]
        for index,bad in ((0,0),(0,128),(1,31),(2,31),(3,0),(3,128),(4,31),(5,0),(6,31),(7,1000000),(8,256),(9,32)):
            invalid=values.copy();invalid[index]=bad
            q.send('DBGSET',56,extra=' '.join(map(str,invalid)),expected='invalid')
        unchanged=q.actor();assert all(changed[k]==unchanged[k] for k in ('strength','magic','xp','training'))
        changed=q.setstats(strength=5,magic=3);assert changed['hp']==5 and changed['mana']==3
        q.setstats(strength=30,hp=1,magic=30,mana=1)
        q.send('DBGREFILL',56);live_health(p)
        assert stats(p)['hp']==stats(p)['max_hp'] and stats(p)['mana']==stats(p)['max_mana']
        for condition,mask in ((0,0x80),(1,0x2000),(2,0x1000),(3,0x200),(4,0x4000)):
            q.send('DBGCOND',56,condition,'1');assert stats(p)['status']&mask
            if condition==3:assert stats(p)['effective_strength']==stats(p)['strength']-3
            if condition in (0,2):assert stats(p)['effective_dexterity']==0
            q.send('DBGCOND',56,condition,'0');assert not stats(p)['status']&mask
        q.send('DBGCOND',56,5,'1');assert inspected(p)['flags']&1
        q.send('DBGCOND',56,5,'0');assert not inspected(p)['flags']&1
        q.send('DBGCOND',56,6,'1');assert stats(p)['extra_flags']&0x10
        q.send('DBGCOND',56,6,'0');assert not stats(p)['extra_flags']&0x10
        q.note('Absolute base-stat edits, atomic rejection, maxima clamping, refill and seven native condition controls passed.')

        day=cap(p)[3];q.send('DBGTIME',12,23);assert cap(p)[1:4]==[12,23,day]
        for weather in range(7):q.send('DBGWEATHER',weather);assert cap(p)[4]==weather
        q.send('DBGWEATHER',0)
        q.send('DBGTELEPORT',1090,2214,'0')
        avatar=next(r for r in p.rows if r[0]==56);iolo=next(r for r in p.rows if r[0]==184)
        assert max(abs(avatar[3]-1090),abs(avatar[4]-2214))<=2
        assert max(abs(iolo[3]-avatar[3]),abs(iolo[4]-avatar[4]))<12
        rat=q.creature(523,(1090,2214))
        assert q.inspect(rat)['shape']==523
        clone=q.creature(523,(1090,2214),source=rat)
        assert clone!=rat and q.inspect(clone)['shape']==523
        q.send('DBGCLEAN',clone)
        q.send('DBGINSPECT',clone,expected='invalid')
        fresh=q.creature(523,(1090,2214))
        q.send('DBGINSPECT',clone,expected='invalid');assert fresh!=clone
        q.note('Native clock/day, all original weather values, party teleport, fresh creature duplication and stale-ID rejection passed.')

        # A tracked bag must not erase original possessions placed inside it.
        q.setstats(strength=127,hp=127)
        guard=q.create(802);assert p.send('MOVE',104,guard)=='ok'
        q.send('DBGCLEAN',guard,expected='blocked')
        p.send('USE',guard);q.wait(lambda:int(p.head[8])==guard)
        assert q.inspect(104)['parent']==guard
        p.send('CLOSE')
        saved_reagents={(r['frame'],r['quantity']) for r in (q.inspect(id) for id in supplies)}
        old_generation=p.head[2];before=q.actor();q.send('DBGSAVE')
        digest=hashlib.sha256((folder/'GAME00.U7').read_bytes()).hexdigest()
        p.send('LOAD');assert cap(p)[-1]==0
        after=q.actor();assert all(before[k]==after[k] for k in ('strength','magic','xp','training'))
        # Native save buffers retain raw handles, but load deliberately resets
        # lifetime-qualified wire IDs. Reacquire through the new snapshot.
        loaded_bag=next(r[0] for r in p.rows if r[0]==(bag&0xffff) and r[1]==802)
        loaded_guard=next(r[0] for r in p.rows if r[0]==(guard&0xffff) and r[1]==802)
        assert any(r[0]==(rat&0xffff) and r[1]==523 for r in p.rows),'Generated creature was not preserved'
        assert q.inspect(loaded_bag)['shape']==802
        if loaded_bag!=bag:q.send('DBGINSPECT',bag,expected='invalid')
        p.send('USE',loaded_bag);q.wait(lambda:int(p.head[8])==loaded_bag)
        assert {(r[2],r[9]) for r in p.rows if r[6]==loaded_bag and r[1]==842}==saved_reagents
        p.send('CLOSE')
        p.send('USE',loaded_guard);q.wait(lambda:int(p.head[8])==loaded_guard)
        assert q.inspect(104)['parent']==loaded_guard;p.send('CLOSE')
        assert p.raw(f'{int(p.head[4])+1} {old_generation} DBGSUP 0 0')=='stale'
        assert cap(p)[-1]==0
        q.send('DBGCLEAN',loaded_bag,expected='blocked')
        audit['settle'](p);audit['movement'](p)
        q.note('Cleanup preserves untracked possessions; native save/load preserves edits and generated inventory, clears cleanup history and rejects stale-generation commands; movement recovers.')
        p.close();(folder/'checks.json').write_text(json.dumps({'checks':q.evidence,'save_sha256':digest,'catalog_total':total},indent=2)+'\n')


def resurrection():
    with session('developer-wand-resurrection','Investigation',True,{'TRINSIC_DEBUG':'1'}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);q=Checks(p)
        q.send('DBGTELEPORT',1090,2214,'0')
        q.setstats(strength=127,dexterity=30,intelligence=30,combat=127,hp=127)
        rat=q.creature(523,(1090,2214))
        q.setstats(rat,strength=1,dexterity=1,intelligence=1,combat=1,hp=1)
        gold=q.create(644,6,7,rat)
        old_bodies={r[0] for r in p.rows if r[1]==762}
        assert p.send('WAR',1)=='ok'
        assert p.send('USE',rat)=='using'
        q.wait(lambda:any(r[1]==762 and r[0] not in old_bodies for r in p.rows),seconds=35)
        body=next(r[0] for r in p.rows if r[1]==762 and r[0] not in old_bodies)
        p.send('WAR',0);audit['settle'](p)
        assert q.inspect(gold)['parent']==body
        corpse_info=q.inspect(body)
        (folder/'corpse.json').write_text(json.dumps({'corpse':corpse_info,'rat_id':rat,'gold':q.inspect(gold)},indent=2)+'\n')
        q.send('DBGDUP',body,-1,'0 0 0',expected=('blocked','invalid'))
        q.send('DBGCLEAN',rat,expected='blocked')
        assert q.actor(rat)['status']&0x8000 and q.inspect(gold)['parent']==body
        tracked_count=cap(p)[-1]
        q.send('DBGRES',body)
        assert cap(p)[-1]==tracked_count
        q.wait(lambda:any(r[0]==rat and r[1]==523 for r in p.rows))
        actor=q.actor(rat);assert actor['hp']>0 and not actor['status']&0x8000
        assert q.inspect(gold)['parent']==rat
        q.send('DBGRES',gold,expected=('blocked','invalid'));assert q.inspect(gold)['parent']==rat
        audit['movement'](p)
        q.note('Original combat creates an identity-linked rat corpse; duplicate is rejected; native resurrection restores actor and possessions; invalid resurrection preserves its target.')
        p.close();(folder/'checks.json').write_text(json.dumps(q.evidence,indent=2)+'\n')


def copy_integration():
    source=ROOT/'runs/developer-wand-native/GAME00.U7'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    run='developer-wand-copy-'+str(time.time_ns())
    folder=copy_test_save('developer-wand-native',run)
    assert hashlib.sha256((folder/'GAME00.U7').read_bytes()).hexdigest()==before
    with session(run,'Investigation',False,{'TRINSIC_DEBUG':'1'}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);q=Checks(p)
        assert cap(p)[-1]==0
        original=q.actor();q.setstats(xp=12345,training=11)
        q.send('DBGSAVE');p.send('LOAD');after=q.actor()
        assert after['xp']==12345 and after['training']==11
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        try:copy_test_save('developer-wand-native',run)
        except FileExistsError:pass
        else:raise AssertionError('Existing test run was overwritten')
        p.close();(folder/'checks.json').write_text(json.dumps({'source_sha256':before,'source_stats':original,'copy_stats':after},indent=2)+'\n')
    (source.parent/'copy-check.json').write_text(json.dumps({'copy_run':run,'source_sha256':before,'independent_save_verified':True},indent=2)+'\n')
    print('Copied native world resumes and saves independently; source checkpoint and existing test run are preserved.',flush=True)


def limits():
    with session('developer-wand-limits','Investigation',True,{'TRINSIC_DEBUG':'1'}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);q=Checks(p)
        root=q.create(802);q.create(644,6,1,root)
        # Copy into the source container: each detached copy is distinct, not a cycle.
        # Eight doublings create exactly 512 objects without a flat 500-item UI fixture.
        for _ in range(8):q.duplicate(root,root)
        assert cap(p)[-1]==512
        clone=q.duplicate(root);assert len(clone)==512 and len(set(clone))==512
        extra=q.create(644,6,1,root);count=cap(p)[-1]
        q.send('DBGDUP',root,-1,'0 0 0',expected='blocked')
        assert '512' in message(p) and cap(p)[-1]==count
        q.send('DBGCLEAN',extra);q.send('DBGCLEAN',clone[0])
        assert cap(p)[-1]==512
        q.note('Exactly 512 native objects duplicate successfully; 513 objects are rejected before allocation.')
        allocated=[]
        for _ in range(64):
            before=cap(p)[-1]
            q.send('DBGDUP',root,-1,'0 0 0',expected=('ok','blocked'))
            if p.head[5]=='blocked':
                assert 'records' in message(p).lower(),message(p)
                assert cap(p)[-1]==before
                break
            assert len(created(p))==512
            allocated.append(created(p)[0])
        else:raise AssertionError('Allocation boundary was not reached within 32768 test objects')
        assert allocated
        for _ in range(3):
            q.send('DBGDUP',root,-1,'0 0 0',expected='blocked');assert cap(p)[-1]==before
        q.send('DBGCLEAN',allocated.pop());assert cap(p)[-1]==before-512
        recovered=q.duplicate(root);assert len(recovered)==512 and cap(p)[-1]==before
        q.send('DBGCLEAN',0);assert cap(p)[-1]==0
        q.note('Native record exhaustion refuses complete copies without partial objects; repeated refusal leaks no capacity; freeing one tree allows the same copy again; cleanup returns to zero.')
        p.close();(folder/'checks.json').write_text(json.dumps(q.evidence,indent=2)+'\n')


def equipment():
    with session('developer-wand-equipment','Investigation',True,{'TRINSIC_DEBUG':'1'}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);q=Checks(p)
        q.send('DBGTELEPORT',1090,2214,'0')
        # Original MONSTERS.DAT pirate equipment set 13 supplies native armor and weapons.
        pirate=q.creature(401,(1090,2214));original_ids=created(p)
        original={id&0xffff:q.inspect(id) for id in original_ids}
        assert len(original)>5
        source_stats=q.setstats(pirate,hp=1)
        q.send('DBGCOND',pirate,3,'1')
        clone=q.creature(401,(1090,2214),source=pirate);clone_ids=created(p)
        copied={id&0xffff:q.inspect(id) for id in clone_ids}
        assert len(copied)==len(original) and not original.keys()&copied.keys()
        signature=lambda data:Counter((r['shape'],r['frame'],r['quantity'],r['quality']) for r in data.values() if r['npc']<0)
        assert signature(original)==signature(copied)
        q.inspect(clone);target_stats=live_health(p)
        assert all(source_stats[k]==target_stats[k] for k in ('strength','dexterity','intelligence','combat','magic','hp','xp','training'))
        assert not target_stats['status']&0x7380
        source_npc=original[pirate&0xffff]['npc'];copy_npc=copied[clone&0xffff]['npc']
        assert source_npc!=copy_npc
        q.send('DBGSAVE')
        # NpcSaver::save writes packed 105-byte NPC records, four free-list bytes,
        # then twelve native equipment handles per actor. Read the actual save,
        # since non-party equipment is intentionally absent from normal E rows.
        data=members(folder/'GAME00.U7')['U7NBUF.DAT']
        count,remainder=divmod(len(data)-4,105+24);assert remainder==0
        def slots(npc,objects):
            handles=struct.unpack_from('<12H',data,count*105+4+npc*24)
            return [None if handle==0 else (objects[handle]['shape'],objects[handle]['frame']) for handle in handles]
        original_slots=slots(source_npc,original);copied_slots=slots(copy_npc,copied)
        assert any(original_slots) and original_slots==copied_slots,(original_slots,copied_slots)
        q.send('DBGCLEAN',0);assert cap(p)[-1]==0
        q.note('Original pirate equipment and every occupied native slot duplicate with fresh actor/item identities and copied base attributes; transient curse is cleared; cleanup succeeds.')
        p.close();(folder/'checks.json').write_text(json.dumps({'checks':q.evidence,'original_slots':original_slots,'copied_slots':copied_slots},indent=2)+'\n')


def client():
    run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    commands=[
        'WAIT 1000','WANDCHECK','WANDOPEN','WAIT 300','WANDTAB 0','CAPTURE',
        'WANDCLICK Reagent bag: 30 of each','WAIT 350','WANDRESULT ok','WANDCREATED 9',
        'WANDUSEROOT','WAIT 350','CAPTURE','CLOSE','WAIT 150',
        'WANDCLICK Cleanup','WANDCLICK Remove all created objects','WAIT 350','WANDRESULT ok','WANDCREATED 0',
        'WANDCLICK Items','WAIT 200','WANDTAB 1','WANDFIELD Search bag','WANDTYPING',
        'ENTER','WANDWAITCAT','WANDSELECT 802 0','WANDCLICK Preview and create','CAPTURE',
        'WANDCLICK Create in backpack','WAIT 500','WANDRESULT ok','WANDCREATED 1',
        'WANDCLICK Creatures','WANDWAITCAT','WANDTAB 2','WANDFIELD Search horse','ENTER','WANDWAITCAT',
        'WANDSELECT 727 0','WANDCLICK Preview and create','CAPTURE',
        'WANDCLICK Inspect','WANDCLICK Avatar','WAIT 250','WANDTAB 3','CAPTURE',
        'WANDCLICK Edit actor stats','WAIT 200','WANDTAB 4','WANDFIELD HP 3','WANDCLICK Apply stats','WAIT 350','WANDRESULT ok','CAPTURE',
        'WANDCLICK Supplies','WANDCLICK Refill Avatar HP and mana','WAIT 350','WANDRESULT ok',
        'WANDCLICK World','WANDTAB 5','WANDFIELD Hour 12','WANDFIELD Minute 0','WANDCLICK Set time','WAIT 300','WANDRESULT ok','CAPTURE',
        'WANDCLICK Save current world','WAIT 300','WANDRESULT ok',
        'WANDCLICK Cleanup','WANDTAB 6','CAPTURE',
        # Cancellation before selecting a source and after selecting a source creates nothing.
        'WANDCLICK Duplicate','WAIT 100','TARGETING 1','TARGET 0','WAIT 100','TARGETING 0','WANDCREATED 1',
        'WANDCLICK Duplicate','WAIT 100','TARGET 104','WAIT 100','TARGETING 1','TARGET 0','WAIT 100','TARGETING 0','WANDCREATED 1',
        # The original spell prompt owns targeting while the modeless toolbox stays open.
        'WANDCLICK Supplies','WANDCLICK Fully learned spellbook','WAIT 350','WANDRESULT ok','WANDCREATED 2',
        'WANDUSELAST','WAIT 350','MODAL 6','BOOKDOUBLE 72 40','WAIT 350','MODAL 4','TARGETING 1',
        'WANDCLICK Inspect','WANDCLICK Select target','WAIT 150','MODAL 4','TARGETING 1','TARGET 0','WAIT 450','MODAL 0',
        'RECONNECT','WAIT 400','WANDCHECK','WANDOPEN','WAIT 150','WANDCREATED 2',
        'LOAD','WAIT 500','WANDCHECK','WANDOPEN','WAIT 150','WANDCREATED 0','CAPTURE',
        'ESCAPE','WAIT 200','STEP 0','WAIT 300','STEP 2','WAIT 300','STEP 4','WAIT 300','STEP 6','WAIT 300','WALKCHECK','EXIT',
    ]
    receipt=run('developer-wand-client','Investigation',commands,True,scenario='wand',extra={'TRINSIC_DEBUG':'1'})
    assert any('DBGI 802 0' in event and ' ok ' in event for event in receipt['events']),receipt['events']
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--client',action='store_true');parser.add_argument('--resurrection',action='store_true');parser.add_argument('--limits',action='store_true');parser.add_argument('--equipment',action='store_true');args=parser.parse_args()
    if args.client:client()
    elif args.resurrection:resurrection()
    elif args.limits:limits()
    elif args.equipment:equipment()
    else:native();resurrection();copy_integration();limits();equipment()
    print('Developer Wand qualification passed.',flush=True)
