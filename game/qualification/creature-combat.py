"""Verify creature visibility and native combat authority in a disposable save."""
import json,runpy,time
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('creature-combat','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
    result=p.send('AUDITCREATURE',523)
    assert result.startswith('creature-'),result
    rat=int(result[9:]);row=lambda:next(r for r in p.rows if r[0]==rat)
    assert row()[1]==523 and row()[7]>=256,row()
    def state(id):return next(l.split() for l in p.frame.splitlines() if l.startswith(f'C {id} '))
    before=int(state(rat)[2]); assert before>0,(row(),state(rat))
    assert p.send('WAR',1)=='ok'
    assert p.send('USE',rat)=='using'
    events=[];end=time.monotonic()+20
    while time.monotonic()<end:
        time.sleep(.05);p.sync()
        if not any(r[0]==rat for r in p.rows):break
        events.append([row()[2],*map(int,state(rat)[2:6])])
        if int(state(rat)[2])<before:break
    assert events and min(e[1] for e in events)<before,events[-10:]
    assert any(int(l.split()[4]) for l in p.frame.splitlines() if l.startswith('C '))
    p.send('WAR',0);audit['settle'](p)
    audit['movement'](p)
    (folder/'combat.json').write_text(json.dumps({'rat':rat,'initial_health':before,'observations':events},indent=2))
    p.close();print('Spawned rat exported; original attack changed native health; peace and movement passed.',flush=True)
run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
run('creature-combat-client','Investigation',[
    'WAIT 1000','CREATUREART','CREATURE 727','WAIT 400','CREATURECHECK 200','CAPTURE',
    'CREATURE 523','WAIT 400','CREATURECHECK 238','CAPTURE',
    'ATTACKCREATURE','WAIT 2200','ACTIONCHECK','CAPTURE','PEACE','WAIT 400','STEP 4','WAIT 400','WALKCHECK','EXIT'
],True,scenario='creatures',extra={'TRINSIC_PREPARE':'interaction-audit'})
