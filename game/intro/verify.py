"""Exercise the dream through the existing ClassicUO replay qualification driver."""
import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
os.environ.setdefault('TRINSIC_CLIENT_BIN',str(HERE/'bin/layout-client'))
os.environ.setdefault('TRINSIC_HOST_EXECUTABLE',str(HERE/'bin/native-creation/Ultima7.exe'))
sys.path.insert(0,str(HERE.parent/'qualification'))
spec=importlib.util.spec_from_file_location('client_proof',HERE.parent/'qualification/client-proof.py')
proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(proof)
extra={'TRINSIC_INTRO_ASSETS':os.environ.get('TRINSIC_INTRO_ASSETS',str(HERE/'bin/painted-assets')),'U7_ENABLE_AUDIO':'1'}

def run(mode):
    if mode=='creation-resume':
        encoded='Éowyn'.encode('cp437').hex()
        r=proof.run('character-native-female','Investigation',
            ['WAIT 1800','INTRO GAME',f'INTRO IDENTITY {encoded} 1','RECONNECT','WAIT 700','INTRO GAME',
             f'INTRO IDENTITY {encoded} 1','LOAD','WAIT 700','INTRO GAME',f'INTRO IDENTITY {encoded} 1','CAPTURE','EXIT'],
            False,original_opening=True,extra=extra,scenario='creation-resume')
        (HERE/'bin/proof-creation-resume.json').write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({'run':r['run'],'images':r['images'],'named_save_bypasses_creation':True}));return
    if mode=='arrival':
        from play import session,Pipe
        from investigation import Walkthrough
        import time
        results={}
        class DreamPipe(Pipe):
            def send(self,op,a=0,b=0):
                result=super().send(op,1 if op=='BEGIN' else a,b)
                if op=='BEGIN':
                    first=self.head[6:9]
                    assert self.raw('1 '+self.head[2]+' BEGIN 1 0')=='ok'
                    assert self.head[4]=='1' and self.head[6:9]==first,'Repeated BEGIN relocated the Avatar'
                return result
        with session('dream-stables-commission','Investigation',True,original_opening=True) as (folder,env,host):
            pipe=DreamPipe(env['TRINSIC_PIPE'],host);walk=Walkthrough(pipe,folder);walk.opening()
            avatar=next(r for r in pipe.rows if r[7]==0)
            assert avatar[3:6]==[1071,2210,0],avatar
            results['dream']={'position':avatar[3:6],'quest90':bool(walk.flags()[90]),'saved':(folder/'GAME00.U7').exists(),'duplicate_begin':True}
            pipe.close()
        with session('dream-original-arrival-regression','Investigation',True,original_opening=True) as (folder,env,host):
            pipe=Pipe(env['TRINSIC_PIPE'],host);pipe.send('BEGIN');deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                pipe.sync()
                if int(pipe.head[9]):break
                time.sleep(.1)
            avatar=next(r for r in pipe.rows if r[7]==0)
            assert avatar[3:6]==[1076,2214,0] and int(pipe.head[9])==1
            results['ordinary']={'position':avatar[3:6],'original_greeting':True}
            pipe.close()
        (HERE/'bin/proof-arrival.json').write_text(json.dumps(results,indent=2)+'\n')
        print(json.dumps(results));return
    options=dict(extra)
    if mode in ('creation','creation-male'):
        name,sex=('Éowyn',1) if mode=='creation' else ('Avatar12345678',0)
        encoded=name.encode('cp437').hex()
        commands=['WAIT 500','INTRO FORM','INTRO HELD','INTRO SEX 0','INTRO SEX 0 label',
                  'INTRO SEX 1','INTRO SEX 1 label','INTRO SEX 0','CAPTURE','INTRO NAME','INTRO SUBMIT','INTRO INVALID',
                  'INTRO KEY ESCAPE','INTRO KEY RIGHT','WAIT 300','INTRO FORM','INTRO HELD',
                  f'INTRO NAMEHEX {encoded}',f'INTRO SEX {sex}','CAPTURE','INTRO KEY RETURN','WAIT 3000',
                  f'INTRO IDENTITY {encoded} {sex}','INTRO APPEARANCE','CAPTURE',
                  'INTRO KEY ESCAPE','WAIT 1800','INTRO PHASE Portal','INTRO PORTAL','WAIT 20000','INTRO GAME',
                  f'INTRO IDENTITY {encoded} {sex}','FXCOUNT travel 1','INTRO DIALOGUECENTER','CAPTURE','EXIT']
    elif mode=='creation-cancel':
        commands=['WAIT 500','INTRO FORM','INTRO HELD','INTRO NAME Unfinished','INTRO SEX 1','INTRO KEY ESCAPE',
                  'WAIT 700','INTRO FORM','INTRO HELD','CAPTURE','EXIT']
    elif mode=='world':
        commands=['WAIT 3000','INTRO WORLD','INTRO APPEARANCE','INTRO HELD','CAPTURE',
                  'INTRO KEY ESCAPE','WAIT 1800','INTRO PHASE Portal','INTRO WORLD','INTRO APPEARANCE','INTRO COLLISION','INTRO HELD','CAPTURE',
                  'WAIT 1800','INTRO PHASE Portal','INTRO RECORDPOS',
                  'INTRO KEY RIGHT','WAIT 700','INTRO KEYUP RIGHT','WAIT 800','INTRO MOVED','CAPTURE',
                  'INTRO KEY SPACE','WAIT 200','INTRO RECORDPOS','INTRO KEY LEFT','WAIT 600','INTRO STILL','INTRO KEYUP LEFT','INTRO KEY SPACE',
                  'INTRO MOVE 5 7','WAIT 2500','INTRO RAN','INTRO STOP',
                  'INTRO PORTAL','WAIT 20000','INTRO GAME','FXCOUNT travel 1','INTRO DIALOGUECENTER','CAPTURE','EXIT']
    elif mode=='preview':
        commands=['WAIT 6000','CAPTURE','WAIT 700','EXIT']
    elif mode=='full':
        commands=['INTRO HELD','WAIT 2300','INTRO PHASE Speech','INTRO AUDIO Playing',
                  'INTRO KEY SPACE','WAIT 100','INTRO PAUSESTART','WAIT 700','INTRO PAUSED','INTRO HELD',
                  'CAPTURE','INTRO KEY SPACE','WAIT 12000','CAPTURE','WAIT 12000','CAPTURE',
                  'WAIT 26000','INTRO PHASE Portal','INTRO AUDIO Stopped','INTRO HELD','CAPTURE',
                  'INTRO PORTAL','WAIT 10000','INTRO GAME','WAIT 1200','CAPTURE','EXIT']
    elif mode=='skip':
        commands=['WAIT 2300','INTRO HELD','INTRO KEY ESCAPE','WAIT 2000','INTRO PHASE Portal','INTRO HELD','WAIT 1500','INTRO PHASE Portal','INTRO PORTAL','WAIT 20000','INTRO GAME','CAPTURE','EXIT']
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
            for name in ('guardian.png','intro.json','blue-static.png'):shutil.copyfile(Path(extra['TRINSIC_INTRO_ASSETS'])/name,folder/name)
            options['TRINSIC_INTRO_ASSETS']=str(folder)
        commands=['WAIT 2500','INTRO PHASE Speech','INTRO '+mode.upper(),'INTRO HELD','CAPTURE',
                  'INTRO KEY ESCAPE','WAIT 1800','INTRO PHASE Portal','INTRO HELD','INTRO PORTAL','WAIT 10000','INTRO GAME','EXIT']
    else:raise ValueError(mode)
    if mode!='resume' and not mode.startswith('creation'):
        commands=['WAIT 500','INTRO FORM','INTRO NAME Avatar','INTRO SEX 0','INTRO SUBMIT','WAIT 500']+commands
    r=proof.run('dream-'+mode+'-proof','Investigation',commands,True,original_opening=mode!='resume',extra=options,scenario='dream')
    if mode.startswith('creation'):
        if mode=='creation-cancel':
            assert not (proof.ROOT/'runs'/r['run']/'GAME00.U7').exists()
            r['cancelled_without_save']=True
        else:r['identity']={'name':name,'female':bool(sex),'dream_and_trinsic':True}
    if mode=='world':
        last=next(e for e in reversed(r['events']) if e.startswith('INTRO GAME |'))
        if 'sync 1071 2210 0 1 ' not in last:raise RuntimeError('Arrival did not reach the original greeting at the stable entrance')
        r['stable_arrival']=[1071,2210,0]
        from PIL import Image
        with Image.open(proof.ROOT/'runs'/r['run']/r['images'][0]) as shot:
            for box in ((15,80,80,180),(1080,80,1145,180),(350,10,450,30)):
                pixels=list(shot.crop(box).convert('RGB').getdata())
                if sum(b>r*2 and b>g*2 and b>35 for r,g,b in pixels)<len(pixels)*.9:
                    raise RuntimeError('Blue backdrop does not cover viewport edges')
        r['blue_covers_left_right_top']=True
    if mode=='full':
        # Void must not fade into an opaque foreground over the room.
        from PIL import Image
        for name in r['images'][1:3]:
            with Image.open(proof.ROOT/'runs'/r['run']/name) as shot:
                    # Distinguish the neutral stone floor from the saturated blue
                    # backdrop, which must not count as a surviving room surface.
                    visible=sum(min(pixel[:3])>30 and max(pixel[:3])-min(pixel[:3])<65
                                for pixel in shot.crop((560,400,650,500)).getdata())
            if visible<6000:raise RuntimeError('Room floor disappeared during speech')
        r['floor_visible_during_speech']=True
    if mode=='resume':
        saved=proof.ROOT/'runs/dream-resume-proof/GAME00.U7'
        if not saved.exists():raise RuntimeError('Native save was not written')
        r['reload']=proof.run('dream-resume-proof','Investigation',
            ['WAIT 1800','INTRO GAME','LOAD','WAIT 700','INTRO GAME','CAPTURE','EXIT'],False,
            original_opening=True,extra=extra,scenario='reload')
    (HERE/'bin'/('proof-'+mode+'.json')).write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'run':r['run'],'images':r['images'],'events':len(r['events'])}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['creation','creation-male','creation-cancel','creation-resume','arrival','world','preview','full','skip','resume','muted','silent']);run(p.parse_args().mode)
