"""Original demo-only Socket.IO adapter. Protocol references in README.md."""
import json, math, ssl, threading, time, uuid
from collections import deque
import websocket
from m1_strategy import MinuteSignals, five_minute_closes
from tick_exhaustion import TickExhaustion,EXHAUSTION_EXPIRIES
from market_radar import Radar
from zigzag_trendline import ZigZagFractalTrend
from zigzag_5s import ZigZagFractalTrend5s
from zigzag_m2 import ZigZagFractalTrendM2
from price_action_zones import PriceActionZones5s
from triangle_breakout import TriangleBreakout
from triangle_validation import walkforward
from technical_strategies import TechnicalStrategy, PROFILES, EXPIRIES

DEMO_URLS = ('wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket', 'wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket')

def parse_auth(raw):
    try:
        packet = json.loads(raw[2:] if raw.startswith('42') else raw)
        if not isinstance(packet,list) or len(packet)!=2 or packet[0]!='auth': raise ValueError()
        p=packet[1]
        if type(p.get('isDemo')) is not int or p['isDemo']!=1: raise ValueError()
        if not isinstance(p.get('session'),str) or not 10<=len(p['session'])<=16000: raise ValueError()
        if type(p.get('uid')) is not int or p['uid']<=0: raise ValueError()
        return {'session':p['session'],'isDemo':1,'uid':p['uid'],'platform':2,'isFastHistory':True,'isOptimized':True}
    except (ValueError,TypeError,KeyError,AttributeError):
        raise ValueError('Cole a mensagem auth completa de uma conta DEMO (isDemo: 1).') from None

def signal(ticks):
    """New 3s/8s crossover, based on *distinct seconds* of broker quotes.

    No late signal is returned after the first crossover second. A stream of
    old prices or irregularly-spaced seconds is not enough evidence.
    This is an unvalidated experimental indicator, not a win-rate promise.
    """
    buckets={int(t):p for t,p in ticks if isinstance(t,(int,float)) and isinstance(p,(int,float))
             and math.isfinite(t) and math.isfinite(p) and p>0}
    a=sorted(buckets.items())[-10:]
    if len(a)<10 or a[-1][0]-a[0][0]>11:return None
    if max(a[i+1][0]-a[i][0] for i in range(9))>2:return None
    v=[p for _,p in a]
    previous=sum(v[-4:-1])/3-sum(v[-9:-1])/8
    current=sum(v[-3:])/3-sum(v[-8:])/8
    # Avoid false nonzero baselines from floating-point roundoff on flat data.
    epsilon=max(abs(v[-1]),1e-8)*1e-10
    if previous<=epsilon and current>epsilon and v[-1]>v[-2]:return 'call'
    if previous>=-epsilon and current<-epsilon and v[-1]<v[-2]:return 'put'
    return None

def continuation_signal(ticks):
    """Recheck confirmed short-term momentum for recurring DEMO opportunities.

    Distinct recent one-second bars, positive MA separation and two successive
    changes in the same direction are required. Never treat a flat or broken
    stream as a continuation signal. Experimental; not a profit prediction.
    """
    buckets={int(t):p for t,p in ticks if isinstance(t,(int,float))
             and isinstance(p,(int,float)) and math.isfinite(t)
             and math.isfinite(p) and p>0}
    a=sorted(buckets.items())[-10:]
    if len(a)<10 or a[-1][0]-a[0][0]>11:return None
    if max(a[i+1][0]-a[i][0] for i in range(9))>2:return None
    v=[p for _,p in a]
    fast=sum(v[-3:])/3
    slow=sum(v[-8:])/8
    separation=max(abs(v[-1])*1e-7,(max(v)-min(v))*0.05)
    if fast-slow>separation and v[-1]>v[-2]>v[-3]:return 'call'
    if slow-fast>separation and v[-1]<v[-2]<v[-3]:return 'put'
    return None

AUTO_INTERVAL_SECONDS=15
PAUSE_CHOICES=(5,10,15,20,30)
# These are application-tested integer candidates, NOT a promise the upstream
# broker accepts every requested duration for a given instrument/account.
# 1h/4h are intentionally disabled: this in-memory DEMO runner cannot safely
# reconcile a trade lasting beyond its bounded 60-minute session.
FAST_EXPIRIES=tuple(range(3,11))+(15,20,30,45)
LONG_EXPIRIES=(60,90,120,180,300,600,900,1800)
ALL_EXPIRIES=FAST_EXPIRIES+LONG_EXPIRIES
MANUAL_SIGNAL_TTL=2.5
M1_FEED_STOP_SECONDS=180
AUTO_MAX_SESSION_SECONDS=3600

def not_lateral(ticks,direction):
    """Minimal trend-efficiency check, without altering the signal strategy.

    Repeated direction changes and weak net travel are signs of congestion.
    Uses only observed 1-second quote samples; insufficient samples block
    automatic entries when the optional filter is on.
    """
    seconds={int(t):p for t,p in ticks if isinstance(t,(int,float)) and isinstance(p,(int,float))
             and math.isfinite(t) and math.isfinite(p) and p>0}
    a=sorted(seconds.items())[-10:]
    if len(a)<10 or a[-1][0]-a[0][0]>12:return False
    v=[p for _,p in a]
    changes=[v[i]-v[i-1] for i in range(1,len(v))]
    travel=sum(abs(z) for z in changes)
    if travel<=max(v[-1]*1e-8,1e-10):return False
    net=v[-1]-v[0]
    if direction=='call' and net<=0:return False
    if direction=='put' and net>=0:return False
    efficiency=abs(net)/travel
    reversals=sum(1 for x,y in zip(changes,changes[1:]) if x*y<0)
    return efficiency>=0.55 and reversals<=3


def parse_expiry(value):
    if type(value) is not int or value not in ALL_EXPIRIES:
        raise ValueError('Expiração indisponível neste motor. Escolha uma das durações demonstrativas até 30 minutos.')
    return value

def verified_five_second_duration(start,end):
    """Validate *observed* broker open/close timestamps, not requested expiry.

    Normalizes epoch seconds or epoch milliseconds. Does not infer a completed
    duration from the order request or local network receipt timing.
    """
    if isinstance(start,bool) or isinstance(end,bool):return None
    try:
        a=float(start);b=float(end)
        if not math.isfinite(a) or not math.isfinite(b) or b<=a:return None
        seconds=(b-a)/1000 if a>1e11 and b>1e11 else b-a
        return round(seconds,3) if 0<seconds<=86400 else None
    except (ValueError,TypeError,OverflowError):return None

