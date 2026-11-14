"""Qualify stack conservation, slider gestures, status and both war-mode controls."""
import runpy,sys
from pathlib import Path
from play import session
audit=runpy.run_path(str(Path(__file__).with_name('item-use-audit.py')))
def native():
    with session('stack-transactions','Investigation',True) as (folder,env,host):
        p=audit['BoundedPipe'](env['TRINSIC_PIPE'],host)
        row=lambda id:next(r for r in p.rows if r[0]==id)
        def move(amount):return p.raw(f'{int(p.head[4])+1} {p.head[2]} MOVE 136 200 -1 -1 {amount}')
        assert move(0)=='amount' and move(11)=='amount'
        result=move(4);assert result.startswith('split-'),result
        new=int(result[6:]);assert row(136)[9]==6 and row(new)[9]==4 and row(new)[6]==200
        assert p.send('MOVE',new,136)=='merged'
        assert row(136)[9]==10 and not any(r[0]==new for r in p.rows)
        result=p.raw(f'{int(p.head[4])+1} {p.head[2]} GROUND 136 1076 2214 0 4')
        assert result=='blocked' and row(136)[9]==10
        assert p.send('SAVE')=='ok';assert p.send('LOAD')=='ok';assert row(136)[9]==10
        audit['movement'](p);p.close();print('Split, merge, invalid amounts, blocked-drop rollback and save/load conserve gold.',flush=True)
def client():
    run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    result=run('stack-controls-client','Investigation',[
        'WAIT 900','MONEY 10','MONEY split 4','WAIT 400','MONEY 4,6','MONEY join','WAIT 400','MONEY 10',
        'STATUS','TAB','WAIT 300','WARSTATE 0','SHEETWAR','WAIT 300','WARSTATE 1','SHEETWAR','WAIT 300','WARSTATE 0','CAPTURE',
        'USE 88','WAIT 300','STEP 4','WAIT 500','CLOSEDWALK 1076 2214','SAVE','EXIT'
    ],True,scenario='stacks-controls')
    result=run('stack-controls-client','Investigation',['WAIT 900','MONEY 10','WARSTATE 0','EXIT'],False,scenario='restart')
if __name__=='__main__':
    native()
    if '--native' not in sys.argv:client()
