"""Play the separate investigation through native movement and original Usecode inputs."""
import argparse
import heapq
import json
import time
from play import Pipe, RELEASE, ROOT, session

DIRECTIONS=((0,-1),(1,-1),(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1))
DOORS=(270,376,432,433)
FLAGS=(60,61,62,64,66,67,72,90)
def distance(a,b): return max(abs(a[0]-b[0]),abs(a[1]-b[1]))

class Walkthrough:
    def __init__(self,pipe,folder):
        self.p=pipe
        self.folder=folder
        sample=json.loads((RELEASE/'sample.json').read_bytes())
        ox,oy=sample['source_origin']
        solid={r['id'] for r in sample['static_rules'].values() if r['flags']&64}
        self.solid={(ox+s['x'],oy+s['y']) for s in sample['statics'] if not s['z'] and s['id'] in solid}
        self.failed=set()
        self.tried_doors=set()
        self.events=[]
    def actor(self,n): return next((r for r in self.p.rows if r[7]==n),None)
    def xy(self): return tuple(self.actor(0)[3:5])
    def flags(self):
        return dict(zip(FLAGS,map(int,next(l[2:] for l in self.p.frame.splitlines() if l.startswith('Q ')).split())))
    def record(self,what,*details):
        line=[what,self.actor(0)[3:6],self.flags(),*details]
        self.events.append(line)
        print(what,*details,'at',line[1],list(line[2].values()),flush=True)
        with (self.folder/'investigation.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(line)+'\n')
    def go(self,xy,near=0):
        xy=tuple(xy)
        for attempt in range(600):
            start=self.xy()
            if distance(start,xy)<=near:return
            queue=[(0,0,0,start,None)];best={start:0};first=None
            while queue:
                _,_,cost,here,action=heapq.heappop(queue)
                if cost!=best[here]:continue
                if distance(here,xy)<=near:
                    first=action
                    break
                for d,(dx,dy) in enumerate(DIRECTIONS):
                    nxt=(here[0]+dx,here[1]+dy)
                    if not(930<=nxt[0]<=1120 and 2080<=nxt[1]<2352) or (here,nxt) in self.failed:continue
                    price=cost+10+(4 if dx and dy else 0)+(50 if nxt in self.solid else 0)
                    if price>=best.get(nxt,10**8):continue
                    h=distance(nxt,xy)*10
                    best[nxt]=price
                    heapq.heappush(queue,(price+h,h,price,nxt,action or (d,nxt)))
            if first is None:break
            d,nxt=first
            self.p.send('STEP',d)
            if self.xy()!=nxt:
                doors=sorted((r for r in self.p.rows if r[1] in DOORS and distance(r[3:5],nxt)<=1 and distance(r[3:5],start)<=2 and (r[0],r[2],xy) not in self.tried_doors),key=lambda r:distance(r[3:5],nxt))
                if doors:
                    door=doors[0]
                    self.tried_doors.add((door[0],door[2],xy))
                    self.p.send('USE',door[0]);self.p.sync()
                    self.p.send('STEP',d)
                if self.xy()!=nxt:self.failed.add((start,nxt))
            if int(self.p.head[9]):
                self.talk([],started=True)
        raise RuntimeError(('cannot walk',self.xy(),xy,len(self.failed)))
    def words(self):
        return bytes.fromhex(next(l[2:] for l in self.p.frame.splitlines() if l.startswith('T '))).decode('latin1')
    def talk(self,topics,n=None,started=False):
        if not started:
            actor=self.actor(n)
            if not actor:raise ValueError(('missing NPC',n,self.xy()))
            self.p.send('USE',actor[0])
        left=list(topics);last='';visited=False
        for _ in range(240):
            self.p.sync()
            mode=int(self.p.head[9]); token=int(self.p.head[10])
            if not mode:
                if visited:break
                time.sleep(.025);continue
            visited=True
            words=self.words()
            if words:last=words
            if mode==1:self.p.send('ANSWER',token,0)
            elif mode==2:
                choice=next((item for item in left if item in self.p.choices),None)
                if not choice and self.p.choices==['Yes','No']:choice='Yes'
                if not choice: raise ValueError(('unhandled answers',self.p.choices,left,last))
                self.record('answer',n,choice)
                if choice in left:left.remove(choice)
                self.p.send('ANSWER',token,self.p.choices.index(choice))
            elif mode==3:
                values={'Spektran':120,'Buccaneer':60,'Terfin':120,'Dagger':0,'Skara':60 if 'longitude runs' in last else 30,'Deep Forest':60}
                val=next(v for k,v in values.items() if k.lower() in last.lower())
                self.record('geography',last,val)
                assert self.p.send('NUMBER',token,val)=='ok'
            else:raise ValueError(('unexpected prompt',mode))
        else:raise RuntimeError(('dialogue timed out',n,last))
    def check(self,milestone):
        self.record(milestone)
        assert self.p.send('SAVE')=='ok'
    def run(self,stage):
        if stage<=0:
            self.go((1070,2208))
            door=next(r for r in self.p.rows if r[1] in DOORS and r[3:5]==[1071,2207])
            self.p.send('USE',door[0]);self.p.sync()
            self.go((1070,2207));self.go((1069,2197))
            key=next(r for r in self.p.rows if r[1]==641 and r[3:5]==[1068,2197])
            bag=next(r for r in self.p.rows if r[1]==801 and r[6]==self.actor(0)[0])
            assert self.p.send('MOVE',key[0],bag[0])=='ok' and self.flags()[60]
            assert any(r[0]==key[0] and r[6]==bag[0] for r in self.p.rows)
            self.check('stables and key')
        if stage<=1:
            if not self.actor(12):self.go((984,2202))
            actor=self.actor(12)
            self.go(actor[3:5],2)
            self.talk(['Yes','a key','bye'],12)
            assert self.flags()[72]
            self.check('key reported')
        if stage<=2:
            self.go((977,2137))
            door=next(r for r in self.p.rows if r[1] in DOORS and distance(r[3:5],(975,2137))<=1)
            if door[2]==0:
                self.p.send('USE',door[0]); self.p.sync()
            self.go((974,2136))
            self.go((971,2139))
            for x in range(970,964,-1):self.go((x,2139))
            for xy in ((965,2138),(965,2137),(965,2136),(971,2136),(971,2133)):self.go(xy)
            chest=next(r for r in self.p.rows if r[1]==522 and r[3:5]==[972,2132])
            key=next(r for r in self.p.rows if r[1]==641 and r[6])
            self.p.send('USE',key[0]);self.p.sync()
            assert self.p.head[9]=='4',self.p.head
            assert self.p.send('TARGET',int(self.p.head[10]),chest[0])=='ok'
            self.p.sync()
            assert self.flags()[62] and any(r[0]==chest[0] and r[1]==800 for r in self.p.rows)
            self.p.send('USE',chest[0]);self.p.sync()
            scroll=next(r for r in self.p.rows if r[1]==797 and r[6]==chest[0])
            self.p.send('USE',scroll[0]);self.p.sync()
            for _ in range(12):
                if self.p.head[9]=='1':break
                self.p.sync()
            assert self.p.head[9]=='1' and 'delivery' in self.words(),self.p.head
            self.record('estate scroll',self.words())
            self.talk([],started=True)
            self.p.send('CLOSE');self.p.sync()
            self.check('estate unlocked')
        if stage<=3:
            if self.actor(0)[5]>0:
                for xy in ((971,2136),(965,2136),(965,2137),(965,2138),(965,2139),(971,2139)):self.go(xy)
            if not self.actor(2):self.go((970,2139))
            self.go(self.actor(2)[3:5],2)
            self.talk(['Avatar','murder','find','something','man','hook','No','bye'],2)
            assert self.flags()[67]
            self.check('Spark witness')
        if stage<=4:
            # Spark can finish his conversation inside the estate. Use the same
            # east door used on entry before planning the long walk to the docks.
            x,y=self.xy()
            if 964<x<975 and 2130<y<2141:
                door=next((r for r in self.p.rows if r[1] in DOORS and r[3:5]==[975,2137] and r[5]==0),None)
                if door and door[2]%4!=1:
                    self.p.send('USE',door[0]);self.p.sync()
                for xy in ((974,2135),(976,2135),(977,2138),(978,2142)):self.go(xy)
            if not self.actor(13):self.go((957,2257))
            self.go(self.actor(13)[3:5],2)
            self.talk(['murder','knocked','blow','Crown Jewel','bye'],13)
            assert self.flags()[64]
            self.check('Gilberto witness')
        if stage<=5:
            if not self.actor(12):self.go((986,2205))
            self.go(self.actor(12)[3:5],2)
            self.talk(['murder','report','Yes','blacksmith','a key','a chest','all of these','Yes','hook','Crown Jewel','Yes','bye'],12)
            assert self.flags()[61]
            self.check('password earned')
        if stage<=6:
            if not self.actor(14):self.go((1092,2215))
            self.go(self.actor(14)[3:5],2)
            self.talk(['password','Blackbird','bye'],14)
            self.go((1100,2214))
            gate=next(r for r in self.p.rows if r[1]==271 and abs(r[3]-1102)<4)
            assert gate[5]>0,gate
            for x in range(1101,1108): self.go((x,2214))
            self.check('outside east gate')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--stage',type=int,default=0);ap.add_argument('--run',default='town-journey-proof');args=ap.parse_args()
    with session(args.run,'Investigation',not args.stage) as (folder,env,host):
        pipe=Pipe(env['TRINSIC_PIPE'],host)
        Walkthrough(pipe,folder).run(args.stage)
