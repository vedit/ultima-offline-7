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
    result=p.send('AUDITBOOK')
    assert result.startswith('book-'),result
    book=int(result[5:])
    p.send('USE',book)
    wait(p,5)
    assert 'U controls ' in p.frame
    frame=p.raw('0 0 SCREEN').split()
    from PIL import Image
    colors=bytes.fromhex(frame[3]);pixels=bytes.fromhex(frame[4])
    img=Image.frombytes('P',(int(frame[1]),int(frame[2])),pixels)
    img.putpalette(bytes(round(c*255/63) for c in colors));img.convert('RGB').resize((640,400)).save(folder/'book.png')
    def click(x,y,action=1):
        token=int(p.head[10])
        ox,oy=map(int,next(l for l in p.frame.splitlines() if l.startswith('U controls ')).split()[2:])
        x+=ox;y+=oy
        assert p.raw(f'{int(p.head[4])+1} {p.head[2]} VIEWCLICK {token} {x} {y} {action}')=='ok'
        end=time.monotonic()+8
        while time.monotonic()<end:
            p.sync()
            if int(p.head[9])==5 and int(p.head[10])!=token:break
            time.sleep(.03)
        else:raise AssertionError(('Click did not return',p.head))
        print((folder/'host.log').read_text().splitlines()[-1],flush=True)
    click(133,23)
    assert 'spellbook page=1' in (folder/'host.log').read_text()
    click(75,34)
    assert 'selected=8' in (folder/'host.log').read_text()
    click(75,34,2)
    assert 'interaction refused' in (folder/'host.log').read_text(), 'Missing-reagent/mana refusal must remain original'
    p.send('DISMISS',int(p.head[10]))
    audit['settle'](p);audit['movement'](p)
    p.send('USE',book);wait(p,5)
    click(40,23)
    token=int(p.head[10])
    ox,oy=map(int,next(l for l in p.frame.splitlines() if l.startswith('U controls ')).split()[2:])
    p.raw(f'{int(p.head[4])+1} {p.head[2]} VIEWCLICK {token} {75+ox} {34+oy} 2')
    wait(p,4)
    p.send('TARGET',int(p.head[10]),56)
    audit['settle'](p)
    assert any('An Zu' in bytes.fromhex(l.split()[3]).decode() for l in p.frame.splitlines() if l.startswith('B ')), 'Original Awaken incantation was not emitted'
    audit['movement'](p)
    p.close()
    print('Original spellbook display and close passed.',flush=True)

run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
run('spellbook-client','Investigation',[
    'WAIT 900','BOOKCREATE','BOOKOPEN','WAIT 400','MODAL 5','CAPTURE',
    'VIEWCLICK 133 23','WAIT 600','MODAL 5','CAPTURE',
    'VIEWCLICK 75 34','WAIT 600','MODAL 5','DISMISS','WAIT 300','MODAL 0',
    'BOOKOPEN','WAIT 400','MODAL 5','CAPTURE','ESCAPE','WAIT 400','MODAL 0',
    'STEP 0','WAIT 500','WALKCHECK','EXIT',
],True,scenario='book',extra={'TRINSIC_PREPARE':'interaction-audit'})
from play import ROOT
client_log=(ROOT/'runs/spellbook-client/host.log').read_text()
assert 'spellbook page=1 selected=0' in client_log
assert 'spellbook page=1 selected=8' in client_log
