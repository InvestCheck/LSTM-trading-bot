import csv, numpy as np
from datetime import datetime, timezone

_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%Y-%m-%dT%H:%M:%S",
                 "%Y-%m-%dT%H:%M","%m/%d/%Y %H:%M:%S","%m/%d/%Y %H:%M",
                 "%Y-%m-%d","%m/%d/%Y")

def parse_ts(s):
    """Parse a time field into epoch seconds. Accepts epoch seconds, epoch
    milliseconds, or a datetime string (FirstRateData 'YYYY-MM-DD HH:MM:SS',
    US 'MM/DD/YYYY HH:MM', ISO 8601, date only)."""
    s=s.strip()
    try:
        v=float(s)
        if v>1e11: v/=1000.0      # milliseconds -> seconds
        return int(v)
    except ValueError:
        pass
    for fmt in _TIME_FORMATS:
        try: return int(datetime.strptime(s,fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError: continue
    raise ValueError("unrecognized time format: %r" % s)

def load_series(path):
    """Load OHLC from a CSV with columns time,open,high,low,close[,volume].
    Time may be epoch (s or ms) OR a datetime string; a header row is skipped
    automatically. Returns T,O,H,L,C arrays, T in epoch seconds, sorted ascending."""
    T=[];O=[];H=[];L=[];C=[]
    with open(path, newline="") as f:
        for r in csv.reader(f):
            if len(r)<5: continue
            try: ts=parse_ts(r[0]); o=float(r[1]); h=float(r[2]); l=float(r[3]); c=float(r[4])
            except (ValueError, IndexError): continue   # header or junk row
            T.append(ts);O.append(o);H.append(h);L.append(l);C.append(c)
    if not T: raise ValueError("no rows parsed from %s" % path)
    idx=np.argsort(T)
    return (np.array(T)[idx],np.array(O,float)[idx],np.array(H,float)[idx],
            np.array(L,float)[idx],np.array(C,float)[idx])

def exit_sim(O,H,L,C,e21,e200,A,t0,entry,stop,d):
    """Replay the exit engine for one position; returns the realized R multiple.
    Mirrors the manager inside run() exactly: parabolic exit at 3.5xATR from the
    21 EMA, phase1 stop with a 200 EMA wick ratchet gated until 0.5R separation,
    breakeven at +1R, then a 21 EMA close trail in phase2. Used by the random
    entry control so the monkey runs through the identical exits."""
    R=abs(entry-stop)
    if R<=0: return None
    phase=1; st=float(stop)
    for t in range(t0+1,len(C)):
        ex=None
        if d>0:
            if H[t]-e21[t]>=3.5*A[t]: ex=e21[t]+3.5*A[t]
            if ex is None and phase==1:
                if L[t]<=st: ex=st
                elif H[t]>=entry+R: phase=2; st=entry
            if ex is None and phase==2:
                if L[t]<=entry: ex=entry
                elif C[t]<e21[t]: ex=C[t]
            if ex is None and phase==1 and e200[t]<C[t] and e200[t]>st and abs(e200[t]-entry)>=0.5*R: st=e200[t]
        else:
            if e21[t]-L[t]>=3.5*A[t]: ex=e21[t]-3.5*A[t]
            if ex is None and phase==1:
                if H[t]>=st: ex=st
                elif L[t]<=entry-R: phase=2; st=entry
            if ex is None and phase==2:
                if H[t]>=entry: ex=entry
                elif C[t]>e21[t]: ex=C[t]
            if ex is None and phase==1 and e200[t]>C[t] and e200[t]<st and abs(e200[t]-entry)>=0.5*R: st=e200[t]
        if ex is not None: return ((ex-entry)/R)*d
    return ((C[-1]-entry)/R)*d

def ema(x,n):
    a=2/(n+1); o=np.zeros_like(x,float); o[0]=x[0]
    for i in range(1,len(x)): o[i]=a*x[i]+(1-a)*o[i-1]
    return o
def atr(h,l,c,n=14):
    tr=np.zeros(len(c)); tr[0]=h[0]-l[0]
    for i in range(1,len(c)): tr[i]=max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))
    o=np.zeros(len(c)); o[0]=tr[0]; a=1/n
    for i in range(1,len(c)): o[i]=a*tr[i]+(1-a)*o[i-1]
    return o
def pivots(h,l,k=3):
    n=len(h); ph=[];pl=[]
    for i in range(k,n-k):
        if h[i]==h[i-k:i+k+1].max(): ph.append(i)
        if l[i]==l[i-k:i+k+1].min(): pl.append(i)
    return ph,pl

