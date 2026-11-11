"""Focus Pocket V3: one 5-second signal at a time; no legacy RSI/M1 strategies.

A lack of real Pocket Option 5s candles results in AGUARDAR, not a fake signal.
"""
import math
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from strategy_5s import evaluate_5s

PAYOUT_MIN=87.0

def payout(v):
    if isinstance(v,bool):return None
    try:
        x=float(v);return x if math.isfinite(x) and 0<=x<=100 else None
    except (ValueError,TypeError,OverflowError):return None

class Scanner:
    def __init__(self,broker):
        from signal_ledger import SignalLedger
        self.broker=broker;self.lock=threading.RLock();self.stop_signal=threading.Event()
        self.worker=None;self.stream_users=0;self.eligible=0;self.examined=0;self.round=0
        self.current=None;self.error=None;self.seen_at=0;self.missing5s=0
        # Dedicated ledger for the new 5S strategy, keeping former M1 records separate.
        self.ledger=SignalLedger(path='/tmp/focus-pocket-only-5s-signals.sqlite3')
        self.best=self.ledger.restore_pending()

    def active(self):
        return bool(self.worker and self.worker.is_alive())

    def start(self):
        with self.lock:
            if self.active():return
            if self.stream_users:raise RuntimeError('Feche o monitor antes de iniciar o radar.')
            if not self.broker.connected():raise RuntimeError('Sessão DEMO ainda desconectada.')
            self.stop_signal=threading.Event()
            self.worker=threading.Thread(target=self.run,daemon=True,name='focus-only-five-seconds')
            self.worker.start()

    def stop(self):
        self.stop_signal.set()

    def status(self):
        now=time.time()
        with self.lock:
            data={'running':self.active() and not self.stop_signal.is_set(),
                  'stopping':self.active() and self.stop_signal.is_set(),
                  'minPayout':PAYOUT_MIN,'maxSignals':1,'scanPeriod':'5S',
                  'signalExpirySeconds':5,'eligible':self.eligible,'examined':self.examined,
                  'round':self.round,'current':self.current,'missing5s':self.missing5s,
                  'candidates':[dict(c) for c in self.best if c['endsAtMs']>now*1000][:1],
                  'error':self.error,'lastUpdateMs':int(self.seen_at*1000),
                  'serverTimeMs':int(now*1000),'mode':'single-five-second-experimental',
                  'readOnly':True}
        data.update(self.ledger.status())
        return data

    def run(self):
        from signal_ledger import verify_outcome
        try:
            while not self.stop_signal.is_set() and self.broker.connected():
                with self.lock:
                    pinned=self.best[0] if self.best else None
                    self.current=None
                if pinned:
                    expiry=pinned['endsAtMs']/1000.0
                    now=time.time()
                    if now<expiry+1:
                        if self.stop_signal.wait(min(0.7,max(.1,expiry+1-now))):break
                        continue
                    if now>expiry+50:
                        self.ledger.unverifiable(pinned['signalId'],
                            'Histórico real 5S de entrada/vencimento indisponível')
                        with self.lock:self.best=[]
                        continue
                    try:
                        # No M1 fallback: 5-second records only, same asset.
                        real5s=self.broker.candles(pinned['symbol'],5)
                        verified=verify_outcome(pinned,real5s,time.time())
                        if verified and self.ledger.finish(pinned['signalId'],verified):
                            with self.lock:self.best=[]
                            continue
                    except Exception:
                        pass
                    if self.stop_signal.wait(.7):break
                    continue
                assets=self.broker.get_symbols()
                eligible=sorted([a for a in assets if a['open'] is True
                    and a.get('payout') is not None and a['payout']>=PAYOUT_MIN],
                    key=lambda a:(-a['payout'],a['symbol']))
                with self.lock:
                    self.round+=1;self.eligible=len(eligible);self.error=None
                if not eligible:
                    with self.lock:self.error='Nenhum ativo aberto com payout confirmado de 87% ou mais.'
                    if self.stop_signal.wait(8):break
                    continue
                found=False
                for asset in eligible:
                    if self.stop_signal.is_set() or not self.broker.connected():break
                    with self.lock:
                        self.current=asset['symbol']
                        if self.best:break
                    try:
                        # Always require real closed 5-second candles; never guess ticks.
                        bars=self.broker.candles(asset['symbol'],5)
                        moment=time.time()
                        signal=evaluate_5s(bars,now=moment)
                        if not signal:
                            with self.lock:self.missing5s+=1
                            continue
                        fresh=next((a for a in self.broker.get_symbols()
                            if a['symbol']==asset['symbol']),None)
                        if not fresh or fresh['open'] is not True or fresh.get('payout') is None:
                            continue
                        if fresh['payout']<PAYOUT_MIN:continue
                        checked=time.time()
                        entry=int((math.floor(checked/5)+1)*5000)
                        # Do not issue signals without enough notice for manual reaction.
                        if entry-checked*1000<1750:continue
                        # The last candle must be immediately before the proposed entry.
                        if entry//1000-(int(bars[-1]['time'])+5)!=5:continue
                        signal.update({'symbol':asset['symbol'],'name':asset['name'],
                            'payout':fresh['payout'],'checkedAt':checked,
                            'entryAtMs':entry,'endsAtMs':entry+5000,
                            'verifiedM1':False,'verifiedLive':False,'verified5S':True,
                            'qualityLabel':'CRITÉRIOS DE CONTINUAÇÃO 5S','winRate':None})
                        recorded=self.ledger.create(signal)
                        if recorded:
                            with self.lock:self.best=[recorded]
                            found=True
                            break
                    except Exception:
                        with self.lock:self.missing5s+=1
                    finally:
                        with self.lock:
                            self.examined+=1;self.seen_at=time.time()
                        if self.stop_signal.wait(.3):break
                with self.lock:self.current=None
                if not found and self.stop_signal.wait(.8):break
        except Exception:
            with self.lock:self.error='Feed de velas 5S indisponível. Nenhum sinal fictício.'
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
