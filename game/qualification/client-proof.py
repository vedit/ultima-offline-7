import json,shutil,sys,time
from play import session,client,ROOT,BIN
def run(name,fixture,commands,reset,zoom='1',scenario='room'):
    with session(name,fixture,reset) as (folder,env,host):
        path=folder/'controls.txt'; path.write_text('\n'.join(commands)+'\n')
        log=path.with_suffix('.txt.log')
        if log.exists():log.replace(folder/('previous-'+str(time.time_ns())+'.log'))
        env.update(TRINSIC_ZOOM=zoom,TRINSIC_REPLAY=str(path))
        start=time.time()
        rc=client(folder,env,host,145)
        if rc!=0 or not log.exists() or 'EXIT | ' not in log.read_text():raise RuntimeError(f'{name} incomplete ({rc})')
        pictures=sorted((BIN/'Data/Client/Screenshots').glob('*.png'),key=lambda p:p.stat().st_mtime)
        paths=[]
        for i,p in enumerate(p for p in pictures if p.stat().st_mtime>=start):
            dest=folder/(scenario+'-'+str(i)+'.png');shutil.copyfile(p,dest);paths.append(dest.name)
        receipt=dict(run=name,zoom=zoom,images=paths,events=log.read_text().splitlines())
        (folder/('client-'+scenario+'.json')).write_text(json.dumps(receipt,indent=2))
        return receipt
def room():
    history=json.loads((ROOT/'runs/room-exercise/exercise.json').read_text())['history']
    commands=['WAIT 700','CAPTURE','TURN 3']
    for i,(op,a,b,outcome,head,coords,parent) in enumerate(history):
        if op=='STEP':commands.append(('CONFLICT' if i==0 else 'STEP')+' '+str(a))
        elif op=='USE':commands+=['USE '+str(a),'WAIT 500']
        elif op=='MOVE':
            if outcome.startswith('refused'):commands+=['USE 21920','WAIT 450']
            commands+=['PICK '+str(a),'WAIT 350','CAPTURE','DROP '+str(b),'DUP','CAPTURE']
            if outcome.startswith('refused'):commands+=['CLOSE']
        elif op=='ANSWER':
            if a in (1,4):commands+=['CAPTURE']
            commands+=['ANSWER '+str(b),'WAIT 400']
        else:commands+=[op]
    commands+=['STALE','RECONNECT','CAPTURE','EXIT']
    r=run('client-room-proof','Trinsic-room',commands,True)
    assert any('refused3' in e for e in r['events'])
    assert any('cursor True' in e for e in r['events'])
    assert any('stale' in e for e in r['events'])
    end=r['events'][-1].split('|')
    assert end[1].strip().split()[-1]=='1' and 'display 985 2199 0' in end[2],end
    directions=[(0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1)]
    reverse=[]; last=None
    for entry in history[8:55]:
        xy=entry[5][:2]
        if last and xy!=last: reverse.append('STEP '+str(directions.index((last[0]-xy[0],last[1]-xy[1]))))
        last=xy
    r=run('client-room-proof','Trinsic-room',['WAIT 850','CAPTURE']+list(reversed(reverse))+['USE 21920','WAIT 550','CAPTURE','EXIT'],False,scenario='restart')
    assert 'display 985 2199 0' in r['events'][0] and r['events'][0].split('|')[1].split()[-1]=='1'
    assert 'chest False' in r['events'][-1] and 'parent 1073763744' in r['events'][-1],r['events'][-1]
if __name__=='__main__':room()

