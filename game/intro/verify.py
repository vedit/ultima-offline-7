"""Exercise the dream through the existing ClassicUO replay qualification driver."""
import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
os.environ['TRINSIC_CLIENT_BIN']=str(HERE/'bin/client')
sys.path.insert(0,str(HERE.parent/'qualification'))
spec=importlib.util.spec_from_file_location('client_proof',HERE.parent/'qualification/client-proof.py')
proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)
extra={'TRINSIC_INTRO_ASSETS':str(HERE/'bin/assets'),'U7_ENABLE_AUDIO':'1'}

def run(mode):
    options=dict(extra)
    if mode=='preview':
        commands=['WAIT 6000','CAPTURE','WAIT 700','EXIT']
    elif mode=='full':
        commands=['INTRO HELD','WAIT 2300','INTRO PHASE Speech','INTRO AUDIO Playing',
                  'INTRO KEY SPACE','WAIT 100','INTRO PAUSESTART','WAIT 700','INTRO PAUSED','INTRO HELD',
                  'CAPTURE','INTRO KEY SPACE','WAIT 12000','CAPTURE','WAIT 12000','CAPTURE',
                  'WAIT 26000','INTRO PHASE Portal','INTRO AUDIO Stopped','INTRO HELD','CAPTURE',
                  'INTRO PORTAL','WAIT 2400','INTRO GAME','WAIT 1200','CAPTURE','EXIT']
    elif mode=='skip':
        commands=['WAIT 2300','INTRO HELD','INTRO KEY ESCAPE','WAIT 2000','INTRO GAME','CAPTURE','EXIT']
    elif mode=='resume':
        # Original source fixture is loaded as a saved world; no READY gate exists.
        commands=['WAIT 1800','INTRO GAME','SAVE','WAIT 400','CAPTURE','EXIT']
    elif mode in ('muted','silent'):
        if mode=='muted':
            folder=proof.ROOT/'runs/dream-muted-proof'
            if not folder.exists():
                from reference import stage
                stage(folder.name)
            profile=folder/'profiles/Local/Trinsic/Avatar/profile.json'
            profile.parent.mkdir(parents=True,exist_ok=True)
            settings=json.loads(profile.read_text()) if profile.exists() else {}
            settings['trinsic_speech_enabled']=False
            profile.write_text(json.dumps(settings))
        else:
            folder=HERE/'bin/no-voice';folder.mkdir(exist_ok=True)
            for name in ('guardian.png','intro.json'):shutil.copyfile(HERE/'bin/assets'/name,folder/name)
            options['TRINSIC_INTRO_ASSETS']=str(folder)
        commands=['WAIT 2500','INTRO PHASE Speech','INTRO '+mode.upper(),'INTRO HELD','CAPTURE',
                  'INTRO KEY ESCAPE','WAIT 1800','INTRO GAME','EXIT']
    else:raise ValueError(mode)
    r=proof.run('dream-'+mode+'-proof','Investigation',commands,True,original_opening=mode!='resume',extra=options,scenario='dream')
    if mode=='resume':
        saved=proof.ROOT/'runs/dream-resume-proof/GAME00.U7'
        if not saved.exists():raise RuntimeError('Native save was not written')
        r['reload']=proof.run('dream-resume-proof','Investigation',
            ['WAIT 1800','INTRO GAME','LOAD','WAIT 700','INTRO GAME','CAPTURE','EXIT'],False,
            original_opening=True,extra=extra,scenario='reload')
    (HERE/'bin'/('proof-'+mode+'.json')).write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'run':r['run'],'images':r['images'],'events':len(r['events'])}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['preview','full','skip','resume','muted','silent']);run(p.parse_args().mode)
