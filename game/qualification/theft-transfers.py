"""Check native ownership, witnessed movement and rollback in a private fixture."""
import runpy
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('theft-transfers','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
    result=p.send('AUDITOWN',136,0)
    assert result=='property',(result,p.head,p.rows[:15])
    assert p.send('SAVE')=='ok'
    assert p.raw(f'{int(p.head[4])+1} {p.head[2]} GROUND 136 -1 2214 0 -1')=='unreachable'
    assert next(r for r in p.rows if r[0]==136)[6]==88
    assert p.send('AUDITOWN',136,2)=='property'
    assert 'transfer crime' not in (folder/'host.log').read_text()
    result=p.raw(f'{int(p.head[4])+1} {p.head[2]} GROUND 136 1076 2213 0 -1')
    assert result=='ok',(result,p.head)
    audit['settle'](p)
    assert 'transfer crime item=136' in (folder/'host.log').read_text()
    assert p.send('LOAD')=='ok'
    assert p.send('AUDITOWN',136,0)=='property'
    assert p.send('AUDITOWN',280,1)=='owned'
    # Both stacks use original quantity metadata; merging reconciles mixed ownership.
    assert p.send('MOVE',136,280)=='merged'
    assert p.send('AUDITOWN',280,2)=='owned'
    assert not any(r[0]==136 for r in p.rows)
    assert p.send('LOAD')=='ok'
    assert p.send('AUDITOWN',136,1)=='owned'
    before=(folder/'host.log').read_text().count('transfer crime')
    result=p.raw(f'{int(p.head[4])+1} {p.head[2]} GROUND 136 1076 2213 0 -1')
    assert result=='ok',(result,p.head)
    audit['settle'](p)
    assert (folder/'host.log').read_text().count('transfer crime')==before
    p.close()
    print('Property move, owned move, rollback and mixed-ownership merge passed.',flush=True)




