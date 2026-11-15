"""Run the Trinsic interaction qualifications and retain per-case evidence."""
import contextlib,json,runpy,sys,time,traceback
from pathlib import Path
from play import ROOT
CASES=[
 ('inventory-dispatch','item-use-audit.py',[]),
 ('town-dispatch','item-use-audit.py',['--town']),
 ('world-targets','world-targets.py',[]),
 ('spellbook','spellbook-controls.py',[]),
 ('theft','theft-transfers.py',[]),
 ('theft-witness','theft-witness.py',[]),
 ('creatures-combat','creature-combat.py',[]),
 ('world-effects','world-effects.py',[]),
 ('commerce-training','commerce-training.py',[]),
 ('rest-potions','rest-potions.py',[]),
 ('forge-effects','forge-effects.py',[]),
 ('audit-boundaries','audit-boundaries.py',[]),
 ('companions-keys','companion-items.py',[]),
 ('inventory-mouse','inventory-interactions.py',[]),
 ('panels','player-panels.py',[]),
 ('stacks-controls','stacks-controls.py',[]),
 ('item-labels','verify_item_labels.py',[]),
 ('npc-overhead','verify_overhead.py',[]),
 ('reported-interactions','player-feedback.py',[]),
 ('map-sign-client','item-use-audit.py',['--client']),
 ('murder-to-gate','investigation.py',['--run','full-interaction-investigation']),
 ('trigger-census','trinsic-triggers.py',['--output',str(ROOT/'runs/full-interaction-suite/trinsic-census.json')]),
 ('frontend-murder-to-gate','trinsic-playtest.py',['--run','full-frontend-journey']),
 ('trigger-branches','trinsic-triggers.py',['--branches','--completed-run','full-interaction-investigation',
    '--output',str(ROOT/'runs/full-interaction-suite/trinsic-branches.json')]),
 ('report-retries','trinsic-report-retry.py',['--checkpoint',str(ROOT/'runs/full-frontend-journey/Gilberto-witness.U7')]),
]
if __name__=='__main__':
    selected=set(sys.argv[1:])
    assert selected.issubset({name for name,_,_ in CASES}),selected
    folder=ROOT/'runs/full-interaction-suite';folder.mkdir(exist_ok=True)
    results=[];run_id=time.strftime('%Y%m%d-%H%M%S')
    for name,script,args in CASES:
        if selected and name not in selected:continue
        print('RUN',name,flush=True);start=time.monotonic();status='passed'
        log_name=run_id+'-'+name+'.log'
        with (folder/log_name).open('w',encoding='utf-8') as log:
            try:
                sys.argv=[script,*args]
                with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                    runpy.run_path(str(Path(__file__).with_name(script)),run_name='__main__')
            except Exception:
                status='failed';traceback.print_exc(file=log)
        result={'case':name,'status':status,'seconds':round(time.monotonic()-start,2),'log':log_name}
        results.append(result);(folder/('results-'+ '-'.join(sorted(selected))+'.json' if selected else 'results.json')).write_text(json.dumps(results,indent=2)+'\n')
        print(status.upper(),name,flush=True)
    assert all(r['status']=='passed' for r in results),[r for r in results if r['status']!='passed']
