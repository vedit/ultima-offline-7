"""Exercise original spellbook controls with a synthetic learned-spell book."""
import runpy
import time
from pathlib import Path
from play import session

audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
Pipe=audit['BoundedPipe']

def wait(p,mode):
    end=time.monotonic()+8
    while time.monotonic()<end:
        p.sync()
        if int(p.head[9])==mode:return
        time.sleep(.03)
    raise AssertionError(p.head)

with session('spellbook-controls','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=Pipe(env['TRINSIC_PIPE'],host)
    book=int(p.send('AUDITBOOK')[5:])
    assert next(r for r in p.rows if r[0]==book)[11]&4, 'Native openable items must advertise USE'
    p.send('USE',book);wait(p,6)
    token=int(p.head[10])
    spells=[l.split() for l in p.frame.splitlines() if l.startswith('L ')]
    assert len(spells)==72 and all(s[2]=='1' for s in spells)
    assert [int(s[1]) for s in spells]==list(range(72))
    assert bytes.fromhex(spells[0][5]).decode()=='Awaken'
    assert spells[0][4]=='0' and int(spells[8][4])==0x38
    assert p.raw('0 0 SCREEN')=='ERROR no-display\n', 'Book must not stream U7 raster UI'
    assert p.send('BOOKSELECT',token,72)=='invalid'
    assert p.send('BOOKSELECT',token-1,8)=='modal'
    assert p.send('BOOKSELECT',token,8)=='ok'
    assert p.send('BOOKCAST',token,8)=='refused'
    assert int(p.head[9])==6 and int(p.head[10])==token
    p.send('DISMISS',token);audit['settle'](p);audit['movement'](p)
    assert p.send('SAVE')=='ok'
    assert p.send('LOAD')=='ok'
    p.send('USE',book);wait(p,6)
    assert next(l for l in p.frame.splitlines() if l.startswith('K ')).endswith(' 8')
    token=int(p.head[10]);p.send('BOOKCAST',token,0);wait(p,4)
    p.send('TARGET',int(p.head[10]),0);audit['settle'](p);audit['movement'](p)
    p.send('USE',book);wait(p,6)
    p.send('BOOKCAST',int(p.head[10]),0);wait(p,4)
    p.send('TARGET',int(p.head[10]),56);audit['settle'](p)
    assert any('An Zu' in bytes.fromhex(l.split()[3]).decode() for l in p.frame.splitlines() if l.startswith('B '))
    audit['movement'](p)
    # A sparse learned-spell book cannot cast a spell absent from original data.
    sparse=int(p.send('AUDITBOOK',1)[5:])
    p.send('USE',sparse);wait(p,6)
    assert sum(l.split()[2]=='1' for l in p.frame.splitlines() if l.startswith('L '))==1
    assert p.send('BOOKCAST',int(p.head[10]),8)=='invalid'
    p.send('DISMISS',int(p.head[10]));audit['settle'](p);audit['movement'](p)
    p.close()
    print('Native book data, validation, bookmark, resource refusal, casting and recovery passed.',flush=True)

run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
run('spellbook-client','Investigation',[
    'WAIT 900','BOOKCREATE','BOOKOPEN','WAIT 500','MODAL 6','CAPTURE',
    # UO circle tabs and stock page corners; circle eight includes all 72 U7 entries.
    'BOOKCLICK 61 181','WAIT 400','BOOKCHECK 2 0','CAPTURE',
    'BOOKCLICK 335 181','WAIT 400','BOOKCHECK 5 0','CAPTURE',
    'BOOKCLICK 236 58','WAIT 650','BOOKCHECK 38 0','CAPTURE',
    'BOOKDOUBLE 55 13','WAIT 400','BOOKCHECK 1 0','CAPTURE',
    # Cantrip index -> native detail page, then minimize / restore.
    'BOOKCLICK 72 58','WAIT 650','BOOKCHECK 6 0','CAPTURE',
    'BOOKCLICK 12 106','WAIT 300','BOOKCHECK 6 1','CAPTURE',
    'BOOKDOUBLE 20 20','WAIT 300','BOOKCHECK 6 0',
    'ESCAPE','WAIT 400','MODAL 0','BOOKOPEN','WAIT 400','BOOKCHECK 6 0',
    # Cast through the native UO label double-click handler, then cancel the U7 target.
    'BOOKDOUBLE 72 40','WAIT 400','MODAL 4','TARGETING 1','TARGET 0','WAIT 500','MODAL 0',
    'BOOKOPEN','WAIT 400','BOOKRIGHT 190 90','WAIT 400','MODAL 0',
    'STEP 0','WAIT 500','WALKCHECK','EXIT',
],True,scenario='book',extra={'TRINSIC_PREPARE':'interaction-audit'})
