"""Native event qualification; real Usecode in disposable saves, never player saves."""
import argparse
import json
import runpy
import time
from pathlib import Path
from play import session, ROOT

audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
Pipe=audit['BoundedPipe']

def collect(p,seconds=2.5,target=56,position=None,cancel=False):
    events={};missiles={};fields={};prompts=[];tokens=set()
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        p.sync()
        for line in p.frame.splitlines():
            if line.startswith('F '):events[int(line.split()[1])]=line
            elif line.startswith('FM '):missiles[line]=True
        for row in p.rows:
            if row[1] in (895,900,902,768):fields[row[0]]=row
        mode,token=map(int,p.head[9:11])
        if mode and token not in tokens:
            tokens.add(token);prompts.append(mode)
            if mode==4:
                if position and not cancel:p.raw(f'{int(p.head[4])+1} {p.head[2]} TARGETPOS {token} {position[0]} {position[1]} 0')
                else:p.send('TARGET',token,0 if cancel else target)
            elif mode in (5,6):p.send('DISMISS',token)
            elif mode in (1,2):
                bye=next((i for i,s in enumerate(p.choices) if s.lower() in ('bye','no')),0)
                p.send('ANSWER',token,bye)
        time.sleep(.025)
    return dict(events=list(events.values()),missiles=list(missiles),fields=list(fields.values()),prompts=prompts,
                rows=p.rows,header=p.head,actors=[l for l in p.frame.splitlines() if l.startswith('C ')])

def kinds(result):return [l.split()[3] for l in result['events']]
def state(p,who,hp,status=8):
    assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITFXSTATE {who} {hp} {status}')=='ok'

def native(all_spells=False):
    results={}
    with session('spell-effects-native','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host)
        assert p.send('SAVE')=='ok'
        def cast(spell,**kwargs):
            assert p.send('AUDITCAST',spell)=='ok'
            result=collect(p,**kwargs);results[str(spell)]=result;return result
        # The healing effect is emitted after the native delayed HP change.
        state(p,56,2)
        result=cast(25)
        assert kinds(result).count('heal')==1,result
        assert next(r for r in result['actors'] if r.split()[1]=='56').split()[2]=='10',result['actors']
        # Repeated snapshots are read-only and retain the same event identities.
        ids={l.split()[1] for l in result['events']}
        for _ in range(3):
            p.sync();assert {l.split()[1] for l in p.frame.splitlines() if l.startswith('F ')}<=ids
        p.send('LOAD');state(p,56,2)
        result=cast(25,cancel=True)
        assert 'heal' not in kinds(result),result
        p.send('LOAD');state(p,56,18,8|0x2000|0x1000)
        result=cast(9)
        assert kinds(result).count('cure')==1,result
        p.send('LOAD');result=cast(21)
        assert kinds(result).count('protect')==1,result
        p.send('LOAD');result=cast(45)
        assert kinds(result).count('hide')==1,result
        p.send('LOAD');result=cast(51,seconds=1.5)
        bursts=[l.split() for l in result['events'] if l.split()[3]=='flamestrike']
        fire={r[0]:r for r in result['fields'] if r[1]==895}
        assert len(bursts)>=2 and len({b[5] for b in bursts})==len(bursts),(bursts,fire)
        assert all(int(b[5]) in fire and list(map(int,b[6:9]))==fire[int(b[5])][3:6] for b in bursts),(bursts,fire)
        p.send('LOAD');result=cast(33,target=864,seconds=4)
        assert kinds(result).count('lightning')==1,result
        p.send('LOAD');result=cast(32,seconds=4)
        assert 'summon' in kinds(result),result
        p.send('LOAD');result=cast(65,seconds=3)
        assert result['missiles'] and all(l.split()[2]=='639' for l in result['missiles']),result
        # Loading clears transient event history, without emitting new success effects.
        p.send('LOAD');assert not any(l.startswith(('F ','FM ')) for l in p.frame.splitlines())
        if all_spells:
            for spell in range(72):
                p.send('LOAD')
                state(p,56,6)
                result=cast(spell,seconds=2.5)
                print(f'{spell:02}: {kinds(result)}; missiles={len(result["missiles"])}; fields={len(result["fields"])}',flush=True)
                assert int(result['header'][9])==0,(spell,result['header'])
        p.close()
        (folder/'events.json').write_text(json.dumps(results,indent=2))
    return results

def client():
    run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    return run('spell-effects-client','Investigation',[
        'WAIT 900','FXART','FXSTATE 56 2 8','FXCAST 25','WAIT 350','TARGET 56',
        'FXWAIT heal 1','CAPTURE','FXCOUNT heal 1','DUP','RECONNECT','FXCOUNT heal 1',
        'WAIT 1200','FXCAST 51','FXWAIT flamestrike 2','CAPTURE','WAIT 450','CAPTURE','WAIT 6500','CAPTURE',
        'STEP 0','WAIT 400','STEP 2','WAIT 400','STEP 4','WAIT 400','STEP 6','WAIT 400','WALKCHECK','EXIT',
    ],True,scenario='effects',extra={'TRINSIC_PREPARE':'interaction-audit'})

def parity():
    """Compare native outcomes with the presentation observer enabled and disabled."""
    outcomes={}
    for enabled in ('0','1'):
        with session('spell-effects-parity-'+enabled,'Investigation',True,
                     {'TRINSIC_PREPARE':'interaction-audit','TRINSIC_EFFECTS':enabled}) as (folder,env,host):
            p=Pipe(env['TRINSIC_PIPE'],host);p.send('SAVE');checks={}
            for spell,hp,status,expected in ((25,2,0,'heal'),(9,18,0x3000,'cure'),(21,18,0,'protect'),(45,18,0,'hide')):
                p.send('LOAD');state(p,56,hp,status);p.send('AUDITCAST',spell)
                result=collect(p)
                actor=next(l.split() for l in result['actors'] if l.split()[1]=='56')
                # HP, spell-condition flags and native invisibility; no wall-clock fields.
                checks[str(spell)]=[int(actor[2]),int(actor[5])&0x7380,int(actor[-1])]
                assert (expected in kinds(result))==(enabled=='1'),result
                if enabled=='0':assert not result['events'] and not result['missiles']
            p.close();outcomes[enabled]=checks
            (folder/'outcomes.json').write_text(json.dumps(checks,indent=2))
    assert outcomes['0']==outcomes['1'],outcomes
    return outcomes

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--all',action='store_true');parser.add_argument('--client',action='store_true');parser.add_argument('--parity',action='store_true')
    args=parser.parse_args()
    if args.parity:parity()
    elif args.client:client()
    else:native(args.all)
    print('Spell-effect qualification passed.',flush=True)
