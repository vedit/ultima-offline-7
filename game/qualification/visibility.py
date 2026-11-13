"""Replay six real client sessions. Each waits at the same native pre-step boundary until Begin."""
import runpy,json
from pathlib import Path
from play import ROOT
from reference import members
from baseline import actor
run=runpy.run_path(str(ROOT/'qualification/client-proof.py'))['run']
for case in ('outside','inside','edge'):
    for name,zoom in [('wide','2.4'),('normal','1')]:
        folder='replay-'+case+'-'+name
        commands=['WAIT 550','OVERLAY','CAPTURE','BEGIN','WAIT 2600','CAPTURE','EXIT']
        result=run(folder,'Iolo-'+case,commands,True,zoom,scenario=case)
        events=result['events']
        assert any('iolo 996 '+str({'outside':2215,'inside':2213,'edge':2214}[case]) in l for l in events)
        assert 'iolo 986 2202' in events[-1],events[-1]
        assert ('zoom '+zoom+' ') in events[-1]
        print(folder,events[-1],flush=True)
        trace=[s for s in (ROOT/'runs'/folder/'host.log').read_text().splitlines() if s.startswith('recovery ')]
        assert bool([s for s in trace if '184 3 camera' in s]) == (case=='outside')
        if name=='wide':prev=trace
        else: assert prev==trace,(prev,trace)

