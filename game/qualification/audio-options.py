"""Native audio/save options and desktop UI qualification, using disposable runs."""
import argparse, array, hashlib, json, math, os, runpy, time, uuid
from pathlib import Path
from play import ROOT, session, copy_test_save, active_slot, members

helpers=runpy.run_path(str(Path(__file__).with_name('developer-wand.py')))
Pipe,Checks,lines=helpers['Pipe'],helpers['Checks'],helpers['lines']

def native(name):
    evidence=[]
    dump=ROOT/'runs'/name/'audio.raw'
    with session(name,'Investigation',True,{'TRINSIC_READY':'1','TRINSIC_DEBUG':'1','U7_AUDIO_DUMP':str(dump)}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);c=Checks(p)
        c.send('BEGIN');time.sleep(.5);p.sync()
        def state():return list(map(int,lines(p,'AU')[0][1:]))
        c.send('AUDIO',1,0,'1 100 100 100 0')
        assert state()[3:]==[1,0,1,100,100,100,0,1],state()
        previous=state()[3:]
        for args in [(2,1,'1 50 50 50 0'),(1,1,'1 101 50 50 0'),(1,1,'1 50 -1 50 0'),(1,1,'1 50 50 50 2'),(1,1,'1 50 50 50 0 extra')]:
            c.send('AUDIO',*args,expected='invalid');assert state()[3:]==previous
        evidence.append('Audio validation is atomic; invalid values do not alter settings')
        def amplitude():
            time.sleep(1.2);start=dump.stat().st_size;time.sleep(1.2)
            with dump.open('rb') as f:f.seek(start);data=f.read()
            samples=array.array('h');samples.frombytes(data[:len(data)//2*2]);return round(math.sqrt(sum(float(x)*x for x in samples)/max(1,len(samples))),3)
        time.sleep(3);loud=amplitude();p.sync();native_track=state()[:3]
        c.send('AUDIO',1,0,'1 0 100 100 0');quiet=amplitude()
        c.send('AUDIO',1,0,'1 100 100 100 1');external=amplitude()
        c.send('AUDIO',1,0,'1 100 100 100 0');restored=amplitude()
        assert loud>1 and restored>1 and quiet<max(1,loud*.02) and external<max(1,loud*.02),(loud,quiet,external,restored,native_track)
        evidence.append(dict(native_track=native_track,rms=dict(full=loud,zero=quiet,external_muted=external,restored=restored)))
        c.send('AUDIO',0,0,'0 33 44 55 0');last=c.last
        assert p.raw(last)=='ok' and state()[3:]==[0,0,0,33,44,55,0,1]
        options=(folder/'GAMEDAT/options.cfg').read_text().lower()
        assert options.count('off')==3,options
        evidence.append('Native music/effects/speech switches persisted; repeated sequence is idempotent')
        c.send('SAVES')
        for op in ('SAVE','LOAD'):
            c.send(op,10,expected='invalid');c.send(op,-2,expected='invalid')
        c.send('SAVE',2,extra='Options test'.encode().hex())
        assert active_slot(folder)==2
        assert helpers['decode'](lines(p,'SL')[2][2])=='Options test'
        assert {'U7IBUF.DAT','U7NBUF.DAT','PARTY'}.issubset(members(folder/'GAME02.U7'))
        c.send('SAVE',2,extra='00',expected='invalid')
        c.send('DBGSAVE');assert active_slot(folder)==2 and not (folder/'GAME00.U7').exists()
        generation=p.head[2];c.send('LOAD',-1)
        assert p.head[2]!=generation and state()[-1]==0
        c.send('AUDIO',1,1,'1 80 70 60 0')
        c.send('SAVE',-1)
        evidence.append('Native slots validate bounds/titles; F5/wand active slot, load generation and audio resync verified')
        source_hash=hashlib.sha256((folder/'GAME02.U7').read_bytes()).hexdigest();p.close()
    with session(name,'Investigation') as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host);c=Checks(p);c.send('SAVES')
        assert int(lines(p,'SV')[0][1])==2 and active_slot(folder)==2;p.close()
    copy=name+'-copy';destination=copy_test_save(name,copy)
    assert hashlib.sha256((destination/'GAME00.U7').read_bytes()).hexdigest()==source_hash
    try:copy_test_save(name,copy);raise AssertionError('Overwrite accepted')
    except FileExistsError:pass
    evidence.append('Launcher resumes active slot; test-copy uses its checkpoint and refuses overwrite')
    return evidence

def desktop(name,music):
    run=runpy.run_path(str(Path(__file__).with_name('client-proof.py')))['run']
    missing=ROOT/'runs'/(name+'-missing-music');missing.mkdir(exist_ok=False);(missing/'35bg.ogg').write_bytes(b'missing-track fixture')
    commands=['WAIT 1600','BEGIN','WAIT 1000','U7OPTIONS','CAPTURE','U7AUDIO','WAIT 700','CAPTURE',
        'U7AUDIOTYPING','U7AUDIOSET 1 1 1 55 65 75','WAIT 900',
        'U7AUDIOFOLDER '+str(music),'WAIT 1300','U7AUDIOCHECK Exult MT-32 recording','U7AUDIOACK 1 1 1 55 65 75 1','CAPTURE',
        'U7AUDIOFOLDER '+str(missing),'WAIT 900','U7AUDIOCHECK unavailable; using native music.','U7AUDIOACK 1 1 1 55 65 75 0',
        'U7AUDIOFOLDER '+str(music),'WAIT 900',
        'RECONNECT','WAIT 1200','U7AUDIOCHECK Exult MT-32 recording',
        'U7AUDIOSET 0 0 0 20 30 40','WAIT 900','U7AUDIOCHECK Music off.',
        'U7AUDIOSET 1 1 1 55 65 75','WAIT 900','U7AUDIOCHECK Exult MT-32 recording',
        'U7AUDIOCREDITS','CAPTURE','U7CREDITSCLOSE','U7AUDIOCLOSE','U7SAVES','WAIT 600','U7SAVEBUTTON 102','U7SAVEBUTTON 1','WAIT 1000','U7SAVEACTIVE 2','CAPTURE',
        'U7SAVEKEY','WAIT 1000','U7SAVEBUTTON 2','U7LOADANSWER 1','WAIT 1400','U7SAVEACTIVE 2',
        'U7SAVECLOSE','U7OPTION 8','U7LOADANSWER 0','U7OPTION 4','STEP 2','WAIT 600','CAPTURE','EXIT']
    result=run(name,'Investigation',commands,True,scenario='options',extra={'TRINSIC_READY':'1'})
    profiles=list((ROOT/'runs'/name/'profiles').rglob('profile.json'))
    result['profiles']=[str(p) for p in profiles]
    assert profiles
    profile=json.loads(profiles[0].read_text())
    assert [profile['trinsic_music_volume'],profile['sound_volume'],profile['trinsic_speech_volume']]==[55,65,75]
    assert Path(profile['trinsic_exult_music_folder']).resolve()==music.resolve()
    result['restart']=run(name,'Investigation',['WAIT 2000','U7SAVEACTIVE 2','U7AUDIOCHECK Exult MT-32 recording',
        'U7AUDIOACK 1 1 1 55 65 75 1','U7OPTIONS','U7AUDIO','WAIT 500','CAPTURE','EXIT'],False,scenario='restart')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--client',action='store_true');parser.add_argument('--music',type=Path,default=ROOT.parents[1]/'Tools/Exult/data/music');args=parser.parse_args()
    name='audio-options-'+uuid.uuid4().hex[:8]
    result=desktop(name,args.music) if args.client else native(name)
    receipt=ROOT/'runs'/name/'audio-options.json';receipt.write_text(json.dumps(result,indent=2)+'\n');print(receipt)