def run(name,path,mult,start_ts,tol=0.0015,toltouch=0.0010,touch_band=0.0005,brk_tol=0.0002,SPANDAYS=7,K=3,MINSPAN=168,MINTOUCH=3,MAXSPAN=1200,CAP=4000.0,TGAP=6,causal=True,return_open=False,tick=0.0,slip_ticks=0.0,slip_frac=0.0,fill='intrabar'):
    # DEFAULTS ARE THE HONEST SETTINGS: causal=True, fill='intrabar'.
    # To reproduce the older, inflated behaviour explicitly, pass
    # causal=False, fill='open'. See README "What changed in this build".
    # slip_frac: round-trip slippage as a FRACTION of price (e.g. 0.0002 = 2 bps/side),
    #   deducted in R at exit. Use this for cross-symbol scans on ratio-adjusted data
    #   where a fixed tick size has no clean mapping. tick/slip_ticks still work for a
    #   single real contract.
    # fill model for the entry:
    #   'open'     LEGACY, no longer the default. Requires a break THROUGH the
    #              line by `tol` and fills at the line, or at the bar open if it
    #              gapped. Optimistic: it silently drops the marginal touches a
    #              live resting order would take. Kept only for comparison.
    #   'intrabar' (default) resting-stop model: trigger the moment price TOUCHES the line
    #              (no break-through buffer) and fill at the line / gap open. Adds the
    #              marginal touches a live resting order would take. Use with causal=True
    #              and slip_ticks>0 for the honest number.
    #   'next'     fill at the next bar open O[t+1] (the bundle audit's conservative fix).
    intrabar = (fill=='intrabar'); nextbar = (fill=='next')
    T,O,H,L,C=load_series(path); n=len(C)
    e21=ema(C,21);e200=ema(C,200);A=atr(H,L,C,14)
    PH,PL=pivots(H,L,K)
    start=int(np.searchsorted(T,start_ts))

    sh=[];rh=[];ih=0;il=0;last_ph=None;last_pl=None
    pos=None;trades=[];traded=set();FAN_S=[];FAN_R=[]
    def sl_low(i,j): return (L[j]-L[i])/(j-i)
    def sl_high(i,j): return (H[j]-H[i])/(j-i)
    def sepidx(idxs):
        out=[]
        for z in sorted(idxs):
            if not out or z-out[-1]>=TGAP: out.append(int(z))
        return out
    def refit(piv,arr,sign,a,m,t,hv):
        # fit a line whose FIRST anchor is a fan node (connectivity) and which spans 7+ calendar
        # days from anchor to entry, with 3+ reaching touches and no wick piercing it.
        cand=[]
        for p in piv:
            if p<a or p>t: continue
            if causal and p>t-K: continue   # only pivots confirmed as of bar t
            ln=arr[a]+m*(p-a); g=(arr[p]-ln) if sign>0 else (ln-arr[p])
            if -brk_tol*arr[p] <= g <= 0.005*arr[p]: cand.append(int(p))
        if len(cand)<MINTOUCH: return None
        best=None
        for x in range(len(cand)):
            p1=cand[x]
            if p1 not in hv: continue
            if (T[t]-T[p1]) < SPANDAYS*86400: continue
            for y in range(x+1,len(cand)):
                p2=cand[y]
                if p2-p1<TGAP: continue
                s=(arr[p2]-arr[p1])/(p2-p1)
                if (sign>0 and s<=0) or (sign<0 and s>=0): continue
                zz=np.arange(p1,t); lnz=arr[p1]+s*(zz-p1)
                if (sign>0 and np.any(L[p1:t]<lnz-brk_tol*L[p1:t])) or (sign<0 and np.any(H[p1:t]>lnz+brk_tol*H[p1:t])): continue
                lnt=arr[p1]+s*(t-p1); lnp=arr[p1]+s*(t-1-p1)
                if sign>0:
                    if intrabar:
                        if not (L[t]<=lnt and L[t-1]>lnp): continue
                    elif not (L[t]<lnt-tol*L[t] and L[t-1]>=lnp-brk_tol*L[t-1]): continue
                else:
                    if intrabar:
                        if not (H[t]>=lnt and H[t-1]<lnp): continue
                    elif not (H[t]>lnt+tol*H[t] and H[t-1]<=lnp+brk_tol*H[t-1]): continue
                if causal:
                    zz=np.arange(p1,t); lnz=arr[p1]+s*(zz-p1)
                    g=(arr[p1:t]-lnz) if sign>0 else (lnz-arr[p1:t])
                    mask=(g>=-brk_tol*arr[p1:t])&(g<=touch_band*arr[p1:t])
                    tt=sepidx([int(z) for z in zz[mask]])
                else:
                    tt=[]
                    for p in cand:
                        if p<p1 or p>t: continue
                        ln=arr[p1]+s*(p-p1); g=(arr[p]-ln) if sign>0 else (ln-arr[p])
                        if -brk_tol*arr[p] <= g <= touch_band*arr[p]: tt.append(p)
                    tt=sepidx(tt)
                if len(tt)>=MINTOUCH:
                    score=(len(tt),p2-p1)
                    if best is None or score>best[0]: best=(score,int(p1),float(s),int(p2),tt)
        if best is None: return None
        _,p1,s,p2,tt=best
        return (p1,s,p2,tt)

    for t in range(210,n):
        # confirm pivots into hulls (causal)
        while il<len(PL) and PL[il]+K<=t:
            p=PL[il]
            while len(sh)>=2 and sl_low(sh[-2],sh[-1])>=sl_low(sh[-1],p): sh.pop()
            if sh and sl_low(sh[-1],p)>0: FAN_S.append((int(sh[-1]),int(p)))
            sh.append(p); last_pl=p; il+=1
        while ih<len(PH) and PH[ih]+K<=t:
            p=PH[ih]
            while len(rh)>=2 and sl_high(rh[-2],rh[-1])<=sl_high(rh[-1],p): rh.pop()
            if rh and sl_high(rh[-1],p)<0: FAN_R.append((int(rh[-1]),int(p)))
            rh.append(p); last_ph=p; ih+=1

        # manage open position (exit engine: 200wick ratchet + BE@1R + 21close + parabolic)
        if pos:
            d=pos['dir'];ex=None;why=''
            if d>0:
                if H[t]-e21[t]>=3.5*A[t]: ex=e21[t]+3.5*A[t];why='parabolic'
                if ex is None and pos['phase']==1:
                    if L[t]<=pos['stop']: ex=pos['stop'];why='stop'
                    elif H[t]>=pos['entry']+pos['R']: pos['phase']=2;pos['stop']=pos['entry']
                if ex is None and pos['phase']==2:
                    if L[t]<=pos['entry']: ex=pos['entry'];why='BE'
                    elif C[t]<e21[t]: ex=C[t];why='21EMA'
            else:
                if e21[t]-L[t]>=3.5*A[t]: ex=e21[t]-3.5*A[t];why='parabolic'
                if ex is None and pos['phase']==1:
                    if H[t]>=pos['stop']: ex=pos['stop'];why='stop'
                    elif L[t]<=pos['entry']-pos['R']: pos['phase']=2;pos['stop']=pos['entry']
                if ex is None and pos['phase']==2:
                    if H[t]>=pos['entry']: ex=pos['entry'];why='BE'
                    elif C[t]>e21[t]: ex=C[t];why='21EMA'
            if ex is not None:
                rr=((ex-pos['entry'])/pos['R'])*d
                if pos['R']:                                 # entry + exit slippage, in R
                    if slip_ticks and tick: rr-=(2.0*slip_ticks*tick)/pos['R']
                    if slip_frac:           rr-=(2.0*slip_frac*pos['entry'])/pos['R']
                pos.update(exit_idx=int(t),exit=float(ex),R=round(rr,6),why=why,stop_final=float(pos['stop']),ratcheted=bool(abs(pos['stop']-pos['stop0'])>1e-6)); trades.append(pos); pos=None
            else:
                if pos['phase']==1:
                    if d>0 and e200[t]<C[t] and e200[t]>pos['stop'] and abs(e200[t]-pos['entry'])>=0.5*pos['R']: pos['stop']=e200[t]
                    if d<0 and e200[t]>C[t] and e200[t]<pos['stop'] and abs(e200[t]-pos['entry'])>=0.5*pos['R']: pos['stop']=e200[t]

        if pos is not None or t<start: continue

        # SUPPORT break -> SHORT : scan connected hull edges, oldest-shallowest first
        sig=None
        for i in range(1,len(sh)):
            a,b=sh[i-1],sh[i]
            if (a,b,'s') in traded: continue
            m=sl_low(a,b)
            if m<=0 or (t-a)<MINSPAN or (t-a)>MAXSPAN: continue
            lt=L[a]+m*(t-a); lp=L[a]+m*(t-1-a)
            if intrabar:
                if not (L[t]<=lt and L[t-1]>lp): continue
            elif not (L[t]<lt-tol*L[t] and L[t-1]>=lp-tol*L[t-1]): continue
            # respected: no low below line over [a, t-1]
            zz=np.arange(a,t)
            if np.any(L[a:t] < L[a]+m*(zz-a) - tol*L[a:t]): continue
            rf=refit(PL,L,1,a,m,t,set(sh))
            if rf is None: continue
            a2,m2,last2,tch=rf
            lt=L[a2]+m2*(t-a2)
            if nextbar:
                if t+1>=n: continue
                entry=O[t+1]
            else:
                entry=O[t] if O[t]<lt else lt
            floor=1.0*A[t]
            cands=[]
            for j in range(1,len(rh)):
                aa,bb=rh[j-1],rh[j]; mm=(H[bb]-H[aa])/(bb-aa); val=H[aa]+mm*(t-aa)
                if val>entry+floor and (val-entry)*mult<=CAP and bb>=t-720 and aa>=t-2880: cands.append((float(val),int(aa),int(bb)))
            cands.sort()
            pick=cands[0] if cands else None
            if pick: stop=pick[0]; saf=dict(a=pick[1],ya=round(float(H[pick[1]]),4),b=pick[2],yb=round(float(H[pick[2]]),4),kind='res'); stop_src='auto'
            elif e200[t]>entry+floor and (e200[t]-entry)*mult<=CAP: stop=float(e200[t]); saf=None; stop_src='ema'
            else: continue
            Rd=stop-entry
            if Rd<=0: continue
            sig=dict(dir=-1,entry=float(entry),stop=float(stop),R=Rd,phase=1,t0=int(t),
                     a=int(a2),ya=round(float(L[a2]),4),m=float(m2),last=int(last2),kind='sup',tch=tch,stop0=float(stop),saf=saf,stop_src=stop_src); traded.add((a,b,'s')); break
        if sig is None:
            for i in range(1,len(rh)):
                a,b=rh[i-1],rh[i]
                if (a,b,'r') in traded: continue
                m=sl_high(a,b)
                if m>=0 or (t-a)<MINSPAN or (t-a)>MAXSPAN: continue
                lt=H[a]+m*(t-a); lp=H[a]+m*(t-1-a)
                if intrabar:
                    if not (H[t]>=lt and H[t-1]<lp): continue
                elif not (H[t]>lt+tol*H[t] and H[t-1]<=lp+tol*H[t-1]): continue
                zz=np.arange(a,t)
                if np.any(H[a:t] > H[a]+m*(zz-a) + tol*H[a:t]): continue
                rf=refit(PH,H,-1,a,m,t,set(rh))
                if rf is None: continue
                a2,m2,last2,tch=rf
                lt=H[a2]+m2*(t-a2)
                if nextbar:
                    if t+1>=n: continue
                    entry=O[t+1]
                else:
                    entry=O[t] if O[t]>lt else lt
                floor=1.0*A[t]
                cands=[]
                for j in range(1,len(sh)):
                    aa,bb=sh[j-1],sh[j]; mm=(L[bb]-L[aa])/(bb-aa); val=L[aa]+mm*(t-aa)
                    if val<entry-floor and (entry-val)*mult<=CAP and bb>=t-720 and aa>=t-2880: cands.append((float(val),int(aa),int(bb)))
                cands.sort(reverse=True)
                pick=cands[0] if cands else None
                if pick: stop=pick[0]; saf=dict(a=pick[1],ya=round(float(L[pick[1]]),4),b=pick[2],yb=round(float(L[pick[2]]),4),kind='sup'); stop_src='auto'
                elif e200[t]<entry-floor and (entry-e200[t])*mult<=CAP: stop=float(e200[t]); saf=None; stop_src='ema'
                else: continue
                Rd=entry-stop
                if Rd<=0: continue
                sig=dict(dir=1,entry=float(entry),stop=float(stop),R=Rd,phase=1,t0=int(t),
                         a=int(a2),ya=round(float(H[a2]),4),m=float(m2),last=int(last2),kind='res',tch=tch,stop0=float(stop),saf=saf,stop_src=stop_src); traded.add((a,b,'r')); break
        if sig: pos=sig

    arr=np.array([x['R'] for x in trades]) if trades else np.array([])
    w=arr[arr>0.01];ls=arr[arr<-0.01]
    summ=dict(symbol=name,trades=len(trades),win=round(100*(arr>0.01).mean(),1) if arr.size else 0,
        totalR=round(arr.sum(),1) if arr.size else 0,avgR=round(arr.mean(),2) if arr.size else 0,
        PF=round(w.sum()/abs(ls.sum()),2) if ls.size else None,
        long=sum(1 for x in trades if x['dir']==1),short=sum(1 for x in trades if x['dir']==-1))
    if return_open:
        return summ,trades,FAN_S,FAN_R,pos   # pos is the position open at the last bar, or None
    return summ,trades,FAN_S,FAN_R
