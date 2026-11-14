"""Test-only mutation commands must fail in an ordinary player session."""
import runpy
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
with session('interaction-audit-boundaries','Investigation',True) as (folder,env,host):
    p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
    items={r[0]:r[1:3]+r[6:7] for r in p.rows if r[6] in (56,88,184,200)}
    for op,a,b in [('AUDITBOOK',0,0),('AUDITOWN',136,0),('AUDITCREATURE',523,0)]:
        assert p.send(op,a,b)=='invalid',op
    assert items=={r[0]:r[1:3]+r[6:7] for r in p.rows if r[6] in (56,88,184,200)}
    audit['movement'](p);p.close()
    print('Audit-only book, ownership and creature commands rejected in ordinary play.',flush=True)
