"""Observe the fixed desktop host with or without an attached ClassicUO client."""
import concurrent.futures,json,os,subprocess,threading,time
from pathlib import Path
from play import session,Pipe,ROOT,client
from baseline import state
from reference import members
def observe(case):
    with session('native-'+case,'Iolo-'+case,True,{'U7_TEST_CLOCK':'fixed','U7_TEST_INPUT':'fixed; 5500 quit'}) as (folder,env,host):
        p=Pipe(env['TRINSIC_PIPE'],host); rows=[]
        try:
            while host.poll() is None:
                p.sync()
                pos=next(r[3:6] for r in p.rows if r[7]==1)
                if not rows or pos!=rows[-1]['xyz']:rows.append(dict(tick=int(p.head[3]),xyz=pos))
        except (OSError,IndexError):pass
        finally:p.close()
        host.wait(timeout=130)
        (folder/'observed.json').write_text(json.dumps(rows,indent=2))
        print(case,rows,flush=True)
def parity():
    import baseline
    name='adapter-observer-fixed-02';pipe='trinsic_parity_209'
    env=dict(os.environ,TRINSIC_PIPE=pipe)
    sub=subprocess.Popen([os.sys.executable,str(Path(__file__).with_name('baseline.py')),name,'--fixed'],env=env,cwd=ROOT,stdout=subprocess.DEVNULL)
    p=Pipe(pipe,sub)
    count=0
    try:
        while sub.poll() is None:
            p.sync();count+=1;time.sleep(.07)
    except (OSError,IndexError): pass
    finally:p.close()
    assert sub.wait(180)==0
    a,b=[json.loads((ROOT/'runs'/n/'result.json').read_text()) for n in ('finnigan-fixed-01',name)]
    receipt=dict(observations=count,frames_equal=a['frames']==b['frames'],state_equal=a['after']==b['after'],members=len(a['after']['members']))
    (ROOT/'evidence/observer-parity.json').write_text(json.dumps(receipt,indent=2));print(receipt,flush=True)
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures=[ex.submit(observe,c) for c in ('inside','edge','outside')]+[ex.submit(parity)]
        for f in futures:f.result()

