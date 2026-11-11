"""Focus Pocket V4: Heikin-Ashi M5 trend + M1 confirmation, ONE signal.

Neither Heikin price nor visual confidence is used for WIN/LOSS. Never auto-trades.
"""
import math
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from heikin_strategy import evaluate_heikin

PAYOUT_MIN=87.0

def payout(v):
    if isinstance(v,bool):return None
    try:
        x=float(v)
        return x if math.isfinite(x) and 0<=x<=100 else None
    except (ValueError,TypeError,OverflowError):
        return None

class Scanner:
    def __init__(self,broker):
        from signal_ledger import SignalLedger
        self.broker=broker
        self.lock=threading.RLock()
        self.stop_signal=threading.Event()
        self.worker=None
        self.stream_users=0
        self.eligible=0
        self.examined=0
        self.round=0
        self.current=None
        self.error=None
        self.seen_at=0
        self.rejected=0
        # Isolate the new Heikin-Ashi history from the old M1 and 5S variants.
        self.ledger=SignalLedger(path="/tmp/focus-pocket-heikin-m1-signals.sqlite3")
        self.best=self.ledger.restore_pending()

    def active(self):
        return bool(self.worker and self.worker.is_alive())

    def start(self):
        with self.lock:
            if self.active():return
            if self.stream_users:
                raise RuntimeError("Feche o monitor para iniciar a busca Heikin-Ashi.")
            if not self.broker.connected():
                raise RuntimeError("Conecte a sessão DEMO antes de iniciar.")
            self.stop_signal=threading.Event()
            self.worker=threading.Thread(target=self.run,daemon=True,name="focus-heikin-only")
            self.worker.start()

    def stop(self):
        self.stop_signal.set()

    def status(self):
        now=time.time()
        with self.lock:
            info={'running':self.active() and not self.stop_signal.is_set(),
                  'stopping':self.active() and self.stop_signal.is_set(),
                  'minPayout':PAYOUT_MIN,'maxSignals':1,
                  'scanPeriod':'M1','confirmationPeriod':'M5',
                  'signalExpirySeconds':60,
                  'eligible':self.eligible,'examined':self.examined,
                  'round':self.round,'current':self.current,
                  'rejected':self.rejected,
                  'candidates':[dict(c) for c in self.best if c['endsAtMs']>now*1000][:1],
                  'error':self.error,
                  'lastUpdateMs':int(self.seen_at*1000),
                  'serverTimeMs':int(now*1000),
                  'mode':'heikin-M5-M1-one-signal-experimental',
                  'readOnly':True}
        info.update(self.ledger.status())
        return info

    def run(self):
        from signal_ledger import verify_outcome
        try:
            while not self.stop_signal.is_set() and self.broker.connected():
                with self.lock:
                    pending=self.best[0] if self.best else None
                    self.current=None
                if pending:
                    expiry=pending['endsAtMs']/1000.0
                    now=time.time()
                    if now<expiry+4:
                        if self.stop_signal.wait(min(1.4,max(.2,expiry+4-now))):break
                        continue
                    if now>expiry+240:
                        self.ledger.unverifiable(pending['signalId'],
                            'Sem velas reais M1 verificáveis na entrada/vencimento')
                        with self.lock:self.best=[]
                        continue
                    try:
                        # Exact REAL standard M1 candle, never synthetic Heikin-Ashi.
                        prices=self.broker.candles(pending['symbol'],60)
                        evidence=verify_outcome(pending,prices,time.time())
                        if evidence and self.ledger.finish(pending['signalId'],evidence):
                            with self.lock:self.best=[]
                            continue
                    except Exception:
                        pass
                    if self.stop_signal.wait(3):break
                    continue

                assets=self.broker.get_symbols()
                eligible=sorted([a for a in assets if a['open'] is True
                                 and a.get('payout') is not None
                                 and a['payout']>=PAYOUT_MIN],
                                key=lambda a:(-a['payout'],a['symbol']))
                with self.lock:
                    self.round+=1
                    self.eligible=len(eligible)
                    self.error=None
                if not eligible:
                    with self.lock:
                        self.error='Nenhum ativo aberto com payout real de 87% ou mais.'
                    if self.stop_signal.wait(10):break
                    continue
                found=False
                for asset in eligible:
                    if self.stop_signal.is_set() or not self.broker.connected():break
                    with self.lock:
                        if self.best:break
                        self.current=asset['symbol']
                    try:
                        bars_m1=self.broker.candles(asset['symbol'],60)
                        bars_m5=self.broker.candles(asset['symbol'],300)
                        moment=time.time()
                        candidate=evaluate_heikin(bars_m1,bars_m5,now=moment)
                        if candidate is None:
                            with self.lock:self.rejected+=1
                            continue
                        # The M1 reading must be from the very last completed minute.
                        completed_minute=math.floor(moment/60)*60
                        if candidate['timestamp']+60!=completed_minute:
                            continue
                        fresh=next((a for a in self.broker.get_symbols()
                                    if a['symbol']==asset['symbol']),None)
                        if not fresh or fresh['open'] is not True or fresh.get('payout') is None:
                            continue
                        if fresh['payout']<PAYOUT_MIN:continue
                        checked=time.time()
                        entry=int((math.floor(checked/60)+1)*60000)
                        # No late signals; allow the person to prepare for the next M1.
                        if entry-checked*1000<10000:continue
                        if checked-(candidate['timestamp']+60)>43:continue
                        candidate.update({'symbol':asset['symbol'],'name':asset['name'],
                                          'payout':fresh['payout'],
                                          'checkedAt':checked,
                                          'entryAtMs':entry,
                                          'endsAtMs':entry+60000,
                                          'verifiedM1':True,'verifiedHA':True,
                                          'verifiedLive':False,
                                          'qualityLabel':'10 CRITÉRIOS TÉCNICOS (NÃO É WIN%)',
                                          'winRate':None})
                        registered=self.ledger.create(candidate)
                        if registered:
                            with self.lock:self.best=[registered]
                            found=True
                            break
                    except Exception:
                        with self.lock:self.rejected+=1
                    finally:
                        with self.lock:
                            self.examined+=1
                            self.seen_at=time.time()
                        if self.stop_signal.wait(.3):break
                with self.lock:self.current=None
                if not found and self.stop_signal.wait(.8):break
        except Exception:
            with self.lock:self.error='Feed insuficiente. Sem sinais inventados.'
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
