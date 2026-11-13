from targets import *
def variants(r):
    keys={(s,f) for s,f in r}
    for s in {k[0] for k in r}:
        keys.update((s,f) for f in range(abs(counts[s])))
        if counts[s]<0:keys.update((s,32+f) for f in range(min(32,abs(counts[s]))))
    return keys
if __name__=='__main__':
    r,_=census();empty=0;bad=[];keys=variants(r)
    for s,f in sorted(keys):
        try:
            im,_=src(s,f)
            if not im.getbbox():empty+=1;continue
            c,key,g,m,n=classify(s,f&31 if (s,f) not in RULES and f>=32 and counts[s]<0 and s not in bodyids else f,im);target(key)
        except Exception as e:bad.append((s,f,repr(e)))
    print(len(keys),empty,len(bad),bad[:80]);print([(x,hex(LABELS[x][0])) for x in LABELS if any(w in x for w in ['pie','cheese','egg','leek','potato','fish steak','cooked bird','butter','baked'])][:80])

