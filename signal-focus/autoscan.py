"""Focus Pocket Strategy 2.0: EMA 9/21/200 + RSI + candle trigger + Bollinger filter; DEMO read-only.

Legacy scanner algorithms are removed; only focus_strategy.evaluate is executed.
"""
import math
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from focus_strategy import evaluate

PAYOUT_MIN=87

def payout(value):
    if isinstance(value,bool):return None
    try:
        n=float(value)
        return n if math.isfinite(n) and 0<=n<=100 else None
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
        self.current=None
        self.error=None
        self.last_tick=0
        self.rejected=0
        self.feed_errors=0
        self.cursor=0
        # New, empty ledger. Previous versions remain preserved only on the backup branch.
        self.ledger=SignalLedger(path='/tmp/focus-pocket-ema200-rsi-candle-20261111.sqlite3')
        self.best=self.ledger.restore_pending()

    def active(self):
        return bool(self.worker and self.worker.is_alive())

    def start(self):
        with self.lock:
            if self.active():return
            if self.stream_users:
                raise RuntimeError('Pause o gráfico antigo antes de iniciar a busca.')
            self.stop_signal=threading.Event()
            self.worker=threading.Thread(target=self.run,daemon=True,name='focus-reset-signal')
            self.worker.start()

    def stop(self):
        self.stop_signal.set()

    def status(self):
        now=time.time()
        with self.lock:
            info={'running':self.active() and not self.stop_signal.is_set(),
                  'stopping':self.active() and self.stop_signal.is_set(),
                  'version':'Focus Strategy 2.0',
                  'minPayout':PAYOUT_MIN,'maxSignals':1,
                  'scanPeriod':'M1','signalExpirySeconds':60,
                  'eligible':self.eligible,'examined':self.examined,'round':self.round,
                  'current':self.current,'error':self.error,
                  'feedErrors':self.feed_errors,'rejected':self.rejected,
                  'candidates':[dict(c) for c in self.best if c['endsAtMs']>now*1000][:1],
                  'lastUpdateMs':int(self.last_tick*1000),
                  'serverTimeMs':int(now*1000),
                  'mode':'ema9-21-200-rsi14-engulf-bollinger-m1-readonly',
                  'readOnly':True}
        info.update(self.ledger.status())
        return info

    def run(self):
        from signal_ledger import verify_outcome
        try:
            while not self.stop_signal.is_set():
                if not self.broker.connected():
                    with self.lock:
                        self.current=None
                        self.error='Pocket Option desconectada. Aguardando reconexão autenticada.'
                    if self.stop_signal.wait(5):break
                    continue

                with self.lock:
                    current=self.best[0] if self.best else None
                    self.current=None
                    self.error=None
                if current:
                    expires=current['endsAtMs']/1000
                    now=time.time()
                    if now<expires+5:
                        if self.stop_signal.wait(min(1.2,max(.1,expires+5-now))):break
                        continue
                    if now>expires+240:
                        self.ledger.unverifiable(current['signalId'],
                            'Sem velas reais do ativo no horário exato da operação')
                        with self.lock:self.best=[]
                        continue
                    try:
                        candles=self.broker.candles(current['symbol'],60)
                        evidence=verify_outcome(current,candles,time.time())
                        if evidence and self.ledger.finish(current['signalId'],evidence):
                            with self.lock:self.best=[]
                            continue
                    except Exception:
                        with self.lock:self.feed_errors+=1
                    if self.stop_signal.wait(3):break
                    continue

                try:
                    market=self.broker.get_symbols()
                    options=sorted([a for a in market if a.get('open') is True
                        and a.get('payout') is not None and a['payout']>=PAYOUT_MIN],
                        key=lambda a:(-a['payout'],a['symbol']))
                    with self.lock:
                        self.eligible=len(options)
                        self.round+=1
                        self.examined=0
                except Exception:
                    with self.lock:
                        self.feed_errors+=1
                        self.error='Falha ao consultar ativos; nova tentativa automática.'
                    if self.stop_signal.wait(8):break
                    continue

                if not options:
                    with self.lock:self.error='Nenhum ativo aberto com payout de 87% ou mais.'
                    if self.stop_signal.wait(10):break
                    continue

                n=len(options)
                start=self.cursor%n
                sequence=options[start:]+options[:start]
                emitted=False
                for idx,asset in enumerate(sequence):
                    if self.stop_signal.is_set() or not self.broker.connected():break
                    with self.lock:self.current=asset['symbol']
                    try:
                        candles=self.broker.candles(asset['symbol'],60)
                        t=time.time()
                        candidate=evaluate(candles,t)
                        if candidate is None:
                            with self.lock:self.rejected+=1
                            continue
                        # Re-check payout and actual asset availability before publishing.
                        latest=next((x for x in self.broker.get_symbols()
                                     if x['symbol']==asset['symbol']),None)
                        if not latest or latest.get('open') is not True or latest.get('payout') is None:
                            continue
                        if latest['payout']<PAYOUT_MIN:continue
                        clock=time.time()
                        next_minute=(int(clock//60)+1)*60
                        until=next_minute-clock
                        # At least 9 seconds notice; no late or retroactive entries.
                        if not 9<=until<=45:continue
                        # The last completed M1 candle must be recent, never two minutes old.
                        if clock-(candidate['timestamp']+60)>51:continue
                        candidate.update({'symbol':asset['symbol'],
                            'name':asset['name'],
                            'payout':latest['payout'],
                            'checkedAt':clock,
                            'entryAtMs':int(next_minute*1000),
                            'endsAtMs':int((next_minute+60)*1000),
                            'verifiedM1':True,
                            'signalTag':'EMA200_RSI14_CANDLE_V2',
                            'qualityLabel':'EMA9/21/200 + RSI14 + ENGOLFO/REJEIÇÃO + BOLLINGER — NÃO É CHANCE DE WIN'})
                        record=self.ledger.create(candidate)
                        if record:
                            with self.lock:self.best=[record]
                            self.cursor=(start+idx+1)%n
                            emitted=True
                            break
                    except Exception:
                        with self.lock:
                            self.feed_errors+=1
                            self.error='Parte do histórico está indisponível.'
                        if self.stop_signal.wait(2):break
                    finally:
                        with self.lock:
                            self.examined+=1
                            self.last_tick=time.time()
                        if self.stop_signal.wait(.35):break
                with self.lock:self.current=None
                if not emitted and self.stop_signal.wait(2.5):break
        except Exception:
            with self.lock:self.error='Falha no feed da corretora. Nenhum sinal simulado.'
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
