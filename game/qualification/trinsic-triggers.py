"""Census original Trinsic placements and qualify native dialogue/guard branches.

The census is read-only. Branch cases use isolated saves and observer positioning;
they do not write quest flags, replace Usecode, or claim continuous walking proof.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct
import sys
import time

from play import ROOT, session, copy_test_save
from reference import GAME, members
from baseline import actor
from install_paths import ATLAS_OUTPUT
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from u7uo.story_seed import area_eggs

SOURCE = ROOT/'native/Black Gate/game/usecode'
KIND = {1:'creature', 2:'music', 3:'sound', 4:'speech', 5:'Usecode',
        6:'missile', 7:'teleport', 8:'weather', 10:'button'}
BOUNDS = (928, 2080, 1120, 2352)


def census():
    static = GAME/'STATIC'
    seed = (static/'INITGAME.DAT').read_bytes()
    types = (static/'TFA.DAT').read_bytes()
    link = (static/'LINKDEP1').read_bytes()
    symbols = {int(number): name for name, number in re.findall(
        r'usableindex #([\w]+) (\d+);', (SOURCE/'usecode.uh').read_text())}
    refs = list(csv.DictReader((ATLAS_OUTPUT/'references.csv').open(encoding='utf-8-sig')))
    art = {tuple(map(int, line.split()[:2])): int(line.split()[2])
           for line in (ROOT/'town-battlement-data/graphics.tsv').read_text().splitlines()}
    eggs = area_eggs(seed, types, hashlib.sha256(seed).hexdigest(), BOUNDS[:2],
                     BOUNDS[2]-BOUNDS[0], BOUNDS[3]-BOUNDS[1])
    triggers = []
    for egg in eggs:
        result = {key: egg[key] for key in ('position','member','offset','kind_id','criteria',
                  'distance','probability','data1','data2','once','repeat','nocturnal')}
        result['kind'] = KIND[egg['kind_id']]
        if egg['kind_id'] == 5:
            result['routine'] = symbols.get(egg['data2'], f"function_{egg['data2']:04x}")
        if egg['kind_id'] == 1:
            result.update(shape=egg['data2']&1023, frame=egg['data2']>>10)
        if egg['kind_id']==7 and egg['data1']&255==255:
            region=egg['data1']>>8
            x=(region%12)*256+(egg['data2']&255)
            y=(region//12)*256+(egg['data2']>>8)
            result.update(destination=[x,y,0],destination_in_town=BOUNDS[0]<=x<BOUNDS[2] and BOUNDS[1]<=y<BOUNDS[3])
        triggers.append(result)
    npcs = []
    families = {}
    for ref in refs:
        shape, frame = int(ref['shape']), int(ref['frame'])
        if ref['layer'] in ('Actor','Scheduled visitor'):
            slot = int(re.search(r'NPC (\d+)', ref['owner'])[1])
            function = 1024+slot if slot<256 else shape
            npcs.append(dict(name=ref['owner'], shape=shape, slot=slot,
                             position=[int(ref['x']),int(ref['y']),int(ref['lift'] or 0)],
                             routine=symbols.get(function, 'player' if slot==0 else 'unknown')))
        if ref['layer'] not in ('World object','Fixed','Contained'):
            continue
        scripted = shape*4+4<=len(link) and struct.unpack_from('<H',link,shape*4+2)[0]!=65535
        container = types[shape*3+1]&15 == 6
        if not (scripted or container):
            continue
        family = families.setdefault(shape, dict(shape=shape, scripted=scripted, container=container,
                                    routine=symbols.get(shape), placements=0, frames=set(), unmapped_frames=set()))
        family['placements'] += 1
        family['frames'].add(frame)
        if not art.get((shape,frame)):
            family['unmapped_frames'].add(frame)
    for family in families.values():
        family['frames'] = sorted(family['frames'])
        family['unmapped_frames'] = sorted(family['unmapped_frames'])
    assert not [f for f in families.values() if f['unmapped_frames']], 'Placed interactive frames lack UO mapping entries'
    required_functions={egg['data2'] for egg in eggs if egg['kind_id']==5}
    required_functions.update(1024+n['slot'] if n['slot']<256 else n['shape'] for n in npcs if n['slot'])
    assert all(function*4+4<=len(link) and struct.unpack_from('<H',link,function*4+2)[0]!=65535
               for function in required_functions), 'A placed script/NPC has no native Usecode dispatch entry'
    source_names = {e['routine'] for e in triggers if 'routine' in e}
    source_names |= {n['routine'] for n in npcs}
    source_names |= {'LaunchShip_i','TurnWinch_i','BargeType_i','StablesKeyEgg_i','TrinsicCleanupEgg_i'}
    source_files = [SOURCE/(name+'.use') for name in sorted(source_names)]
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files if p.exists()}
    result = dict(bounds=list(BOUNDS), inputs={name:hashlib.sha256((static/name).read_bytes()).hexdigest()
                  for name in ('INITGAME.DAT','USECODE','LINKDEP1','TFA.DAT')},
                  source_scripts=hashes, npc_count=len(npcs), npcs=npcs,
                  trigger_count=len(triggers), trigger_kinds=dict(Counter(t['kind'] for t in triggers)),
                  triggers=triggers, item_family_count=len(families), item_families=list(families.values()))
    assert len(npcs)==17 and len(triggers)==48 and len(families)==65, 'Original Trinsic census changed; review scope'
    return result


def branches(name, completed_run):
    audit = runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
    results = []

    def exercise(folder, env, host, finished):
        p = audit['BoundedPipe'](env['TRINSIC_PIPE'], host)
        assert p.send('SAVE')=='ok'
        seed = members(folder/'GAME00.U7')

        def visit(slot):
            x,y,z = actor(seed, slot)['xyz']
            assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT {x+1} {y} {z}')=='ok'
            audit['settle'](p)
            npc = next(r for r in p.rows if r[7]==slot)
            # A schedule can have moved the speaker since the save.
            assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT {npc[3]+1} {npc[4]} {npc[5]}')=='ok'
            return next(r for r in p.rows if r[7]==slot)

        def talk(slot, topics, *, strict=False):
            npc = visit(slot)
            assert p.send('USE',npc[0])=='using'
            pending=list(topics); chosen=[]; texts=[]; visited=False
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                time.sleep(.025);p.sync()
                mode,token=map(int,p.head[9:11])
                if not mode:
                    if visited:break
                    continue
                visited=True
                texts.extend(bytes.fromhex(l[2:]).decode('cp437') for l in p.frame.splitlines() if l.startswith('T '))
                if mode==1:p.send('ANSWER',token,0)
                elif mode==2:
                    choice=next((word for word in pending if word in p.choices),None)
                    if choice is None:
                        choice=next((word for word in ('bye','No','Avatar','hexen','Yes') if word in p.choices),None)
                    assert choice is not None,(slot,p.choices,pending,texts[-1:])
                    if choice in pending:pending.remove(choice)
                    chosen.append(choice);p.send('ANSWER',token,p.choices.index(choice))
                else:raise AssertionError(('Unexpected prompt',slot,mode,pending))
            else:raise TimeoutError(('Conversation',slot,pending))
            if strict:assert not pending,(slot,pending,chosen)
            audit['settle'](p)
            print('NPC',slot,chosen,flush=True)
            return chosen,' '.join(texts)

        try:
            if not finished:
                # All placed/scheduled town speakers, including both generic gate guards.
                for slot in (1,2,11,12,13,14,16,17,18,19,20,21,22,236,257,258):
                    assert p.send('LOAD')=='ok';p.sync()
                    chosen,words=talk(slot,['name','job','murder','bye'])
                    assert words,(slot,chosen)
                    audit['movement'](p)
                    results.append(dict(case='town-speaker',npc=slot,choices=chosen,returned_control=True))
                for slot in (14,257,258):
                    assert p.send('LOAD')=='ok';p.sync()
                    chosen,words=talk(slot,['job',*(['ship'] if slot==14 else []),'password','Please','bye'],strict=True)
                    assert 'password' in words.lower()
                    assert p.send('SAVE')=='ok'
                    flags=members(folder/'GAME00.U7')['FLAGINIT']
                    assert flags[66] and not flags[61]
                    gates=[r for r in p.rows if r[1] in (271,272)]
                    assert gates and all(r[5]==0 for r in gates),gates
                    results.append(dict(case='password-refused',npc=slot,gates=[r[:6] for r in gates]))
            else:
                # North/south exits from a genuinely completed investigation checkpoint.
                for slot in (257,258):
                    assert p.send('LOAD')=='ok';p.sync()
                    chosen,words=talk(slot,['password','Blackbird'],strict=True)
                    end=time.monotonic()+8
                    while time.monotonic()<end:
                        p.sync();gates=[r for r in p.rows if r[1] in (271,272)]
                        if gates and all(r[5]>0 for r in gates):break
                        time.sleep(.05)
                    assert gates and all(r[5]>0 for r in gates),gates
                    results.append(dict(case='password-accepted',npc=slot,gates=[r[:6] for r in gates]))
                assert p.send('LOAD')=='ok';p.sync()
                chosen,words=talk(2,['job','orphan','Father','Fellowship','tests','Klog','gold','medallion','scroll','bye'])
                assert 'Fellowship' in chosen,chosen
                assert p.send('SAVE')=='ok'
                assert members(folder/'GAME00.U7')['FLAGINIT'][63]
                chosen,words=talk(16,['murder','Fellowship','Christopher','argument','companions','gold','medallion','scroll','Crown Jewel','Hook','bye'])
                assert all(t in chosen for t in ('companions','gold','medallion','scroll','Crown Jewel','Hook')),chosen
                assert p.send('SAVE')=='ok' and members(folder/'GAME00.U7')['FLAGINIT'][65]
                results.append(dict(case='Fellowship-leads',choices=chosen,flags=[63,65]))
                chosen,words=talk(2,['leave','Yes','wait here'],strict=True)
                assert p.send('SAVE')=='ok'
                saved=members(folder/'GAME00.U7');spark=actor(saved,2)['handle']
                party=saved['PARTY'];assert spark not in struct.unpack_from('<8H',party)[:party[16]]
                chosen,words=talk(2,['join','bye'],strict=True)
                assert p.send('SAVE')=='ok'
                party=members(folder/'GAME00.U7')['PARTY']
                assert spark in struct.unpack_from('<8H',party)[:party[16]]
                results.append(dict(case='Spark-leave-rejoin',native_party=True))
        finally:
            (folder/'trigger-branches.json').write_text(json.dumps(results,indent=2)+'\n')
            p.close()

    with session(name+'-speakers','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as args:
        exercise(*args,False)
    # A fresh destination is required; copy_test_save never overwrites an existing run.
    copy_test_save(completed_run,name+'-completed')
    with session(name+'-completed','Investigation',False,{'TRINSIC_PREPARE':'interaction-audit'}) as args:
        exercise(*args,True)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--branches', action='store_true')
    parser.add_argument('--run', default='trinsic-trigger-branches-'+time.strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--completed-run', default='trigger-opening-20261115')
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    result=census()
    if args.branches:result['branch_tests']=branches(args.run,args.completed_run)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('npc_count','trigger_count','trigger_kinds','item_family_count')},indent=2))
