"""Character setup against the native bridge, original arrival and native saves."""
import json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
os.environ.setdefault('TRINSIC_HOST_EXECUTABLE',str(HERE/'bin/native-creation/Ultima7.exe'))
sys.path.insert(0,str(HERE.parent/'qualification'))
from play import session,Pipe
from investigation import Walkthrough

def identity(pipe):
    lines=pipe.frame.splitlines()
    name=bytes.fromhex(next(s[2:] for s in lines if s.startswith('N '))).decode('cp437')
    stats=list(map(int,next(s[2:] for s in lines if s.startswith('P ')).split()))
    return name,stats[9]

def command(pipe,female,encoded):
    return pipe.raw(f'{int(pipe.head[4])+1} {pipe.head[2]} CREATEAVATAR {female} 0 {encoded}')

def verify():
    results={}
    for name,female,run in [('Éowyn',1,'character-native-female'),('Avatar12345678',0,'character-native-male')]:
        with session(run,'Investigation',True,original_opening=True) as (folder,env,host):
            p=Pipe(env['TRINSIC_PIPE'],host)
            initial=identity(p);tick,random=p.head[3],p.head[12]
            assert '\nNEWCHAR 1\n' in p.frame
            for gender,encoded in [(0,''),(2,'41'),(0,'41'*15),(0,'00'),(0,'0a'),(0,'7f'),(0,'20'),(0,'2041'),(0,'4120'),(0,'xyz')]:
                assert command(p,gender,encoded)=='invalid-character',(gender,encoded,p.head)
                assert identity(p)==initial and (p.head[3],p.head[12])==(tick,random)
            encoded=name.encode('cp437').hex()
            assert p.raw(f'{int(p.head[4])+1} 0 CREATEAVATAR {female} 0 {encoded}')=='stale'
            assert identity(p)==initial
            seq=int(p.head[4])+1;request=f'{seq} {p.head[2]} CREATEAVATAR {female} 0 {encoded}'
            assert p.raw(request)=='ok'
            assert identity(p)==(name,female) and (p.head[3],p.head[12])==(tick,random)
            assert '\nNEWCHAR 0\n' in p.frame
            assert p.raw(request)=='ok' and identity(p)==(name,female)
            assert command(p,1-female,'52656e616d65')=='unavailable'
            p.close();p=Pipe(env['TRINSIC_PIPE'],host)
            assert identity(p)==(name,female) and '\nNEWCHAR 0\n' in p.frame
            walk=Walkthrough(p,folder);walk.opening()
            assert walk.flags()[90] and identity(p)==(name,female)
            assert p.send('SAVE')=='ok'
            assert p.send('LOAD')=='ok'
            assert identity(p)==(name,female)
            assert command(p,1-female,'52656e616d65')=='unavailable'
            results[run]={'name':name,'female':bool(female),'validation':True,'no_time_or_random_advance':True,
                          'deduplication':True,'reconnect':True,'original_commission':True,'native_save_reload':True}
            p.close()
        with session(run,'Investigation',False,original_opening=True) as (folder,env,host):
            assert 'TRINSIC_READY' not in env
            p=Pipe(env['TRINSIC_PIPE'],host)
            assert identity(p)==(name,female) and '\nNEWCHAR 0\n' in p.frame
            assert command(p,1-female,'52656e616d65')=='unavailable'
            p.close()
            results[run]['fresh_process_resume']=True
    (HERE/'bin/proof-character-native.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results))

if __name__=='__main__':verify()