class Broker:
    def __init__(self,auth,persist=lambda row:None):
        self.auth=auth; self.persist=persist; self.lock=threading.RLock(); self.ws=None
        self.connected=False; self.connecting=False; self.demo_confirmed=False; self.balance=None
        self.connection_state='desconectado';self.connection_failure='';self.connection_attempt=0
        self.assets={}; self.symbol=''; self.ticks=deque(maxlen=600); self.received=0; self.price_time=0; self.quote_samples=deque(maxlen=80)
        self.message='Desconectado'; self.pending=None; self.history=[]; self.events=deque(maxlen=100)
        self.auto=False; self.auto_trial=False; self.auto_started_at=0; self.validated=False; self.validated_expiries=set(); self.auto_expiry=5
        self.validation_message='Valide a expiração desejada com uma operação manual DEMO concluída.'
        self.last_signal=None;self.last_signal_kind=None;self.last_signal_at=0;self.last_signal_bucket=None
        self.last_order=0; self.closed=False; self.binary=None
        self.last_seen=time.time(); self.limit=10; self.stop_win=20.; self.stop_loss=20.; self.amount=1.; self.min_payout=80.; self.baseline=0; self.count=0
        self.keepalive_stop=threading.Event()
        self.last_app_ping=0
        self.auto_stop_reason='Automático não iniciado.'
        self.feed_lag_warning=False
        self.pause_after=20
        self.last_closed_at=0
        self.gale_enabled=False
        self.gale_pending=None
        self.gale_status='Martingale desligado'
        self.lateral_filter=True
        self.market_quality='Aguardando leitura'
        self.minute_engine=MinuteSignals()
        self.exhaustion={3:TickExhaustion(3),5:TickExhaustion(5)}
        self.fast_strategy='trend'  # backward compatibility for existing runs
        self.auto_strategy='standard'
        self.technical_profile=''
        self.technical_observe=False
        self.zone_mode=False
        self.triangle_mode=False
        self.triangle_observe=True
        self.triangle_trial_only=False
        self.triangle_sensitivity='strict'
        self.triangle_reports={}
        self.triangle_observations=deque(maxlen=150)
        self.triangle_last_report=0
        self.scan_timeframe=60
        self.radar=Radar(ZigZagFractalTrend)
        self.scan_queue=deque()
        self.scan_last_subscribe=0
        self.scan_signals=0
        self.scan_last_verified_at=0
        self.history_queue=deque()
        self.history_requests={}
        self.history_requested=set()
        self.history_last_request=0
        self.history_loaded_count=0
        self.history_unmatched=0
        self.recent_closed_deals=deque(maxlen=30)
    def log(self,text):
        self.message=text; self.events.append({'time':time.time(),'text':text})
    def start(self):
        self.connecting=True
        self.connection_state='conectando';self.connection_failure=''
        threading.Thread(target=self.run,daemon=True).start()
        threading.Thread(target=self.keepalive_loop,daemon=True).start()
    def send_keepalive(self):
        # Distinct from Socket.IO Engine.IO ping/pong and WebSocket transport ping.
        # Only authenticated DEMO connections get the documented 'ps' heartbeat.
        with self.lock:
            if self.closed or not self.connected or not self.demo_confirmed or not self.ws:
                return False
            try:
                self.send('ps')
                self.last_app_ping=time.time()
                return True
            except Exception:
                if self.auto:self.auto_stop_reason='Falha no heartbeat DEMO. Conexão não confiável; reinicie manualmente.'
                self.auto=False
                self.log('Falha ao manter conexão DEMO. Confira o estado antes de operar.')
                return False
    def keepalive_loop(self):
        while not self.keepalive_stop.wait(20):
            if self.closed: return
            self.send_keepalive()
            with self.lock:self.subscribe_scan_batch()
    def send(self,event,data=None):
        if not self.ws: raise ValueError('Conexão indisponível.')
        self.ws.send('42'+json.dumps([event] if data is None else [event,data],separators=(',',':')))
    def run(self):
        # Retry the transport at most twice per endpoint. No order replay.
        for attempt, url in enumerate(DEMO_URLS * 2,1):
            if self.closed or self.pending:break
            self.connection_attempt=attempt
            self.connection_state='conectando'
            self.connecting=True
            self.binary=None; self.demo_confirmed=False; self.validated=False; self.validated_expiries.clear()
            self.last_signal=None;self.last_signal_at=0;self.last_signal_bucket=None
            self.validation_message='Nova conexão DEMO: valide manualmente a expiração desejada.'; self.received=0; self.price_time=0; self.ticks.clear(); self.quote_samples.clear(); self.minute_engine=MinuteSignals(); self.exhaustion={3:TickExhaustion(3),5:TickExhaustion(5)}
            self.radar=Radar(ZigZagFractalTrend);self.scan_queue.clear()
            self.history_queue.clear();self.history_requests.clear();self.history_requested.clear()
            self.log('Conectando à Pocket Option DEMO · tentativa %d/4…'%attempt)
            self.ws=websocket.WebSocketApp(url,on_message=self.on_message,
                                            on_error=self.on_error,on_close=self.on_close)
            socket=self.ws
            watchdog=threading.Timer(25,lambda:socket.close()
                if not (self.connected and self.demo_confirmed) and not self.closed else None)
            watchdog.daemon=True;watchdog.start()
            try:
                socket.run_forever(origin='https://pocketoption.com',
                    sslopt={'cert_reqs':ssl.CERT_REQUIRED,'check_hostname':True},
                    ping_interval=20,ping_timeout=10)
            except Exception:
                # Never log credentials or raw upstream exceptions.
                self.connection_state='falha_rede'
                self.connection_failure='Conexão WebSocket interrompida no servidor.'
            finally:watchdog.cancel()
            if self.closed or self.pending:break
            if not self.connection_failure:
                self.connection_failure='A conexão DEMO terminou sem confirmação da corretora.'
            if attempt<4:time.sleep(1.0)
        self.connecting=False;self.connected=False;self.demo_confirmed=False;self.auto=False
        if not self.closed:
            self.connection_state='desconectado'
            self.log((self.connection_failure or 'Conexão DEMO encerrada.')+
                ' Tentativas encerradas; toque CONECTAR POCKET DEMO novamente. Nenhuma ordem foi repetida.')
        self.keepalive_stop.set()
    def on_error(self,ws,error):
        # Classify errors without disclosing URL payloads, cookies or tokens.
        label=str(error).lower()
        if '429' in label:reason='A corretora limitou novas conexões (429).'
        elif '403' in label or '401' in label:reason='Servidor da corretora recusou HTTP 401/403.'
        elif 'timed out' in label or 'timeout' in label:reason='Tempo esgotado ao alcançar a corretora.'
        elif 'ssl' in label or 'certificate' in label:reason='Falha TLS/certificado de conexão.'
        elif 'getaddrinfo' in label or 'name or service not known' in label:
            reason='DNS do servidor não resolveu o endereço da corretora.'
        else:reason='Falha de comunicação WebSocket com a corretora.'
        self.connection_state='falha_rede'
        self.connection_failure=reason
        self.log(reason)
    def on_close(self,ws,*args):
        with self.lock:
            if self.auto:self.auto_stop_reason='Conexão DEMO encerrada. Reconecte para reativar o automático.'
            self.connected=False; self.auto=False; self.demo_confirmed=False; self.validated=False; self.validated_expiries.clear()
            if not self.closed and not self.connection_failure:
                self.connection_failure='Conexão Pocket Option DEMO encerrada antes da confirmação.'
            self.last_signal=None;self.last_signal_at=0
            self.validation_message='Sessão encerrada: reconecte e valide manualmente a expiração escolhida.'
            if self.pending:self.log('Conexão perdida com ordem pendente. Verifique o resultado na corretora antes de reconectar.')
    def on_message(self,ws,message):
        try:
            with self.lock:
                if isinstance(message,bytes):
                    if self.binary:
                        name=self.binary; self.binary=None; self.event(name,json.loads(message.decode()))
                elif message.startswith('0'):
                    ws.send('40')
                elif message=='2':ws.send('3')
                elif message.startswith('40'):
                    self.send('auth',self.auth)
                elif message=='41':
                    # '41' denotes a Socket.IO namespace disconnect, not proof
                    # by itself that the broker explicitly rejected credentials.
                    self.closed=True;self.connected=False;self.demo_confirmed=False
                    self.auto=False;self.validated=False;self.validated_expiries.clear();self.keepalive_stop.set()
                    self.auto_stop_reason='Conexão DEMO encerrada pela corretora (41).'
                    self.connection_state='encerrada_corretora'
                    self.connection_failure='A corretora encerrou a sessão (41). Gere nova sessão DEMO.'
                    self.log('A Pocket Option encerrou a conexão (código 41). Motivo não informado. Reconecte à conta DEMO.')
                    ws.close()
                elif message.startswith('451-'):
                    p=json.loads(message.split('-',1)[1]);self.binary=p[0]
                elif message.startswith('42'):
                    p=json.loads(message[2:]);self.event(p[0],p[1] if len(p)>1 else {})
        except (ValueError,KeyError,TypeError,IndexError):
            if self.auto:self.auto_stop_reason='Mensagem da corretora não reconhecida; automático pausado por segurança.'
            self.auto=False; self.log('Mensagem da corretora não reconhecida. Automático pausado.')
    def event(self,name,d):
        if name=='successauth':
            self.connected=True;self.connecting=False;self.connection_state='autenticada';self.connection_failure='';self.log('Autenticado. Aguardando confirmação do saldo demo e catálogo.');self.send('indicator/load');self.send('favorite/load')
        elif name=='successupdateBalance' and isinstance(d,dict):
            previously_demo=self.demo_confirmed
            if 'isDemo' in d:
                self.demo_confirmed=d['isDemo'] in (1,True)
                if not self.demo_confirmed:self.auto=False;self.close();return
            b=d.get('balance')
            if isinstance(b,(int,float)) and math.isfinite(b):self.balance=b
            if self.demo_confirmed:
                self.connection_state='demo_confirmada';self.connection_failure=''
            if self.demo_confirmed and not previously_demo:self.log('Conta demo confirmada. Selecione um ativo para receber preços.')
        elif name=='updateAssets' and isinstance(d,list):
            self.assets={r[1]:{'symbol':r[1],'name':str(r[2]),'payout':float(r[5]),'available':bool(r[14])} for r in d if isinstance(r,list) and len(r)>14 and isinstance(r[1],str) and isinstance(r[5],(int,float))}
            if self.auto and self.auto_strategy=='zigzag_fractal':
                for sym in self.radar.sync(self.assets,self.min_payout):
                    if sym not in self.scan_queue:self.scan_queue.append(sym)
                    if sym not in self.history_queue:self.history_queue.append(sym)
        elif name=='updateHistoryNewFast' and isinstance(d,dict):
            # Historical broker ticks only, cannot generate old orders.
            sym=d.get('asset')
            rows=d.get('history')
            if (self.auto and self.auto_strategy=='zigzag_fractal' and
                isinstance(sym,str) and isinstance(rows,list) and len(rows)<=50000):
                if self.radar.load_history(sym,rows,'updateHistoryNewFast'):
                    self.history_loaded_count+=1
        elif name=='loadHistoryPeriodFast' and isinstance(d,dict):
            # Unlabelled/mismatched responses are never attributed to an asset.
            idx=d.get('index')
            sym=d.get('asset')
            if isinstance(idx,(int,str)) and str(idx).isdigit():
                requested=self.history_requests.pop(int(idx),None)
                if requested and (sym is None or sym==requested[0]):sym=requested[0]
                else:sym=None
            elif isinstance(sym,str) and sym in self.history_requested:
                pass
            else:sym=None
            rows=d.get('data')
            if (self.auto and self.auto_strategy=='zigzag_fractal' and
                isinstance(sym,str) and isinstance(rows,list) and len(rows)<=50000):
                if self.radar.load_history(sym,rows,'loadHistoryPeriodFast'):
                    self.history_loaded_count+=1
            else:self.history_unmatched+=1
        elif name=='updateStream' and isinstance(d,list):
            m1_direction=None
            exhaustion_direction=None
            scan_candidates=[]
            for r in d:
                if (self.auto and self.auto_strategy=='zigzag_fractal' and
                    isinstance(r,list) and len(r)>=3 and isinstance(r[0],str)):
                    try:
                        stamp=float(r[1]);price=float(r[2])
                        seen=self.radar.ingest(r[0],stamp,price,time.time())
                        watch=self.radar.watches.get(r[0])
                        if watch and watch.fresh(time.time()):
                            self.scan_last_verified_at=time.time()
                        if seen in ('put','call'):scan_candidates.append(r[0])
                    except (ValueError,TypeError,OverflowError):
                        pass
                if isinstance(r,list) and len(r)>=3 and r[0]==self.symbol:
                    t,p=float(r[1]),float(r[2]);t=t/1000 if t>1e12 else t
                    if math.isfinite(t) and math.isfinite(p) and p>0 and t>self.price_time:
                        self.ticks.append((t,p));self.received=time.time();self.price_time=t;self.quote_samples.append((t,self.received))
                        # The M1/M5 engine only sees real, ascending broker
                        # quotes; it never backfills missing candles.
                        qualified=self.minute_engine.ingest(t,p,self.received)
                        if qualified: m1_direction=qualified
                        # Preserve sub-second quote timestamps and tick counts,
                        # rather than collapsing them to one quote per second.
                        for duration,engine in self.exhaustion.items():
                            seen=engine.ingest(t,p,self.received)
                            if (self.auto and self.fast_strategy=='exhaustion' and
                                self.auto_expiry==duration and seen):
                                exhaustion_direction=seen
            # Reevaluate the signal on each new second, not just the first
            # crossover. This permits subsequent entries after the cooldown,
            # but only when the source feed shows current trend evidence.
            bucket=int(self.price_time) if self.price_time else None
            direction=None
            if bucket is not None and bucket!=self.last_signal_bucket and self.fresh_quote():
                self.last_signal_bucket=bucket
                crossed=signal(self.ticks)
                direction=crossed or continuation_signal(self.ticks)
                if direction:
                    self.last_signal=direction
                    self.last_signal_kind='cross' if crossed else 'trend'
                    self.last_signal_at=time.time()
            if self.auto:
                if self.auto_expiry in LONG_EXPIRIES:
                    direction=m1_direction
                elif self.auto_expiry in EXHAUSTION_EXPIRIES and self.fast_strategy=='exhaustion':
                    direction=exhaustion_direction
                pnl=sum(x.get('net',0) for x in self.history)-self.baseline
                if self.count>=self.limit or pnl>=self.stop_win or pnl<=-self.stop_loss:
                    self.auto=False;self.auto_trial=False
                    self.auto_stop_reason=('Limite de %d operações atingido.'%self.limit if self.count>=self.limit else
                                           'Stop Win atingido.' if pnl>=self.stop_win else 'Stop Loss atingido.')
                    self.log('Automático encerrado: '+self.auto_stop_reason)
                elif self.auto_strategy=='zigzag_fractal':
                    # A confirmed LOSS can schedule exactly one same-direction
                    # DEMO attempt at the NEXT candle's opening tick. While
                    # armed, no other original ZigZag signal may get ahead.
                    gale_wait=self._try_gale_next_candle()
                    if not gale_wait and not self.pending:self.try_scan_order(scan_candidates)
                elif direction and not self.pending:
                    # Same server-validated signal offered to the manual button;
                    # never act on a stale quote, sideways market or expired
                    # cooldown. No UI/client-side BUY/SELL direction is trusted.
                    offer=self.signal_status(allow_auto=True,expiry=self.auto_expiry)
                    self.market_quality=offer['reason']
                    if offer['ready'] and offer['direction']==direction:
                        try:self.order(direction,1.0 if self.auto_trial else self.amount,self.auto_expiry)
                        except ValueError as e:
                            self.auto=False;self.auto_trial=False
                            self.auto_stop_reason='Entrada automática bloqueada: '+str(e)
                            self.log(self.auto_stop_reason)
        elif name=='successopenOrder' and isinstance(d,dict) and self.pending:
            if str(d.get('requestId'))!=self.pending['requestId']:return
            bid=d.get('id')
            if bid is None or str(bid)=='':
                self.log('Abertura DEMO confirmada sem identificador. Aguardando corretora.')
                return
            self.pending['broker_order_id']=str(bid)
            self.pending['status']='ABERTA';self.pending['opened']=d
            self.log('Ordem demo aceita. Aguardando resultado oficial.');self.save(self.pending)
            # Close event may precede opening ACK for 3s options. Buffer
            # until ACK proves exact requestId => broker order ID.
            for closed in list(self.recent_closed_deals):
                if str(closed.get('id',''))==str(bid):
                    self._settle_pending_from_official_deal(closed)
                    break
        elif name in ('successcloseOrder','updateClosedDeals'):
            deals=d.get('deals',d.get('data',d.get('closedDeals'))) if isinstance(d,dict) else d
            if isinstance(deals,dict):
                deals=deals.get('deals',deals.get('closedDeals',deals))
            if isinstance(deals,dict) and deals.get('id') is not None:deals=[deals]
            if not isinstance(deals,list) and isinstance(d,dict) and d.get('id') is not None:deals=[d]
            if not isinstance(deals,list):return
            for deal in deals[:500]:
                if not isinstance(deal,dict) or deal.get('id') is None:continue
                bid=str(deal['id'])
                if self.pending and str(self.pending.get('broker_order_id') or '')==bid:
                    self._settle_pending_from_official_deal(deal)
                    break
                elif self.pending and not self.pending.get('broker_order_id') and self.pending.get('requestId'):
                    self.recent_closed_deals.append(deal)
        elif name=='failopenOrder' and isinstance(d,dict) and self.pending:
            # Official rejection with the SAME requestId proves no deal
            # opened; discard only this exact rejected request. No replay.
            if str(d.get('requestId',''))!=str(self.pending.get('requestId')):return
            p=self.pending;p['status']='REJEITADA'
            p['result']={'reason':'A corretora confirmou rejeição da abertura da ordem DEMO.'}
            self.history.append(p);self.history=self.history[-300:]
            self.pending=None;self.last_closed_at=time.time();self.auto=False;self.auto_trial=False
            self.auto_stop_reason='A corretora rejeitou a ordem DEMO. Revise a configuração.'
            self.save(p)
            self.log('Ordem DEMO rejeitada oficialmente e pendência liberada automaticamente. Nenhum reenvio.')
        elif name.lower()=='notauthorized':
            self.connection_state='autenticacao_recusada'
            self.connection_failure='Sessão DEMO recusada. Gere nova autenticação no navegador.'
            self.auto=False;self.validated=False
            self.log('Autenticação DEMO recusada pela corretora. Gere uma nova sessão no navegador interno.')
            self.close()
        elif 'error' in name.lower():
            if self.auto:
                self.auto_stop_reason=('Corretora retornou erro no perfil %ds. Confira se o ativo oferece esta expiração; '
                                       'não repetiremos a ordem sem verificar o histórico.'%self.auto_expiry)
            self.auto=False
            self.log('A corretora recusou uma solicitação. Confira ativo, valor, vencimento e ordens abertas.')
    def _settle_pending_from_official_deal(self,deal):
        """Only an official matched broker ID can close a DEMO pending order."""
        if not isinstance(deal,dict) or not self.pending:return False
        bid=self.pending.get('broker_order_id')
        if not bid or str(deal.get('id',''))!=str(bid):return False
        p=self.pending; profit=deal.get('profit')
        if not isinstance(profit,(int,float)) or not math.isfinite(profit):
            self.auto=False;self.log('Resultado recebido sem lucro reconhecível. Confira na corretora.');return
        op=deal.get('openPrice',p.get('opened',{}).get('openPrice')); cp=deal.get('closePrice')
        if not isinstance(op,(int,float)) or not isinstance(cp,(int,float)) or not math.isfinite(op) or not math.isfinite(cp):
            self.auto=False;self.log('Fechamento recebido sem preços reconhecíveis. Confira o resultado na corretora.');return
        diff=(cp-op)*(1 if p['direction']=='call' else -1)
        expected=p['amount']*p['payout']/100
        if diff>0:
            if abs(profit-expected)<0.02: net=profit
            elif abs(profit-p['amount']-expected)<0.02: net=profit-p['amount']
            else:
                self.auto=False;self.log('Lucro retornado não corresponde ao payout. Confira o resultado na corretora.');return
        elif diff<0:
            if abs(profit)<0.02 or abs(profit+p['amount'])<0.02:net=-p['amount']
            else:
                self.auto=False;self.log('Resultado divergente. Confira a ordem na corretora.');return
        else:
            if abs(profit)<0.02 or abs(profit-p['amount'])<0.02:net=0
            else:
                self.auto=False;self.log('Empate com retorno divergente. Confira a corretora.');return
        p['net']=float(net);p['status']='WIN' if net>0 else 'LOSS' if net<0 else 'EMPATE'
        p['result']={'profit':profit,'net':net,'openPrice':op,'closePrice':cp}
        opened=p.get('opened',{})
        start=deal.get('openTime',opened.get('openTime')); end=deal.get('closeTime',opened.get('closeTime'))
        duration=verified_five_second_duration(start,end)
        requested=p.get('expiry',5)
        if duration is not None and abs(duration-requested)<=0.5:
            self.validated_expiries.add(requested)
            self.validated=True
            if self.auto and self.auto_trial and requested==self.auto_expiry:
                self.auto_trial=False
                self.log('Teste automático DEMO de %ds confirmado pela corretora. Motor seguirá operando somente novos sinais.'%requested)
            self.validation_message=('Expiração de %ds confirmada pela corretora. '
                                     'Automático DEMO disponível para esta duração.'%requested)
        elif duration is None:
            # The broker acknowledged this exact order ID and
            # delivered a reconciled official close event (prices
            # and payout-consistent result). That proves closure,
            # but NOT the actual expiry duration. Keep an already
            # running DEMO-only auto in a restricted value-1 mode;
            # do not mark this expiry as validated or raise stakes.
            self.validated=bool(self.validated_expiries)
            self.validation_message=('Resultado oficial da ordem DEMO de %ds confirmado, '
                                     'mas a corretora não informou horários suficientes. '
                                     'Expiração NÃO verificada; entradas seguintes limitadas a valor 1.'%requested)
            if self.auto and requested==self.auto_expiry:
                self.auto_trial=True
                self.log('Fechamento oficial confirmado sem horários completos. '
                         'Automático DEMO continua com valor 1, expiração não verificada e intervalo mínimo de 15s.')
        else:
            # An explicitly mismatched broker duration is positive
            # contrary evidence: stop, rather than guess.
            self.auto=False;self.auto_trial=False
            self.auto_stop_reason='Duração oficial %.2fs não coincide com %ds.'%(duration,requested)
            self.validated=bool(self.validated_expiries)
            self.validation_message=('Duração %.2fs diferente dos %ds pedidos. '
                                     'Automático bloqueado para esta duração.'%(duration,requested))
        self.history.append(p);self.history=self.history[-300:];self.pending=None;self.last_closed_at=time.time();self.save(p);self.log('Resultado confirmado: '+p['status'])
        self._arm_gale_after_loss(p)
        self.recent_closed_deals.clear()
        return True
    def save(self,p):
        # Persist only allowlisted non-sensitive fields.
        row={k:p.get(k) for k in ('id','asset','direction','amount','broker_order_id','status','strategy','expiry','gale_level')};row['result']=p.get('result',{})
        self.persist(row)
    def fresh_quote(self):
        """Fail closed if the feed is stale, even if broker and server clocks differ.

        When the upstream timestamp has a stable clock offset, prove that source
        times advance at a credible rate over multiple separate arrivals.
        A bulk replay with identical receipt times cannot satisfy this check.
        """
        now=time.time()
        if not self.ticks or not self.received or not self.price_time:
            return False
        if not 0<=now-self.received<=2.0:
            return False
        if abs(now-self.price_time)<=3.0:
            return True
        if abs(now-self.price_time)>12*3600:
            return False
        for source,arrival in reversed(self.quote_samples):
            elapsed=self.received-arrival
            advanced=self.price_time-source
            if 0.8<=elapsed<=5.0 and 0.25<=advanced<=elapsed+3:
                return True
        return False

    def subscribe_scan_batch(self,now=None,force=False):
        """Request one OTC feed at a time; never claim subscription equals live data."""
        now=time.time() if now is None else now
        if not self.auto or self.auto_strategy!='zigzag_fractal' or not self.connected:
            return
        if not force and now-self.scan_last_subscribe<1.0:return
        while self.scan_queue:
            symbol=self.scan_queue.popleft()
            if symbol not in self.radar.eligible or symbol in self.radar.subscribed:continue
            try:
                # subscribeSymbol requests price ticks; subfor alone is a
                # sentiment subscription on newer Pocket Option clients.
                self.send('subscribeSymbol',symbol)
                self.send('changeSymbol',{'asset':symbol,'period':self.scan_timeframe})
            except Exception:
                self.auto=False;self.auto_trial=False
                self.auto_stop_reason='Falha ao solicitar feed de varredura OTC; reconecte manualmente.'
                self.log(self.auto_stop_reason)
                return
            self.radar.subscribed.add(symbol)
            self.scan_last_subscribe=now
            return

    def request_history_batch(self,now=None):
        """Request one historical feed every 2s; use only verified live clocks.

        Broker-native read-only loadHistoryPeriod; never invent candles.
        Strict asset/index association blocks cross-asset history leakage.
        """
        now=time.time() if now is None else now
        if not self.auto or self.auto_strategy!='zigzag_fractal' or not self.connected:
            return
        if now-self.history_last_request<2:return
        for idx,(sym,sent) in list(self.history_requests.items()):
            if now-sent>20:self.history_requests.pop(idx,None)
        n=len(self.history_queue)
        for _ in range(n):
            sym=self.history_queue.popleft()
            watch=self.radar.watches.get(sym)
            if sym in self.history_requested or sym not in self.radar.eligible:
                continue
            if not watch or not watch.fresh(now):
                self.history_queue.append(sym)
                continue
            idx=int(now*1000)+len(self.history_requested)
            period=self.scan_timeframe
            anchor=int(watch.price_time)
            try:
                self.send('loadHistoryPeriod',{'asset':sym,'index':idx,
                    'offset':min(172800,period*500) if (self.triangle_mode or self.technical_profile) else 9000,'period':period,
                    'time':anchor if period==5 else anchor//period*period})
            except Exception:
                self.log('Histórico não disponível; estratégia seguirá somente candles reais novos.')
                return
            self.history_requested.add(sym)
            self.history_requests[idx]=(sym,now)
            self.history_last_request=now
            return

    def _arm_gale_after_loss(self,p):
        """Schedule ONE optional x2 DEMO follow-up, only after official LOSS.

        No addition to ZigZag rules; Gale is a separate operator-selected
        follow-up with an explicit next-candle deadline.
        """
        self.gale_pending=None
        if not self.gale_enabled or not self.auto or self.auto_strategy!='zigzag_fractal':
            return
        if p.get('gale_level'):
            self.gale_status='Gale concluído; sem segundo Martingale'
            return
        if p.get('status')!='LOSS':
            self.gale_status='Sem Gale: resultado não foi LOSS'
            return
        symbol=p.get('asset')
        watch=self.radar.watches.get(symbol)
        stake=round(float(p['amount'])*2,2)
        pnl=sum(x.get('net',0) for x in self.history)-self.baseline
        asset=self.assets.get(symbol,{})
        timeframe=self.scan_timeframe
        if (p.get('expiry') not in self.validated_expiries or
            not watch or not watch.price_time or
            stake>100 or self.balance is None or stake>self.balance or
            not asset.get('available') or asset.get('payout',0)<self.min_payout or
            self.count>=self.limit or pnl<=-self.stop_loss or
            pnl>=self.stop_win or -pnl+stake>self.stop_loss):
            self.gale_status='Gale não agendado: expiração, saldo, ativo ou stop não permite'
            return
        tick=watch.price_time
        next_bucket=(int(tick)//timeframe+1)*timeframe
        self.gale_pending={'asset':symbol,'direction':p['direction'],
                           'amount':stake,'expiry':p['expiry'],
                           'timeframe':timeframe,'next_bucket':next_bucket,
                           'armed_at':time.time()}
        self.gale_status='Gale aguardando próxima vela de '+str(timeframe)+'s · '+symbol
        self.log(self.gale_status)

    def _gale_tick_ready(self,g):
        now=time.time()
        watch=self.radar.watches.get(g['asset'])
        if not (watch and watch.fresh(now)):return False
        tf=g['timeframe']
        tick=watch.price_time
        start=int(tick)//tf*tf
        # Enforce strict next candle and no late entry. For 3s expiry
        # require the first 1s of the newly opened 5s candle.
        allowance=1.0 if tf==5 else 2.0
        return (start==g['next_bucket'] and
                0<=tick-start<=allowance and
                now>=g['armed_at'] and now-g['armed_at']<=tf+3)

    def _try_gale_next_candle(self):
        """True while Gale has priority (including when its deadline expires)."""
        g=self.gale_pending
        if not g:return False
        now=time.time()
        watch=self.radar.watches.get(g['asset'])
        if (not self.auto or not self.demo_confirmed or not watch or
            now-g['armed_at']>g['timeframe']+3 or
            (watch.price_time and int(watch.price_time)//g['timeframe']*g['timeframe']>
             g['next_bucket']) or
            (watch.price_time and watch.price_time>g['next_bucket']+
             (1.0 if g['timeframe']==5 else 2.0))):
            self.gale_pending=None
            self.gale_status='Gale cancelado: próxima vela perdida ou DEMO indisponível'
            self.log(self.gale_status)
            return False
        if not self._gale_tick_ready(g):return True
        try:
            self.order(g['direction'],g['amount'],g['expiry'],symbol=g['asset'],gale=True)
        except ValueError as error:
            self.gale_pending=None
            self.gale_status='Gale descartado: '+str(error)
            self.log(self.gale_status)
        return True

    def try_scan_order(self,candidates):
        """Only fresh, newly confirmed DEMO BUY/SELL signals with selected expiry."""
        now=time.time()
        if (not candidates or self.pending or not self.demo_confirmed or
            now-self.last_order<10 or
            now<self.last_closed_at+self.pause_after):return
        for symbol in sorted(set(candidates),key=lambda s:-self.assets.get(s,{}).get('payout',0)):
            watch=self.radar.watches.get(symbol)
            asset=self.assets.get(symbol,{})
            if not (watch and watch.last_signal in ('put','call') and
                    0<=now-watch.signal_received<=MANUAL_SIGNAL_TTL and watch.fresh(now) and
                    asset.get('available') and asset.get('payout',0)>=self.min_payout):
                continue
            self.market_quality=watch.engine.reason
            # A three-second option must never be submitted from a late
            # 5-second breakout signal or an aged feed after network delay.
            if self.auto_expiry==3 and (now-watch.signal_received>1.0 or
                now-watch.received>1.0):
                watch.last_signal=None;watch.signal_received=0
                self.log('3s DEMO: sinal atrasado >1s; entrada descartada, sem ordem')
                continue
            selected_direction=watch.last_signal
            if self.triangle_mode:
                key=(symbol,self.scan_timeframe,self.auto_expiry)
                report=self.triangle_reports.get(key,{})
                if (self.triangle_observe or (not self.triangle_trial_only and
                    (report.get('status')!='PAPER_APROVADO' or
                     self.auto_expiry not in self.validated_expiries))):
                    price=(watch.engine.bars[-1]['close'] if watch.engine.bars else None)
                    self.triangle_observations.append({
                        'time':now,'asset':symbol,'timeframe':self.scan_timeframe,
                        'expiry':self.auto_expiry,'direction':selected_direction,
                        'price':price,'payout':asset.get('payout'),
                        'pattern':watch.engine.pattern,'status':'OBSERVADO_SEM_ORDEM'})
                    watch.last_signal=None;watch.signal_received=0
                    self.scan_signals+=1
                    self.log('TRIÂNGULO OBSERVADO '+symbol+' · '+watch.engine.pattern+
                             ' · SEM ORDEM (validação cronológica pendente).')
                    continue
            if self.technical_profile and self.technical_observe:
                self.scan_signals+=1
                self.log('OBSERVADO SEM ORDEM: '+PROFILES[self.technical_profile]+' · '+symbol+
                         ' · '+selected_direction.upper()+' · '+watch.engine.reason)
                watch.last_signal=None;watch.signal_received=0
                continue
            try:self.order(selected_direction,1.0 if self.auto_trial else self.amount,self.auto_expiry,symbol=symbol)
            except ValueError as e:
                self.auto=False;self.auto_trial=False
                self.auto_stop_reason='Varredura DEMO bloqueada: '+str(e)
                self.log(self.auto_stop_reason)
                return
            watch.last_signal=None;watch.signal_received=0
            self.scan_signals+=1
            if self.triangle_trial_only:
                self.auto=False
                self.auto_trial=False
                self.auto_stop_reason='TESTE ÚNICO DEMO enviado. Aguarde resultado oficial antes de iniciar outro teste.'
                self.log(self.auto_stop_reason)
            self.log(('%s DEMO %ds: '%('COMPRA' if selected_direction=='call' else 'VENDA',self.auto_expiry))+symbol+' · '+watch.engine.reason)
            return

    def subscribe(self,symbol):
        with self.lock:
            if self.auto:raise ValueError('Pare o automático antes de trocar o ativo.')
            if self.pending:raise ValueError('Aguarde a resolução da ordem antes de trocar o ativo.')
            if not self.connected:raise ValueError('Conecte a corretora primeiro.')
            if symbol not in self.assets or not self.assets[symbol]['available']:raise ValueError('Ativo indisponível.')
            self.auto=False;self.auto_trial=False;self.symbol=symbol;self.ticks.clear();self.received=0;self.price_time=0;self.quote_samples.clear()
            self.last_signal=None;self.last_signal_at=0;self.last_signal_bucket=None;self.minute_engine=MinuteSignals();self.exhaustion={3:TickExhaustion(3),5:TickExhaustion(5)}
            self.send('changeSymbol',{'asset':symbol,'period':5});self.send('subfor',symbol);self.log('Aguardando preços de '+symbol)
    def order(self,direction,amount,expiry=5,symbol=None,gale=False):
        with self.lock:
            if direction not in ('call','put'):raise ValueError('Direção inválida.')
            expiry=parse_expiry(expiry)
            if not isinstance(amount,(int,float)) or not math.isfinite(amount) or not 1<=amount<=100:raise ValueError('Valor demo permitido: 1 a 100.')
            if not self.connected or not self.demo_confirmed:raise ValueError('Saldo de conta demo ainda não confirmado.')
            if self.pending:raise ValueError('Há uma ordem pendente. Não será enviada outra.')
            if not gale and time.time()-self.last_order<10:raise ValueError('Aguarde o intervalo mínimo de 10 segundos.')
            if gale:
                g=self.gale_pending
                if (not self.auto or not self.gale_enabled or not g or
                    g['asset']!=(self.symbol if symbol is None else symbol) or
                    g['direction']!=direction or g['expiry']!=expiry or
                    abs(g['amount']-amount)>0.0001 or not self._gale_tick_ready(g)):
                    raise ValueError('Gale bloqueado: próxima vela não confirmada ou configuração mudou.')
                pnl=sum(x.get('net',0) for x in self.history)-self.baseline
                if (self.count>=self.limit or pnl>=self.stop_win or
                    pnl<=-self.stop_loss or -pnl+amount>self.stop_loss):
                    raise ValueError('Gale excede o limite de risco configurado.')
            target=self.symbol if symbol is None else symbol
            if symbol is not None:
                if not self.auto or self.auto_strategy!='zigzag_fractal':
                    raise ValueError('Ativo externo permitido somente na varredura DEMO ativa.')
                watch=self.radar.watches.get(symbol)
                if not watch or not watch.fresh(time.time()):
                    raise ValueError('Feed do ativo de varredura ausente ou atrasado.')
            elif not self.fresh_quote():raise ValueError('Preço ausente ou atrasado. Ordem bloqueada.')
            asset=self.assets.get(target,{})
            if not asset.get('available') or (symbol is None and not target.endswith('_otc')):raise ValueError('Ativo DEMO fechado ou indisponível para o modo escolhido.')
            if asset.get('payout',0)<=80 or asset.get('payout',0)<self.min_payout:raise ValueError('Payout precisa ser superior a 80% e atingir o mínimo configurado.')
            if self.balance is None or amount>self.balance:raise ValueError('Saldo demo insuficiente ou desconhecido.')
            rid='demo-'+uuid.uuid4().hex
            self.pending={'id':str(uuid.uuid4()),'requestId':rid,'asset':target,'direction':direction,'amount':amount,'payout':asset['payout'],'expiry':expiry,'status':'ENVIANDO','sent_at':time.time(),'broker_order_id':None,'timed_out':False,'gale_level':1 if gale else 0,'strategy':self.technical_profile or ('triangle' if self.triangle_mode else 'zigzag_fractal' if self.auto_strategy=='zigzag_fractal' else 'standard')}
            self.last_order=time.time();self.count+=1
            if gale:
                self.gale_pending=None
                self.gale_status='Gale DEMO enviado: '+target+' · '+direction.upper()+' ×2'
            self.save(self.pending)
            try:self.send('openOrder',{'asset':target,'amount':amount,'action':direction,'isDemo':1,'requestId':rid,'optionType':100,'time':expiry})
            except Exception:self.auto=False;self.log('Envio sem confirmação. Não repita a ordem; confira na corretora.');raise ValueError('Envio sem confirmação. Automático pausado.') from None
            self.log('Ordem demo enviada; aguardando confirmação.')
    def resolve_unconfirmed_order(self,pending_id,confirm_no_open_orders):
        """Explicitly release a stuck DEMO order after user checks broker.

        No automatic reconciliation is claimed, and this does not submit,
        replay or cancel broker trades. A complete audit row is retained.
        """
        with self.lock:
            p=self.pending
            if not p or p.get('id')!=pending_id:
                raise ValueError('A pendência mudou. Atualize a tela antes de liberar.')
            if type(confirm_no_open_orders) is not bool or not confirm_no_open_orders:
                raise ValueError('Confirme que verificou na corretora que não existe operação aberta.')
            if not self.demo_confirmed or not self.connected:
                raise ValueError('Conecte e confira a conta DEMO antes de liberar a pendência.')
            if time.time()-p.get('sent_at',time.time())<=max(30,p.get('expiry',5)+30) or not p.get('timed_out'):
                raise ValueError('Aguarde o prazo de conferência da ordem antes de liberar.')
            self.auto=False;self.auto_trial=False
            self.auto_stop_reason='Pendência liberada após conferência manual. Reative o automático quando desejar.'
            # Never pretend a missing broker close is WIN or LOSS. The
            # original ID remains in persisted/history audit for examination.
            p['status']='RESULTADO_DESCONHECIDO'
            p['result']={'review':'Conferido manualmente no painel: usuário declarou não haver operação DEMO aberta.'}
            self.history.append(p)
            self.history=self.history[-300:]
            self.pending=None
            self.last_closed_at=time.time()
            self.save(p)
            self.log('Pendência arquivada como RESULTADO DESCONHECIDO após confirmação do usuário. '
                     'Nenhuma ordem foi enviada ou cancelada. Automático permanece parado.')
            return True

    def signal_status(self,allow_auto=False,expiry=5,fast_strategy=None):
        """Current server-side recommendation, never a claimed win probability."""
        now=time.time()
        fresh=bool(self.demo_confirmed and self.connected and self.fresh_quote())
        long_mode=expiry in LONG_EXPIRIES
        active_strategy=fast_strategy if fast_strategy is not None else self.fast_strategy
        micro=self.exhaustion.get(expiry) if expiry in EXHAUSTION_EXPIRIES and active_strategy=='exhaustion' else None
        timestamp=micro.signal_at if micro else self.minute_engine.signal_at if long_mode else self.last_signal_at
        direction=(micro.direction if micro else self.minute_engine.direction if long_mode else self.last_signal) if fresh and timestamp and now-timestamp<=MANUAL_SIGNAL_TTL else None
        # Reversals must NOT pass a trend-continuation microfilter, which would
        # reject an opposite-direction tick exhaustion by construction. The
        # independent tick engine requires a measured late stretch, retracement,
        # multiple reverse ticks and an unexpired live source bucket.
        quality=bool(direction and (
            micro.ready(now,self.price_time) if micro else
            long_mode or not_lateral(self.ticks,direction)))
        asset=self.assets.get(self.symbol,{})
        available=bool(asset.get('available') and self.symbol.endswith('_otc'))
        cooldown=max(0.,max(self.last_order+AUTO_INTERVAL_SECONDS if self.last_order else 0,
                             self.last_closed_at+self.pause_after if self.last_closed_at else 0)-now)
        # Movement efficiency is never a claimed win probability.
        if micro:
            strength=micro.strength
        elif long_mode:
            strength=self.minute_engine.strength
        else:
            buckets={int(t):p for t,p in self.ticks if isinstance(t,(int,float)) and isinstance(p,(int,float))
                     and math.isfinite(t) and math.isfinite(p) and p>0}
            prices=[p for _,p in sorted(buckets.items())[-10:]]
            if len(prices)>=10:
                gross=sum(abs(prices[i]-prices[i-1]) for i in range(1,len(prices)))
                strength=round(100*abs(prices[-1]-prices[0])/gross) if gross>0 else 0
            else: strength=None
        reason=('Conta DEMO desconectada' if not self.demo_confirmed or not self.connected else
                'Aguardando preços atuais' if not fresh else
                'Ordem anterior pendente' if self.pending else
                'Modo automático ativo; pare-o para executar manualmente' if self.auto and not allow_auto else
                (micro.reason if micro else self.minute_engine.reason if long_mode else 'Aguardando sinal novo') if not direction else
                ('Sinal de esgotamento expirado ou incompleto' if micro else 'Mercado lateralizado; sinal bloqueado') if not quality else
                'Ativo OTC indisponível' if not available else
                'Payout abaixo do mínimo' if asset.get('payout',0)<self.min_payout else
                'Aguardando pausa após a última operação' if cooldown>0 else
                'Sinal pronto para sua decisão')
        ready=bool(direction and quality and available and fresh and not self.pending and (not self.auto or allow_auto)
                   and cooldown==0 and asset.get('payout',0)>=self.min_payout)
        return {'direction':direction,'kind':('tick_exhaustion' if micro else 'm1_ema_rsi_m5' if long_mode else self.last_signal_kind) if direction else None,
                'strength':strength if direction else None,'ready':ready,
                'reason':reason,'age':round(now-timestamp,2) if direction else None,
                'cooldown':round(cooldown,1),'asset':self.symbol,'payout':asset.get('payout',0)}

    def order_signal(self,amount,expiry,symbol,pause_after=20,min_payout=80,fast_strategy='trend'):
        """Single explicit user click; read direction from verified current signal.

        Never trust a client-provided direction or stale signal from a
        screenshot. No background order placement or automatic restart.
        """
        with self.lock:
            expiry=parse_expiry(expiry)
            if fast_strategy not in ('trend','exhaustion') or (fast_strategy=='exhaustion' and expiry not in EXHAUSTION_EXPIRIES):
                raise ValueError('Modo de ticks inválido para o vencimento escolhido.')
            if type(pause_after) is not int or pause_after not in PAUSE_CHOICES:
                raise ValueError('Escolha pausa de 5, 10, 15, 20 ou 30 segundos.')
            if not isinstance(min_payout,(int,float)) or isinstance(min_payout,bool) or not 0<=min_payout<=100:
                raise ValueError('Payout mínimo inválido.')
            if symbol!=self.symbol:
                raise ValueError('Ativo mudou. Atualize o sinal antes de operar.')
            self.pause_after=pause_after
            self.min_payout=float(min_payout)
            info=self.signal_status(expiry=expiry,fast_strategy=fast_strategy)
            if not info['ready']:
                raise ValueError(info['reason']+'. Nenhuma ordem enviada.')
            direction=info['direction']
            self.order(direction,amount,expiry)
            # Consume this opportunity. Fresh broker ticks must create a new
            # qualified signal before another user-initiated order.
            if fast_strategy=='exhaustion':
                self.exhaustion[expiry].clear_signal()
            elif expiry in LONG_EXPIRIES:
                self.minute_engine.direction=None;self.minute_engine.signal_at=0
            else:
                self.last_signal=None;self.last_signal_at=0
            self.log('Entrada DEMO enviada por clique no sinal %s. Nenhuma operação automática iniciada.'%
                     ('BUY' if direction=='call' else 'SELL'))
            return {'direction':direction,'expiry':expiry}

    def start_auto(self,c):
        with self.lock:
            expiry=parse_expiry(c.get('expiry',5))
            strategy=c.get('strategy','standard')
            if strategy not in ('standard','zigzag_fractal'):
                raise ValueError('Estratégia DEMO desconhecida.')
            analysis_timeframe=c.get('analysis_timeframe',5 if expiry==5 else 60)
            zone_mode=c.get('zone_mode',False)
            triangle_mode=c.get('triangle_mode',False)
            triangle_observe=c.get('triangle_observe',True)
            triangle_trial_only=c.get('triangle_trial_only',False)
            triangle_sensitivity=c.get('triangle_sensitivity','strict')
            triangle_entry=c.get('triangle_entry','both')
            triangle_adx=c.get('triangle_adx',False)
            triangle_ema=c.get('triangle_ema',False)
            technical_profile=c.get('technical_profile','')
            technical_observe=c.get('technical_observe',True)
            if (type(technical_profile) is not str or
                (technical_profile and technical_profile not in PROFILES) or
                type(technical_observe) is not bool or
                (technical_profile and (strategy!='zigzag_fractal' or triangle_mode or zone_mode))):
                raise ValueError('Estratégia técnica inválida; use uma opção do seletor DEMO.')
            if (type(triangle_mode) is not bool or type(triangle_observe) is not bool or
                (triangle_mode and (strategy!='zigzag_fractal' or zone_mode)) or
                triangle_entry not in ('breakout','retest','both') or
                type(triangle_adx) is not bool or type(triangle_ema) is not bool or
                type(triangle_trial_only) is not bool or
                triangle_sensitivity not in ('strict','balanced') or
                (triangle_sensitivity=='balanced' and (not triangle_mode or analysis_timeframe!=5)) or
                (triangle_trial_only and (not triangle_mode or triangle_observe or
                    analysis_timeframe!=5 or expiry not in (3,5)))):
                raise ValueError('Configuração de triângulo inválida.')
            if type(zone_mode) is not bool or (zone_mode and (strategy!='zigzag_fractal' or analysis_timeframe!=5)):
                raise ValueError('Gráfico de regiões exige estratégia ZigZag DEMO com candles de 5 segundos.')
            if type(analysis_timeframe) is not int or analysis_timeframe not in (5,60,120,300):
                raise ValueError('Timeframe de análise inválido: escolha 5s, M1, M2 ou M5.')
            allowed={5:(3,5,60),60:(60,),120:(60,120,180)}
            if zone_mode:
                allowed[5]=(3,5,60,120,180)
            if triangle_mode:
                allowed={5:(3,5,60,120,180,300),60:(60,120,180,300),
                         120:(120,180,300),300:(300,)}
            if technical_profile:
                allowed=EXPIRIES
            if strategy=='zigzag_fractal' and (c.get('scan_all') is not True or
                expiry not in allowed[analysis_timeframe]):
                raise ValueError('Expiração incompatível com o timeframe/estratégia selecionados. Confira as combinações disponíveis.')
            fast_strategy=c.get('fast_strategy','trend')
            if fast_strategy not in ('trend','exhaustion') or (fast_strategy=='exhaustion' and expiry not in EXHAUSTION_EXPIRIES):
                raise ValueError('Motor de segundos inválido para a expiração selecionada.')
            pause=c.get('pause_after',20)
            if type(pause) is not int or pause not in PAUSE_CHOICES:
                raise ValueError('Escolha pausa de 5, 10, 15, 20 ou 30 segundos.')
            gale_enabled=c.get('gale_enabled',False)
            if type(gale_enabled) is not bool or (gale_enabled and
                (strategy!='zigzag_fractal' or triangle_mode or zone_mode)):
                raise ValueError('Martingale disponível somente em ZigZag + Fractal na conta DEMO.')
            filter_lateral=c.get('filter_lateral',True)
            if type(filter_lateral) is not bool:
                raise ValueError('Filtro de lateralização inválido.')
            if not self.connected or not self.demo_confirmed or self.pending or self.closed:
                raise ValueError('Conexão DEMO confirmada e sem ordem pendente necessária.')
            if self.auto:raise ValueError('O automático DEMO já está ativo.')
            vals=[float(c.get(k,0)) for k in ('amount','stop_win','stop_loss','min_payout')]
            limit=int(c.get('limit',0))
            if not all(math.isfinite(v) for v in vals) or not 1<=vals[0]<=100 or not 1<=vals[1]<=10000 or not 1<=vals[2]<=10000 or not 1<=limit<=1000 or not 0<=vals[3]<=100:
                raise ValueError('Revise os limites do automático.')
            if triangle_trial_only:
                if vals[0]!=1:
                    raise ValueError('Teste único de triângulo exige valor 1 (USD DEMO).')
                # One first experimental demo order for duration calibration;
                # never auto-promote this profile to unrestricted trading.
                limit=1
            if triangle_mode and not triangle_observe and not triangle_trial_only:
                if triangle_sensitivity!='strict':
                    raise ValueError('Automático contínuo exige estratégia rigorosa validada.')
                if expiry not in self.validated_expiries:
                    raise ValueError('Triângulo: expiração ainda não validada por execução DEMO oficial. Use OBSERVAÇÃO.')
                suitable=[r for (sym,tf,exp),r in self.triangle_reports.items()
                          if tf==analysis_timeframe and exp==expiry and r.get('status')=='PAPER_APROVADO']
                if not suitable:
                    raise ValueError('Triângulo: sem backtest cronológico aprovado para este timeframe/expiração. Use OBSERVAÇÃO.')
            # A missing duration validation no longer requires a manual order.
            # Automatically test just ONE demo order of amount 1; never silently
            # use the full configured stake until official settlement validates
            # the exact requested expiry.
            trial=expiry not in self.validated_expiries
            if trial and vals[0]!=1 and not (triangle_mode and triangle_observe) and not (technical_profile and technical_observe):
                raise ValueError('Para o primeiro teste automático de %ds use valor 1 na conta DEMO.'%expiry)
            desired=c.get('symbol')
            # The selected UI asset is authoritative. Previously an already
            # subscribed (different) OTC asset silently won over the user's
            # choice, leaving the bot analyzing the wrong instrument.
            subscribed=False
            if strategy=='zigzag_fractal':
                factory=(lambda:TriangleBreakout(analysis_timeframe,triangle_entry,triangle_adx,triangle_ema,sensitivity=triangle_sensitivity)) if triangle_mode else ((lambda:TechnicalStrategy(technical_profile,analysis_timeframe)) if technical_profile else (PriceActionZones5s if zone_mode else {5:ZigZagFractalTrend5s,60:ZigZagFractalTrend,120:ZigZagFractalTrendM2}[analysis_timeframe]))
                radar=Radar(factory)
                radar.sync(self.assets,vals[3])
                if not radar.eligible:
                    raise ValueError('Nenhum ativo DEMO aberto com payout mínimo para varredura.')
            elif isinstance(desired,str) and desired:
                chosen=self.assets.get(desired,{})
                if not chosen.get('available') or not desired.endswith('_otc'):
                    raise ValueError('Ativo escolhido indisponível para a DEMO.')
                if chosen.get('payout',0)<vals[3]:
                    raise ValueError('Payout do ativo escolhido abaixo do mínimo configurado.')
                if desired!=self.symbol:
                    self.subscribe(desired);subscribed=True
            elif not (self.symbol in self.assets and self.assets[self.symbol].get('available') and self.symbol.endswith('_otc')):
                candidates=[a for a in self.assets.values() if a.get('available') and a.get('symbol','').endswith('_otc') and a.get('payout',0)>=vals[3]]
                if not candidates:raise ValueError('Não há ativos OTC disponíveis com o payout mínimo. Automático não iniciado.')
                self.subscribe(max(candidates,key=lambda a:a['payout'])['symbol']);subscribed=True
            if strategy!='zigzag_fractal' and self.assets.get(self.symbol,{}).get('payout',0)<vals[3]:
                raise ValueError('Ativo selecionado abaixo do payout mínimo; escolha outro.')
            if strategy!='zigzag_fractal' and not subscribed and not self.fresh_quote():
                # One subscription only; re-subscribing on every start
                # otherwise erased genuine M5 candle warmup.
                self.subscribe(self.symbol)
            self.amount,self.stop_win,self.stop_loss,self.min_payout=vals
            self.auto_expiry=expiry;self.pause_after=pause;self.lateral_filter=filter_lateral
            self.fast_strategy=fast_strategy
            self.auto_strategy=strategy
            self.technical_profile=technical_profile
            self.technical_observe=technical_observe if technical_profile else False
            self.gale_enabled=gale_enabled
            self.gale_pending=None
            self.gale_status=('Martingale 1×2 ativado: aguardando LOSS oficial' if gale_enabled
                              else 'Martingale desligado')
            self.zone_mode=(zone_mode or triangle_mode) if strategy=='zigzag_fractal' else False
            self.triangle_mode=triangle_mode if strategy=='zigzag_fractal' else False
            self.triangle_observe=triangle_observe if self.triangle_mode else False
            self.triangle_trial_only=triangle_trial_only if self.triangle_mode else False
            self.triangle_sensitivity=triangle_sensitivity if self.triangle_mode else 'strict'
            self.triangle_entry=triangle_entry
            self.triangle_adx=triangle_adx
            self.triangle_ema=triangle_ema
            self.scan_timeframe=analysis_timeframe if strategy=='zigzag_fractal' else 60
            self.market_quality=('Buscando histórico ZigZag/Fractal + linha de tendência em %s'%{5:'5s',60:'M1',120:'M2',300:'M5'}[self.scan_timeframe]) if strategy=='zigzag_fractal' else 'Aguardando tendência'
            self.limit=limit;self.count=0
            self.baseline=sum(x.get('net',0) for x in self.history)
            self.auto_trial=(trial and not (triangle_mode and triangle_observe) and not (technical_profile and technical_observe)) or triangle_trial_only;self.auto_started_at=time.time();self.auto=True
            self.auto_stop_reason='';self.feed_lag_warning=False
            if strategy=='zigzag_fractal':
                self.radar=radar
                self.scan_queue=deque(sorted(radar.eligible,key=lambda s:(-radar.eligible[s]['payout'],s)))
                self.scan_last_subscribe=0
                self.scan_signals=0
                self.scan_last_verified_at=0
                self.history_queue=deque(sorted(radar.eligible,key=lambda s:(-radar.eligible[s]['payout'],s)))
                self.history_requests.clear()
                self.history_requested.clear()
                self.history_last_request=0
                self.history_loaded_count=0
                self.history_unmatched=0
                self.subscribe_scan_batch(force=True)
                if not self.auto:raise ValueError(self.auto_stop_reason)
                self.log((('ESTRATÉGIA '+PROFILES[technical_profile]+': '+('OBSERVAÇÃO SEM ORDENS' if technical_observe else 'TESTE DEMO EXPERIMENTAL')+'; ') if technical_profile else 'TRIÂNGULO: TESTE ÚNICO DEMO valor 1; sem aprovação contínua; ' if self.triangle_trial_only else 'TRIÂNGULO BREAKOUT: OBSERVAÇÃO sem ordens; ' if self.triangle_mode and self.triangle_observe else 'TRIÂNGULO BREAKOUT: DEMO validada; ' if self.triangle_mode else 'ZONAS AO VIVO: suporte, resistência; ' if self.zone_mode else 'VARREDURA ZigZag + Fractal + linha; ')+('%d ativos DEMO; candles %s; expiração %ds.'%(len(radar.eligible),{5:'5s',60:'M1',120:'M2',300:'M5'}[self.scan_timeframe],expiry)))
                return
            self.log(('AUTOMÁTICO POR SINAL ativo em DEMO: primeira entrada de valor 1 valida a expiração; depois continua apenas com sinais atuais.' if trial else
                     'AUTOMÁTICO POR SINAL ativo em DEMO: BUY/SELL obedecem ao cartão, pausa e limites.') +
                     ' Expiração: %ds.'%expiry)
    def snapshot(self):
        with self.lock:
            # Short interruptions must not permanently disable auto; NEVER
            # enter while the quote freshness guard is false. Prolonged loss
            # of data does stop the bot and needs explicit user restart.
            now=time.time()
            if self.auto and self.auto_strategy=='zigzag_fractal':
                self.subscribe_scan_batch(now)
                self.request_history_batch(now)
                age=now-(self.scan_last_verified_at or self.auto_started_at)
            else:
                age=(now-self.received) if self.received else (now-self.auto_started_at)
            # M5 needs a long continuous observation period; never stop it
            # because a mobile browser is suspended. Quote freshness remains
            # mandatory for EVERY order and missing candles are never filled.
            feed_limit=M1_FEED_STOP_SECONDS if self.auto_expiry in LONG_EXPIRIES else 20
            if self.auto and now-self.auto_started_at>=AUTO_MAX_SESSION_SECONDS:
                self.auto=False;self.auto_trial=False
                self.auto_stop_reason='Sessão automática DEMO atingiu 60 minutos; reinício manual obrigatório.'
                self.log(self.auto_stop_reason)
            elif self.auto and age>feed_limit:
                self.auto=False;self.auto_trial=False
                self.auto_stop_reason='Sem cotações por mais de %d segundos. Confira a conexão antes de reiniciar.'%feed_limit
                self.log(self.auto_stop_reason)
            elif self.auto and age>3 and not self.feed_lag_warning:
                self.feed_lag_warning=True
                self.log('Leitura temporariamente atrasada. Aguardando novos preços; nenhuma entrada será enviada sem cotação atual.')
            elif self.auto and age<=2 and self.feed_lag_warning:
                self.feed_lag_warning=False
                self.log('Cotações recuperadas. Automático continua aguardando sinais.')
            if self.pending and time.time()-self.pending['sent_at']>max(30,self.pending.get('expiry',5)+30) and not self.pending.get('timed_out'):
                # A late official result must clear this automatically.
                # Keep auto armed, but other orders remain blocked while
                # this pending record exists (even after this timeout).
                self.pending['timed_out']=True
                self.pending['status']='RESULTADO_PENDENTE'
                self.save(self.pending)
                self.log('Reconciliação automática: aguardando resultado oficial da corretora. Sem novas entradas enquanto esta ordem estiver pendente.')
            if self.auto and self.triangle_mode and now-self.triangle_last_report>30:
                # Validate observed real streams, at most a few assets per
                # status call; never infer profitability from 3s expiry on 5s bars.
                keys=sorted(self.radar.watches,
                            key=lambda sym:len(self.radar.watches[sym].engine.bars),
                            reverse=True)
                for sym in keys[:3]:
                    watch=self.radar.watches[sym]
                    if len(watch.engine.bars)<250:continue
                    asset=self.assets.get(sym,{})
                    key=(sym,self.scan_timeframe,self.auto_expiry)
                    self.triangle_reports[key]=walkforward(
                        list(watch.engine.bars),sym,self.scan_timeframe,
                        self.auto_expiry,asset.get('payout',0),
                        self.triangle_entry,self.triangle_adx,self.triangle_ema)
                self.triangle_last_report=now
            radar_status=self.radar.status(now) if self.auto_strategy=='zigzag_fractal' else None
            return {'auto_strategy':self.auto_strategy,'technical_profile':self.technical_profile,'technical_observe':self.technical_observe,'gale_enabled':self.gale_enabled,'gale_armed':bool(self.gale_pending),'gale_status':self.gale_status,'zone_mode':self.zone_mode,'triangle_mode':self.triangle_mode,'triangle_observe':self.triangle_observe,
                    'triangle_trial_only':self.triangle_trial_only,'triangle_sensitivity':self.triangle_sensitivity,
                    'triangle_reports':list(self.triangle_reports.values())[-10:],
                    'triangle_observations':list(self.triangle_observations)[-12:],
                    'triangle_entry':getattr(self,'triangle_entry','both'),
                    'scan_timeframe':self.scan_timeframe,'radar':radar_status,'scan_signals':self.scan_signals,
                    'history_requested':len(self.history_requested),
                    'history_loaded_count':self.history_loaded_count,
                    'history_unmatched':self.history_unmatched,
                    'connection_state':self.connection_state,'connection_failure':self.connection_failure,
                    'connection_attempt':self.connection_attempt,
                    'connected':self.connected,'connecting':self.connecting,'demo_confirmed':self.demo_confirmed,'balance':self.balance,'assets':list(self.assets.values()),'symbol':self.symbol,'ticks':list(self.ticks)[-200:],'age':round(max(0,time.time()-self.received),1) if self.received else None,'source_offset_s':round(time.time()-self.price_time,1) if self.price_time else None,'quote_verified':self.fresh_quote(),'last_app_ping_age':round(time.time()-self.last_app_ping,1) if self.last_app_ping else None,'message':self.message,'auto':self.auto,'auto_expiry':self.auto_expiry,'auto_trial':self.auto_trial,'auto_stop_reason':self.auto_stop_reason,
                    'pause_after':self.pause_after,'filter_lateral':self.lateral_filter,'market_quality':self.market_quality,
                    'auto_waiting_prices':bool(self.auto and age>3),
                    'validated':self.validated,'validated_expiries':sorted(self.validated_expiries),'validation_message':self.validation_message,
                    'signal':self.last_signal if self.fresh_quote() and time.time()-self.last_signal_at<=1.5 else None,
                    'signal_age':round(time.time()-self.last_signal_at,2) if self.last_signal_at and time.time()-self.last_signal_at<=1.5 else None,
                    'signal_kind':self.last_signal_kind if self.last_signal_at and time.time()-self.last_signal_at<=1.5 else None,
                    'signal_offer':self.signal_status(expiry=5),
                    'long_signal_offer':self.signal_status(expiry=60),
                    'exhaustion_offer_3':self.signal_status(expiry=3,fast_strategy='exhaustion'),
                    'exhaustion_offer_5':self.signal_status(expiry=5,fast_strategy='exhaustion'),
                    'exhaustion_3':self.exhaustion[3].status(),
                    'exhaustion_5':self.exhaustion[5].status(),
                    'fast_strategy':self.fast_strategy,
                    'm1_candles':len(self.minute_engine.bars),'m1_status':self.minute_engine.reason,
                    'm5_candles':len(five_minute_closes(list(self.minute_engine.bars))),
                    'm1_completed_total':self.minute_engine.completed_bars,
                    'm1_rejected':self.minute_engine.rejected_bars,
                    'm1_last_gap':self.minute_engine.last_gap,
                    'm1_live_samples':len(self.minute_engine.current['sample_seconds']) if self.minute_engine.current else 0,
                    'supported_expiries':list(ALL_EXPIRIES),
                    'expiry_profile':'M5_M1' if self.auto_expiry in LONG_EXPIRIES else 'QUICK_TICKS',
                    'expiry_support_note':'Prazos configurados para testes DEMO, disponibilidade real depende da corretora e ativo.',
                    'auto_interval':AUTO_INTERVAL_SECONDS,'auto_count':self.count,'auto_limit':self.limit,
                    'auto_session_remaining':round(max(0,AUTO_MAX_SESSION_SECONDS-(time.time()-self.auto_started_at)),1) if self.auto else 0,
                    'auto_feed_stop_after':M1_FEED_STOP_SECONDS if self.auto_expiry in LONG_EXPIRIES else 20,
                    'next_entry_in':round(max(0,max((self.last_order+AUTO_INTERVAL_SECONDS) if self.last_order else 0,
                                                  (self.last_closed_at+self.pause_after) if self.last_closed_at else 0)-time.time()),1),'pending_reconciliation':('Aguardando confirmação do fechamento oficial '+str(self.pending.get('broker_order_id') or 'da ordem') if self.pending else 'Sem pendência; resultado liberado automaticamente'),'pending':{k:v for k,v in (self.pending or {}).items() if k not in ('opened','requestId')},'history':[{k:v for k,v in h.items() if k not in ('opened','requestId')} for h in self.history],'events':list(self.events)[-15:]}
    def close(self):
        self.auto_stop_reason='Sessão DEMO encerrada.';self.auto=False;self.auto_trial=False;self.closed=True;self.connected=False;self.demo_confirmed=False;self.keepalive_stop.set();self.auth={}
        if self.ws:self.ws.close()
