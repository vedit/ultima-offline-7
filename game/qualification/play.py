"""Launch one private native authority and the ClassicUO fork using one owned run directory."""
import argparse, contextlib, json, os, subprocess, sys, time, uuid
from pathlib import Path
from reference import ROOT, SOURCE, stage, members
BIN = ROOT/'client/bin/Release-Trinsic-Avatar-Sheet/net10.0'
RELEASE = SOURCE/'Builds/BritanniaChairRouteFacet/releases/50f99d0c53594314f443902201e3a2312aa43764c7d35fede5f252da601ec4f1'
@contextlib.contextmanager
def session(name,fixture,reset=False,extra=None,*,original_opening=False):
    folder=ROOT/'runs'/name
    if not folder.exists(): stage(name)
    if folder.resolve().parent != (ROOT/'runs').resolve(): raise ValueError(name)
    import msvcrt
    with (folder/'session.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        seed=ROOT/'fixtures'/(fixture+'.U7')
        slot=folder/'GAME00.U7'
        if reset and slot.exists(): slot.replace(folder/('previous-'+uuid.uuid4().hex+'.U7'))
        parts=members(slot if slot.exists() else seed)
        for f in (folder/'GAMEDAT').iterdir():
            if f.is_file() and f.name not in parts: f.unlink()
        for k,v in parts.items(): (folder/'GAMEDAT'/k).write_bytes(v)
        pipe='trinsic_'+uuid.uuid4().hex
        env=dict(os.environ,TRINSIC_PIPE=pipe,U7_TEST_INPUT='live',TRINSIC_TRACE='1')
        if fixture=='Investigation':
            folder_data=ROOT/'town-battlement-data'
            if not (folder_data/'graphics.tsv').exists(): raise RuntimeError("Build the Trinsic town atlas before launching")
            env['TRINSIC_TOWN']=str(folder_data)
            args_file=folder/'gameargs.dat'
            if original_opening:
                # Black Gate consumes these character-creation arguments and loads INITGAME.DAT.
                args_file.write_bytes(b'\x00' + b'Avatar'.ljust(15,b'\x00'))
                env['TRINSIC_READY']='1'
            elif args_file.exists(): args_file.unlink()
        if fixture.startswith('Iolo-') and not extra: env['TRINSIC_READY']='1'
        if extra: env.update(extra)
        with (folder/'host.log').open('w') as log:
            host=subprocess.Popen([str(ROOT/'build-host/playtest-avatar-inventory/Ultima7.exe'),'--data',str(folder),'--program','u7','-p'],cwd=folder,env=env,stdout=log,stderr=log)
            try: yield folder,env,host
            finally:
                if host.poll() is None: host.terminate()
                host.wait(8)
class Pipe:
    def __init__(self,name,host):
        self.path=r'\\.\pipe'+'\\'+name
        end=time.monotonic()+145
        while time.monotonic()<end:
            try:
                self.file=open(self.path,'r+b',buffering=0)
                break
            except OSError:
                if host.poll() is not None: raise RuntimeError(f'host exited {host.returncode}')
                time.sleep(.1)
        else: raise TimeoutError(self.path)
        self.sync()
    def raw(self,msg):
        self.file.write(msg.encode())
        data=self.file.read(131072).decode()
        self.frame=data
        lines=data.splitlines()
        self.head=lines[0].split()
        self.rows=[list(map(int,line.split()[1:])) for line in lines if line.startswith('E ')]
        self.choices=[bytes.fromhex(line[2:]).decode('latin1') for line in lines if line.startswith('A ')]
        return self.head[5]
    def sync(self): return self.raw('0 0 SYNC')
    def send(self,op,a=0,b=0): return self.raw(f'{int(self.head[4])+1} {self.head[2]} {op} {a} {b}')
    def close(self): self.file.close()
def client(folder,env,host,seconds):
    config=json.loads((RELEASE/'client/settings.json').read_text())
    config.update(profilespath=str(folder/'profiles'),ultimaonlinedirectory=str(RELEASE/'assets'),window_size=({'X':1440,'Y':900} if 'TRINSIC_TOWN' in env else {'X':1216,'Y':720}),is_win_maximized=False)
    settings=folder/'settings.json'
    settings.write_text(json.dumps(config))
    with (folder/'client.log').open('w') as log:
        proc=subprocess.Popen([str(SOURCE/'Tools/dotnet/dotnet.exe'),str(BIN/'cuo.dll'),'-settings',str(settings)],cwd=BIN,env=env,stdout=log,stderr=log)
        try:
            end=time.monotonic()+seconds if seconds else float('inf')
            while time.monotonic()<end:
                if proc.poll() is not None: return proc.returncode
                if host.poll() is not None: raise RuntimeError(f'host exited {host.returncode}')
                time.sleep(.3)
            return 0
        finally:
            if proc.poll() is None: proc.terminate()
            proc.wait(8)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('scenario',nargs='?',default='room',choices=['investigation','room','inside','edge','outside'])
    p.add_argument('--run');p.add_argument('--reset',action='store_true');p.add_argument('--capture',type=int,default=0)
    a=p.parse_args()
    fixture=('Trinsic-room' if (ROOT/'fixtures/Trinsic-room.U7').exists() else 'Finnigan-before-chair') if a.scenario=='room' else ('Investigation' if a.scenario=='investigation' else 'Iolo-'+a.scenario)
    with session(a.run or 'player-'+a.scenario,fixture,a.reset) as (folder,env,host):
        if a.capture: env['TRINSIC_CAPTURE']='1'
        sys.exit(client(folder,env,host,a.capture))

