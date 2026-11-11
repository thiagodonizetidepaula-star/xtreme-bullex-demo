"""Focus Pocket V1.7 — automatic payout >=87% read-only discovery.
Sequential only: the unofficial feed supports one active subscription.
A ranked HISTORICAL candidate is not a live, executable signal.
"""
import math
import threading
import time
from urllib.parse import urlsplit
from pathlib import Path

PAYOUT_MIN=87.0

def payout(v):
    if isinstance(v,bool):return None
    try:
        x=float(v)
        return x if math.isfinite(x) and 0<=x<=100 else None
    except (ValueError,TypeError,OverflowError):return None

def ema(values,n):
    k=2/(n+1);r=values[0];o=[]
    for v in values:r=r+(v-r)*k;o.append(r)
    return o

def rsi(values,n=14):
    up=sum(max(0,values[i]-values[i-1]) for i in range(1,n+1))/n
    down=sum(max(0,values[i-1]-values[i]) for i in range(1,n+1))/n
    for i in range(n+1,len(values)):
        d=values[i]-values[i-1]
        up=(up*(n-1)+max(d,0))/n;down=(down*(n-1)+max(-d,0))/n
    return 50 if up==down==0 else 100 if down==0 else 100-100/(1+up/down)


def confirm_five_seconds(ticks, direction, now=None):
    """Reject an M1 signal unless real, continuous, CLOSED 5-second bars agree."""
    now = time.time() if now is None else float(now)
    if direction not in ('CALL','SELL'):
        return False
    samples = []
    for point in ticks:
        try:
            timestamp, price = float(point[0]), float(point[1])
            if math.isfinite(timestamp) and math.isfinite(price) and price > 0 and now-240 <= timestamp <= now+1:
                samples.append((timestamp, price))
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
    samples.sort()
    if not samples or not 0 <= now - samples[-1][0] <= 3:
        return False
    current_bucket = int(now//5)*5
    buckets = {}
    for timestamp, price in samples:
        bucket = int(timestamp//5)*5
        if bucket >= current_bucket:
            continue
        if bucket not in buckets:
            buckets[bucket] = {'time':bucket,'open':price,'high':price,'low':price,'close':price}
        else:
            bar = buckets[bucket]
            bar['high']=max(bar['high'],price)
            bar['low']=min(bar['low'],price)
            bar['close']=price
    bars = [buckets[k] for k in sorted(buckets)][-12:]
    if len(bars)<12 or bars[-1]['time']!=current_bucket-5:
        return False
    if any(bars[i]['time']-bars[i-1]['time']!=5 for i in range(1,len(bars))):
        return False
    closes=[b['close'] for b in bars]
    avg_range=max(sum(max(1e-12,b['high']-b['low']) for b in bars)/len(bars),1e-10)
    fast=ema(closes,4)
    slow=ema(closes,9)
    side=1 if direction=='CALL' else -1
    agreeing_bars=sum((b['close']-b['open'])*side>0 for b in bars[-3:])
    return (
        side*(fast[-1]-slow[-1])>0.04*avg_range
        and side*(fast[-1]-fast[-4])>0.08*avg_range
        and side*(closes[-1]-closes[-5])>0.25*avg_range
        and agreeing_bars>=2
        and side*(samples[-1][1]-closes[-1])>=-0.4*avg_range
    )

def grade(bars):
    """Bollinger curve + EMA + RSI + candle behavior on recent closed M1."""
    if len(bars)<48:return None
    b=bars[-85:];last=b[-1];now=time.time()
    if not 0<=now-(last['time']+60)<=125:return None
    if any(b[i]['time']-b[i-1]['time']!=60 for i in range(len(b)-47,len(b))):return None
    close=[x['close'] for x in b];f=ema(close,9);s=ema(close,21);i=len(b)-1
    ranges=[max(x['high']-x['low'],abs(x['high']-b[j-1]['close']),abs(x['low']-b[j-1]['close'])) for j,x in enumerate(b) if j>=len(b)-22]
    atr=sum(ranges)/len(ranges)
    if atr<=0:return None
    def boll(idx):
        z=close[idx-19:idx+1]
        m=sum(z)/20;sd=math.sqrt(sum((a-m)**2 for a in z)/20)
        return m,m+2*sd,m-2*sd
    mid,upper,lower=boll(i)
    slope_mid=(mid-boll(i-2)[0])/atr
    slope_upper=(upper-boll(i-2)[1])/atr
    prior_slope=(boll(i-3)[0]-boll(i-5)[0])/atr
    curvedown=(prior_slope>-.18 and slope_mid<-.045 and slope_upper<-.02) or (slope_mid<-.11 and slope_upper<-.06 and slope_mid-prior_slope<.07)
    curveup=(prior_slope<.18 and slope_mid>.045 and slope_upper>.02) or (slope_mid>.11 and slope_upper>.06 and slope_mid-prior_slope>-.07)
    sep=(f[-1]-s[-1])/atr;momentum=(f[-1]-f[-4])/atr
    rr=rsi(close);last4=b[-4:];width=max(1e-12,last['high']-last['low'])
    path=close[-10:];movement=sum(abs(path[j]-path[j-1]) for j in range(1,10))
    efficiency=abs(path[-1]-path[0])/movement if movement else 0
    previous_high=max(x['high'] for x in b[-9:-4]);recent_high=max(x['high'] for x in b[-4:])
    previous_low=min(x['low'] for x in b[-9:-4]);recent_low=min(x['low'] for x in b[-4:])
    support=min(x['low'] for x in b[-24:-5]);resistance=max(x['high'] for x in b[-24:-5])
    stretched=abs(last['close']-f[-1])/atr>2.1 or width/atr>2.4
    results=[]
    for side in ('BUY','SELL'):
        buy=side=='BUY'
        wick=(last['high']-max(last['open'],last['close'])) if buy else (min(last['open'],last['close'])-last['low'])
        count=sum(x['close']>x['open'] if buy else x['close']<x['open'] for x in last4)
        rejection=(resistance-.25*atr<last['close']<=resistance) if buy else (support<=last['close']<support+.25*atr)
        structure=(recent_low>previous_low or recent_high>previous_high) if buy else (recent_high<previous_high or recent_low<previous_low)
        checks=[
           (curveup if buy else curvedown),
           (sep>.11 and momentum>.07 if buy else sep<-.11 and momentum<-.07),
           (mid<last['close']<upper+.12*atr if buy else lower-.12*atr<last['close']<mid),
           (count>=3 and (last['close']>last['open'] if buy else last['close']<last['open'])),
           (52<rr<78 if buy else 22<rr<48),
           structure,
           (efficiency>.26 and abs(sep)>.12),
           (not stretched and wick/width<.55 and not rejection and ((upper-last['close']) if buy else (last['close']-lower))>.16*atr)
        ]
        score=sum(bool(c) for c in checks)
        if score>=7 and all(checks[j] for j in (0,1,2,3,4,5,7)) and abs(last['close']-last['open'])/width>.2:
            results.append({'direction':side,'score':score,'total':8,'pattern':'BOLLINGER CURVA '+side,
                'expirySeconds':60 if score==8 else 120,'strength':'FORTE' if score==8 else 'MÉDIO',
                'verifiedLive':False,'status':'CANDIDATO HISTÓRICO — REQUER VALIDAÇÃO AO VIVO',
                'timestamp':last['time'],'checks':[bool(v) for v in checks]})
    return max(results,key=lambda x:x['score']) if results else None


def grade_radar(bars):
    """Independent closed-bar strategies, NOT proof of live win probability."""
    curve=grade(bars)
    if curve:
        curve['direction']='CALL' if curve['direction']=='BUY' else 'SELL'
        return curve
    if len(bars)<48:return None
    b=bars[-85:]
    if any(b[i]['time']-b[i-1]['time']!=60 for i in range(len(b)-47,len(b))):return None
    last=b[-1]
    if not 0<=time.time()-(last['time']+60)<=68:return None
    close=[x['close'] for x in b]
    f=ema(close,9);s=ema(close,21)
    v=rsi(close)
    if v is None:return None
    i=len(b)-1
    atr=sum(max(b[j]['high']-b[j]['low'],abs(b[j]['high']-b[j-1]['close']),abs(b[j]['low']-b[j-1]['close'])) for j in range(i-18,i+1))/19
    if atr<=0:return None
    last4=b[-4:]; body=abs(last['close']-last['open']);bar_range=max(1e-10,last['high']-last['low'])
    support=min(x['low'] for x in b[-25:-5]);resistance=max(x['high'] for x in b[-25:-5])
    results=[]
    for direction in ('CALL','SELL'):
        up=direction=='CALL';sgn=1 if up else -1
        trend=sgn*(f[-1]-s[-1])>.12*atr and sgn*(f[-1]-f[-4])>.06*atr
        rr=(50<v<78) if up else (22<v<50)
        bodies=sum(x['close']>x['open'] if up else x['close']<x['open'] for x in last4)
        candles=bodies>=3 and (last['close']>last['open'] if up else last['close']<last['open'])
        breaked=(last['close']>max(x['high'] for x in b[-6:-1])) if up else (last['close']<min(x['low'] for x in b[-6:-1]))
        pullback=abs(last['close']-f[-1])<.9*atr and ((last['low']<=f[-1]) if up else (last['high']>=f[-1]))
        wick=(last['high']-max(last['open'],last['close'])) if up else (min(last['open'],last['close'])-last['low'])
        risk=body/bar_range>.3 and wick/bar_range<.5 and abs(last['close']-f[-1])<1.8*atr and bar_range<2.4*atr
        near=(resistance-.28*atr<last['close']<=resistance) if up else (support<=last['close']<support+.28*atr)
        strength=abs(close[-1]-close[-8])/max(sum(abs(close[j]-close[j-1]) for j in range(i-6,i+1)),1e-12)>.30
        structure=(max(x['high'] for x in b[-5:])>max(x['high'] for x in b[-12:-5])) if up else (min(x['low'] for x in b[-5:])<min(x['low'] for x in b[-12:-5]))
        for label,entry in (('TENDÊNCIA E PULLBACK',pullback),('ROMPIMENTO DE PREÇO',breaked),('PRICE ACTION',candles and structure)):
            checks=[bool(entry),bool(trend),bool(rr),bool(candles),bool(structure),bool(strength),bool(not near),bool(risk)]
            score=sum(checks)
            if entry and trend and rr and candles and risk and not near and score>=6:
                results.append({'direction':direction,'score':score,'total':8,'checks':checks,'pattern':label,
                                'expirySeconds':60 if score>=7 else 120,'strength':'CONFLUÊNCIA TÉCNICA',
                                'verifiedLive':False,'timestamp':last['time']})
    return max(results,key=lambda x:x['score'],default=None)

class Scanner:
    """Sequential scanner. Pins at most three M1 + five-second validated signals until expiry."""
    def __init__(self,broker):
        self.broker=broker;self.lock=threading.RLock();self.stop_signal=threading.Event()
        self.worker=None;self.stream_users=0;self.eligible=0;self.examined=0;self.round=0
        self.current=None;self.best=[];self.error=None;self.seen_at=0
        self.micro_rejected=0

    def active(self):
        return bool(self.worker and self.worker.is_alive())

    def start(self):
        with self.lock:
            if self.active():return
            if self.stream_users:raise RuntimeError('Pause o gráfico antes de iniciar a busca automática.')
            if not self.broker.connected():raise RuntimeError('Conecte a sessão DEMO antes de iniciar a busca.')
            self.stop_signal=threading.Event();self.examined=0;self.round=0;self.eligible=0
            self.current=None;self.best=[];self.error=None;self.seen_at=0;self.micro_rejected=0
            self.worker=threading.Thread(target=self.run,daemon=True,name='focus-radar-v19')
            self.worker.start()

    def stop(self):
        self.stop_signal.set()

    def status(self):
        now=time.time();ms=int(now*1000)
        with self.lock:
            active=self.active()
            cards=[dict(c) for c in self.best if c.get('endsAtMs',0)>ms]
            return {'running':active and not self.stop_signal.is_set(),
                    'stopping':active and self.stop_signal.is_set(),
                    'minPayout':PAYOUT_MIN,'minConfluence':100,'maxSignals':3,
                    'scanPeriod':'M1','microPeriod':'5S','eligible':self.eligible,
                    'examined':self.examined,'round':self.round,'current':self.current,
                    'candidates':cards[:3],'error':self.error,
                    'microRejected':self.micro_rejected,
                    'lastUpdateMs':int(self.seen_at*1000),'serverTimeMs':ms,
                    'mode':'m1-and-5s-confirmed-at-issuance','readOnly':True}

    def run(self):
        from micro_validation import validate_five_sec
        try:
            while not self.stop_signal.is_set() and self.broker.connected():
                now_ms=int(time.time()*1000)
                with self.lock:
                    self.best=[c for c in self.best if c.get('endsAtMs',0)>now_ms]
                    pinned=list(self.best)
                    self.current=None
                if pinned:
                    # Keep the entire set of 1–3 cards fixed until the last scheduled expiry.
                    remaining=max(c['endsAtMs'] for c in pinned)/1000-time.time()
                    if self.stop_signal.wait(max(.2,min(1.5,remaining))):break
                    continue
                assets=self.broker.get_symbols()
                eligible=sorted(
                    [a for a in assets if a['open'] is True and a.get('payout') is not None
                     and a['payout']>=PAYOUT_MIN],
                    key=lambda a:(-a['payout'],a['symbol']))
                with self.lock:
                    self.round+=1;self.eligible=len(eligible);self.error=None
                if not eligible:
                    with self.lock:self.error='Sem ativos abertos com payout confirmado de 87% ou mais.'
                    if self.stop_signal.wait(10):break
                    continue
                for asset in eligible:
                    if self.stop_signal.is_set() or not self.broker.connected():break
                    with self.lock:
                        if len(self.best)>=3:break
                        self.current=asset['symbol']
                    try:
                        bars=self.broker.candles(asset['symbol'],60)
                        candidate=grade_radar(bars)
                        # Eight of eight M1 filters are mandatory; nine of nine after 5S.
                        if not candidate or candidate.get('score')!=8 or candidate.get('total')!=8:
                            continue
                        moment=time.time()
                        if not bars or not (0<=moment-(bars[-1]['time']+60)<=68):
                            continue
                        # Obtain real closed 5-second candles for THIS asset, not another market.
                        # If the broker cannot provide them, we fail closed: no signal.
                        five=self.broker.candles(asset['symbol'],5)
                        tick_data=self.broker.ticks(asset['symbol'])
                        moment=time.time()
                        micro=validate_five_sec(five,tick_data,candidate['direction'],moment)
                        if not micro:
                            with self.lock:self.micro_rejected+=1
                            continue
                        if moment-(bars[-1]['time']+60)>68:
                            continue
                        newest=next((a for a in self.broker.get_symbols()
                                     if a['symbol']==asset['symbol']),None)
                        if not newest or newest['open'] is not True or newest.get('payout') is None:
                            continue
                        if newest['payout']<PAYOUT_MIN:
                            continue
                        entry_ms=int((math.floor(moment/60)+1)*60000)
                        if entry_ms-int(moment*1000)<8000:
                            continue
                        expiry_seconds=int(candidate.get('expirySeconds',60))
                        # One decision, one fixed entry/expiry. No automatic orders.
                        checks=[bool(v) for v in candidate.get('checks',[])]
                        if len(checks)!=8 or not all(checks):
                            continue
                        candidate.update({
                            'symbol':asset['symbol'],'name':asset['name'],'payout':newest['payout'],
                            'checkedAt':moment,'entryAtMs':entry_ms,
                            'endsAtMs':entry_ms+1000*expiry_seconds,
                            'score':9,'total':9,'verifiedLive':True,'verifiedMicro':True,
                            'tickAtMs':micro['tickAtMs'],'microAtMs':micro['microAtMs'],
                            'microTrend':micro['microTrend'],'checks':checks+[True],
                            'filters':[{'name':label,'ok':passed} for label,passed in zip(
                                ('Bollinger/tendência','EMA 9/21','RSI','Velas','Estrutura',
                                 'Força','Suporte/resistência','Risco','M1 + velas 5S'),
                                checks+[True])],
                            'status':'M1 + 5S alinhados no momento da análise; sinal não é garantia'
                        })
                        with self.lock:
                            if len(self.best)<3 and all(c['symbol']!=asset['symbol'] for c in self.best):
                                self.best.append(candidate)
                    except Exception:
                        # Market feed or 5S history may be unavailable; do not invent a signal.
                        with self.lock:self.micro_rejected+=1
                    finally:
                        with self.lock:
                            self.examined+=1;self.seen_at=time.time()
                        if self.stop_signal.wait(1.3):break
                with self.lock:self.current=None
        except Exception:
            with self.lock:self.error='Fonte indisponível; a busca será retomada após reconectar.'
        finally:
            with self.lock:self.current=None

def install(ns):
    Broker=ns['Broker'];Handler=ns['Handler'];broker=ns['broker'];send=ns['response_json']
    orig_symbols=Broker.get_symbols;original_get=Handler.do_GET;original_post=Handler.do_POST;original_stream=Handler.stream
    scanner=Scanner(broker)
    def get_symbols(self):
        symbols=orig_symbols(self)
        with self.lock:raw=self.api.get_assets() or {}
        for item in symbols:
            entry=raw.get(item['symbol']) or {}
            item['open']=entry.get('is_available') is True or entry.get('is_available')==1
            item['payout']=payout(entry.get('payout'))
        return symbols
    def do_get(self):
        route=urlsplit(self.path).path
        if route in ('/','/index.html'):
            page=Path(ns['ROOT'])/'radar-page.html'
            if page.is_file():
                content=page.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Length',str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
        if route!='/api/scanner/status':return original_get(self)
        if not self.auth():return send(self,401,{'error':'Informe o PIN para consultar o scanner.'})
        return send(self,200,scanner.status())
    def do_post(self):
        p=urlsplit(self.path).path
        if p not in ('/api/scanner/start','/api/scanner/stop'):return original_post(self)
        if not self.auth():return send(self,401,{'error':'Informe o PIN para usar o scanner.'})
        if p.endswith('start'):
            try:scanner.start()
            except RuntimeError as e:return send(self,409,{'error':str(e)})
        else:scanner.stop()
        return send(self,200,scanner.status())
    def stream(self,symbol,period):
        with scanner.lock:
            if scanner.active():return send(self,409,{'error':'Varredura em andamento; pause-a antes de abrir o gráfico.'})
            scanner.stream_users+=1
        try:return original_stream(self,symbol,period)
        finally:
            with scanner.lock:scanner.stream_users=max(0,scanner.stream_users-1)
    Broker.get_symbols=get_symbols
    Handler.do_GET=do_get;Handler.do_POST=do_post;Handler.stream=stream
    ns['auto_scanner']=scanner
