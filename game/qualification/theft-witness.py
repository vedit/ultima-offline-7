"""Verify original witness reactions to moved property near the gate guard."""
import json,runpy
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('theft-witness','Investigation',True,{'TRINSIC_PREPARE':'interaction-audit'}) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
    assert p.raw(f'{int(p.head[4])+1} {p.head[2]} AUDITVISIT 1092 2215 0')=='ok'
    assert p.send('AUDITOWN',136,0)=='property'
    for x,y in [(1091,2215),(1092,2214),(1091,2214),(1092,2216)]:
        result=p.raw(f'{int(p.head[4])+1} {p.head[2]} GROUND 136 {x} {y} 0 -1')
        if result=='ok':break
        assert result in ('blocked','unreachable'),result
    else:raise AssertionError('No free native ground tile near the witness')
    audit['settle'](p)
    witnesses={r[0] for r in p.rows if r[7]>1 and not r[11]&16}
    barks=[{'speaker':int(l.split()[2]),'text':bytes.fromhex(l.split()[3]).decode('cp437')} for l in p.frame.splitlines() if l.startswith('B ')]
    assert any(b['speaker'] in witnesses for b in barks),barks
    (folder/'witness.json').write_text(json.dumps(barks,indent=2));p.close()
    print('Original non-party witness reacts to moved property:',barks,flush=True)
