"""Focus Pocket V4.1: rotate ALL eligible assets, use M1 candle-color majority.

No fixed 100% prediction, no automatic orders, no signal on stale or absent data.
"""
import math
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from majority_candles import candle_majority

PAYOUT_MIN=87.0

def payout(value):
    if isinstance(value,bool):return None
    try:
        v=float(value)
        return v if math.isfinite(v) and 0<=v<=100 else None
    except (ValueError,TypeError,OverflowError):return None

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
        self.roundAnalyzed=0
        self.current=None
        self.error=None
        self.seen_at=0
        self.rejected=0
        self.feedErrors=0
        self.cursor=0
        self.ledger=SignalLedger(path="/tmp/focus-pocket-majority-m1-signals.sqlite3")
        self.best=self.ledger.restore_pending()

    def active(self):
        return bool(self.worker and self.worker.is_alive())

    def start(self):
        with self.lock:
            if self.active():return
            if self.stream_users:
                raise RuntimeError("Feche o monitor antes de iniciar o radar.")
            # Even without connection, the worker may wait and resume automatically.
            self.stop_signal=threading.Event()
            self.worker=threading.Thread(target=self.run,daemon=True,name="focus-majority-radar")
            self.worker.start()

    def stop(self):
        self.stop_signal.set()

    def status(self):
        now=time.time()
        with self.lock:
            status={'running':self.active() and not self.stop_signal.is_set(),
                    'stopping':self.active() and self.stop_signal.is_set(),
                    'minPayout':PAYOUT_MIN,'maxSignals':1,
                    'scanPeriod':'M1','confirmationPeriod':None,'signalExpirySeconds':60,
                    'eligible':self.eligible,'examined':self.examined,
                    'round':self.round,'roundAnalyzed':self.roundAnalyzed,
                    'rejected':self.rejected,'feedErrors':self.feedErrors,
                    'current':self.current,'error':self.error,
                    'lastUpdateMs':int(self.seen_at*1000),
                    'serverTimeMs':int(now*1000),
                    'candidates':[dict(c) for c in self.best
                        if c['endsAtMs']>now*1000][:1],
                    'mode':'majority-of-real-candle-colors-readonly',
                    'readOnly':True}
        status.update(self.ledger.status())
        return status

    def run(self):
        from signal_ledger import verify_outcome
        consecutive_errors=0
        try:
            while not self.stop_signal.is_set():
                if not self.broker.connected():
                    with self.lock:
                        self.error="Sem cotações reais: aguardando reconexão autenticada da Pocket Option DEMO."
                        self.current=None
                    # The underlying broker auto-reconnects; do not lose scanner state.
                    if self.stop_signal.wait(4):break
                    continue

                with self.lock:
                    pinned=self.best[0] if self.best else None
                    self.current=None
                if pinned:
                    expiry=pinned['endsAtMs']/1000.0
                    current=time.time()
                    if current<expiry+4:
                        if self.stop_signal.wait(min(1.3,max(.1,expiry+4-current))):break
                        continue
                    if current>expiry+240:
                        self.ledger.unverifiable(pinned['signalId'],
                            'Cotação real M1 de entrada/expiração indisponível na janela de apuração')
                        with self.lock:self.best=[]
                        continue
                    try:
                        prices=self.broker.candles(pinned['symbol'],60)
                        evidence=verify_outcome(pinned,prices,time.time())
                        if evidence and self.ledger.finish(pinned['signalId'],evidence):
                            with self.lock:self.best=[]
                            consecutive_errors=0
                            continue
                    except Exception:
                        with self.lock:self.feedErrors+=1
                    if self.stop_signal.wait(3):break
                    continue

                try:
                    symbols=self.broker.get_symbols()
                    eligible=sorted([a for a in symbols if a.get('open') is True and
                       a.get('payout') is not None and a['payout']>=PAYOUT_MIN],
                       key=lambda a:(-a['payout'],a['symbol']))
                    consecutive_errors=0
                except Exception:
                    with self.lock:
                        self.feedErrors+=1
                        self.error="Catálogo de ativos indisponível; nova tentativa automática."
                    if self.stop_signal.wait(8):break
                    continue

                n=len(eligible)
                with self.lock:
                    self.round+=1
                    self.eligible=n
                    self.roundAnalyzed=0
                    self.error=None if n else "Nenhum ativo aberto com payout confirmado >=87%."
                if not n:
                    if self.stop_signal.wait(10):break
                    continue

                # Rotate the beginning of each scan so every eligible asset is considered
                # across cycles, even when one good candidate is discovered early.
                start=self.cursor % n
                rotated=eligible[start:]+eligible[:start]
                found=False
                for i,asset in enumerate(rotated):
                    if self.stop_signal.is_set():break
                    if not self.broker.connected():break
                    with self.lock:
                        if self.best:break
                        self.current=asset['symbol']
                    try:
                        # Only one M1 history request per candidate. No M5/5S fan-out.
                        bars=self.broker.candles(asset['symbol'],60)
                        moment=time.time()
                        candidate=candle_majority(bars,now=moment)
                        if candidate is None:
                            with self.lock:self.rejected+=1
                            consecutive_errors=0
                            continue
                        # No stale signals and no backdated predictions.
                        current_boundary=math.floor(moment/60)*60
                        if candidate['timestamp']+60!=current_boundary:
                            continue
                        fresh=next((a for a in self.broker.get_symbols()
                            if a['symbol']==asset['symbol']),None)
                        if (not fresh or fresh['open'] is not True
                            or fresh.get('payout') is None or fresh['payout']<PAYOUT_MIN):
                            continue
                        checked=time.time()
                        entry=int((math.floor(checked/60)+1)*60000)
                        if entry-checked*1000<10000 or checked-(candidate['timestamp']+60)>46:
                            continue
                        candidate.update({
                            'symbol':asset['symbol'],'name':asset['name'],
                            'payout':fresh['payout'],'checkedAt':checked,
                            'entryAtMs':entry,'endsAtMs':entry+60000,
                            'verifiedM1':True,'verifiedMajority':True,
                            'verifiedLive':False,'qualityLabel':'PREDOMINÂNCIA, NÃO ASSERTIVIDADE',
                            'winRate':None
                        })
                        registered=self.ledger.create(candidate)
                        if registered:
                            with self.lock:self.best=[registered]
                            found=True
                            # Resume searching from the next eligible asset after completion.
                            self.cursor=(start+i+1)%n
                            break
                    except Exception:
                        consecutive_errors+=1
                        with self.lock:
                            self.feedErrors+=1
                            self.error="Histórico indisponível para um ou mais ativos."
                        if consecutive_errors>=4:
                            # Avoid hammering an already unstable WebSocket.
                            if self.stop_signal.wait(7):break
                            consecutive_errors=0
                    finally:
                        with self.lock:
                            self.examined+=1
                            self.roundAnalyzed+=1
                            self.seen_at=time.time()
                        if self.stop_signal.wait(.55):break
                with self.lock:self.current=None
                if not found and self.stop_signal.wait(2):break
        except Exception:
            with self.lock:self.error="Problema temporário no feed; sem criar sinais fictícios."
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
