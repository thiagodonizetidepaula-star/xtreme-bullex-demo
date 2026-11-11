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
    def __init__(self,broker):
        self.broker=broker;self.lock=threading.RLock();self.stop_signal=threading.Event()
        self.worker=None;self.stream_users=0;self.eligible=0;self.examined=0;self.round=0
        self.current=None;self.best=[];self.error=None;self.seen_at=0
    def active(self):return bool(self.worker and self.worker.is_alive())
    def start(self):
        with self.lock:
            if self.active():return
            if self.stream_users:raise RuntimeError('Pause o gráfico ao vivo antes da busca automática.')
            if not self.broker.connected():raise RuntimeError('Conecte a sessão DEMO antes de iniciar a varredura.')
            self.stop_signal=threading.Event();self.examined=0;self.round=0;self.eligible=0;self.current=None
            self.best=[];self.error=None;self.seen_at=0
            self.worker=threading.Thread(target=self.run,daemon=True);self.worker.start()
    def stop(self):self.stop_signal.set()
    def status(self):
        with self.lock:
            active=self.active();now=time.time()
            return {'running':active and not self.stop_signal.is_set(),'stopping':active and self.stop_signal.is_set(),
                'minPayout':PAYOUT_MIN,'scanPeriod':'M1','eligible':self.eligible,'examined':self.examined,
                'round':self.round,'current':self.current,'candidates':[dict(x,liveQuoteFresh=bool(x.get('verifiedLive') and x.get('tickAtMs') and 0<=now*1000-x['tickAtMs']<4500)) for x in self.best if now-x['checkedAt']<65 and x.get('entryAtMs',0)>now*1000+2500][:8],
                'error':self.error,'lastUpdateMs':int(self.seen_at*1000),'serverTimeMs':int(now*1000),
                'mode':'historic-watchlist-not-live-trade','readOnly':True}
    def run(self):
        try:
            while not self.stop_signal.is_set() and self.broker.connected():
                assets=self.broker.get_symbols()
                eligible=sorted([x for x in assets if x['open'] is True and x.get('payout') is not None and x['payout']>=PAYOUT_MIN],
                    key=lambda x:(-x['payout'],x['symbol']))
                with self.lock:self.round+=1;self.eligible=len(eligible);self.best=[]
                if not eligible:
                    with self.lock:self.error='Nenhum ativo aberto com payout confirmado ≥87%.'
                    if self.stop_signal.wait(10):break
                    continue
                with self.lock:self.error=None
                for a in eligible:
                    if self.stop_signal.is_set() or not self.broker.connected():break
                    with self.lock:self.current=a['symbol']
                    try:
                        bars=self.broker.candles(a['symbol'],60)
                        candidate=grade_radar(bars)
                        item=next((x for x in self.broker.get_symbols() if x['symbol']==a['symbol']),None)
                        if item and item['open'] is True and item.get('payout') is not None and item['payout']>=PAYOUT_MIN and candidate:
                            moment=time.time()
                            if moment-(bars[-1]['time']+60)>68:
                                candidate=None
                            else:
                                ticks=self.broker.ticks(a['symbol'])
                                tick=max((t for t in ticks if 0<=moment-t[0]<4),default=None,key=lambda t:t[0])
                                live=bool(tick and (tick[1]>=bars[-1]['close']-.2*(bars[-1]['high']-bars[-1]['low']) if candidate['direction']=='CALL'
                                                    else tick[1]<=bars[-1]['close']+.2*(bars[-1]['high']-bars[-1]['low'])))
                                entry=int((math.floor(moment/60)+1)*60000)
                                candidate.update({'symbol':a['symbol'],'name':a['name'],'payout':item['payout'],
                                                  'checkedAt':moment,'entryAtMs':entry,'verifiedLive':live,
                                                  'tickAtMs':int(tick[0]*1000) if tick else None,
                                                  'filters':[{'name':name,'ok':v} for name,v in zip(
                                                     ('Bollinger/tendência','EMA 9/21','RSI','Velas','Estrutura',
                                                      'Força','Suporte/resistência','Risco'),candidate.get('checks',[False]*8))]})
                                if entry-moment*1000<8000:candidate=None
                            with self.lock:
                                if candidate:
                                    self.best=[x for x in self.best if x['symbol']!=a['symbol']]+[candidate]
                                self.best=sorted(self.best,key=lambda x:(-x['score'],-x['payout']))[:8]
                    except Exception:pass # Unofficial API may reject an asset; continue.
                    with self.lock:self.examined+=1;self.seen_at=time.time()
                    if self.stop_signal.wait(1.3):break
                with self.lock:self.current=None
        except Exception:
            with self.lock:self.error='Fonte indisponível. Reinicie a busca quando reconectar.'
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
