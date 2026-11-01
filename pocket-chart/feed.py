"""Read-only Pocket Option adapter. Only allowlisted market data events can leave."""
import json,math,ssl,threading,time
from collections import deque
import websocket
from analysis import TIMEFRAMES,valid_bar,structure,evaluate

URLS=('wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket','wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket')
READ_EVENTS=frozenset(('auth','ps','indicator/load','favorite/load','subscribeSymbol','unsubscribeSymbol','changeSymbol','subfor','loadHistoryPeriod'))

def parse_auth(raw):
    try:
        raw=raw.strip();a=json.loads(raw[2:] if raw.startswith('42') else raw)
        p=a[1]
        if a[0]!='auth' or type(p['isDemo']) is not int or p['isDemo']!=1:raise ValueError()
        if not isinstance(p['session'],str) or not 10<=len(p['session'])<=16000 or type(p['uid']) is not int or p['uid']<=0:raise ValueError()
        # Reuse the demo client's original protocol options. Overwriting platform=1
        # with platform=2 can cause the broker to reject an otherwise valid SSID.
        platform=p.get('platform',2)
        if type(platform) is not int or platform not in (1,2):raise ValueError()
        fast=p.get('isFastHistory',True)
        optimized=p.get('isOptimized',True)
        if type(fast) is not bool or type(optimized) is not bool:raise ValueError()
        return {'session':p['session'],'uid':p['uid'],'isDemo':1,
                'platform':platform,'isFastHistory':fast,'isOptimized':optimized}
    except (ValueError,IndexError,KeyError,TypeError,AttributeError):raise ValueError('Informe o pacote auth da sessão demonstrativa (isDemo: 1).') from None

class Feed:
    def __init__(self,auth):
        self.auth=auth;self.lock=threading.RLock();self.ws=None;self.closed=False;self.connected=False
        self.assets={};self.symbol='';self.period=60;self.bars={};self.current=None;self.last_source=0;self.received=0
        self.message='Conectando à Pocket Option…';self.binary=None;self.requests={};self.history_requested=False
        self.signals=deque(maxlen=120);self.last_history=0;self.last_ping=0;self.epoch=0
    def start(self):threading.Thread(target=self.run,daemon=True).start()
    def send(self,event,data=None):
        if event not in READ_EVENTS:raise ValueError('Evento não permitido: aplicativo somente de análise.')
        if not self.ws:raise ValueError('Conecte a Pocket Option.')
        self.ws.send('42'+json.dumps([event] if data is None else [event,data],separators=(',',':')))
    def run(self):
        for url in URLS:
            if self.closed:break
            self.binary=None
            ws=websocket.WebSocketApp(url,on_message=self.on_message,on_error=self.on_error,on_close=self.on_close)
            self.ws=ws
            timer=threading.Timer(25,lambda:ws.close() if not self.connected else None);timer.daemon=True;timer.start()
            ws.run_forever(origin='https://pocketoption.com',sslopt={'cert_reqs':ssl.CERT_REQUIRED,'check_hostname':True},ping_interval=20,ping_timeout=10)
            timer.cancel()
            if self.received or self.closed:break
        self.connected=False
        if not self.closed:self.message='Conexão encerrada. Reconecte uma sessão demonstrativa atual.'
    def on_error(self,*args):
        # Never log or expose raw protocol messages, tokens or session IDs.
        if not self.closed:self.message='Falha de conexão. A sessão pode ter expirado ou o servidor pode estar indisponível.'
    def on_close(self,*args):self.connected=False
    def on_message(self,ws,msg):
        try:
            with self.lock:
                if isinstance(msg,bytes):
                    if self.binary:
                        name=self.binary;self.binary=None;self.event(name,json.loads(msg.decode()))
                elif msg.startswith('0'):ws.send('40')
                elif msg=='2':ws.send('3')
                elif msg.startswith('40'):self.send('auth',self.auth)
                elif msg=='41':
                    if not self.closed:self.message='A corretora encerrou a sessão antes de confirmar as cotações. Entre novamente na conta DEMO.'
                    self.connected=False;self.closed=True;ws.close()
                elif msg.startswith('451-'):self.binary=json.loads(msg.split('-',1)[1])[0]
                elif msg.startswith('42'):
                    p=json.loads(msg[2:]);self.event(p[0],p[1] if len(p)>1 else {})
        except (ValueError,KeyError,TypeError,IndexError,OverflowError):self.message='Pacote de dados não reconhecido; aguardando dados válidos.'
    def event(self,name,d):
        if name=='successauth':
            self.connected=True;self.message='Sessão conectada. Aguardando catálogo de ativos.'
            self.send('indicator/load');self.send('favorite/load')
            self.ensure_selected()
        elif name=='updateAssets' and isinstance(d,list):
            self.assets={r[1]:{'symbol':r[1],'name':str(r[2]),'available':bool(r[14]),'otc':r[1].endswith('_otc')} for r in d if isinstance(r,list) and len(r)>14 and isinstance(r[1],str)}
            self.ensure_selected()
        elif name=='updateStream' and isinstance(d,list):
            for r in d:
                if isinstance(r,list) and len(r)>=3 and r[0]==self.symbol:self.tick(float(r[1]),float(r[2]))
        elif name=='loadHistoryPeriodFast' and isinstance(d,dict):
            idx=str(d.get('index',''));req=self.requests.pop(idx,None)
            if req and req==(self.symbol,self.period,self.epoch) and d.get('asset',self.symbol)==self.symbol:
                self.history(d.get('data',[]))
        elif name=='updateHistoryNewFast' and isinstance(d,dict):
            # Unindexed responses may belong to an old timeframe. Never use them.
            pass
        elif name in ('NotAuthorized','notauthorized','errorauth','failauth'):
            self.message='Autenticação DEMO recusada pela corretora. Abra a Pocket Option, entre na conta DEMO e conecte novamente.'
            self.connected=False;self.closed=True
            if self.ws:self.ws.close()
    def ensure_selected(self):
        if not self.connected or self.symbol:return
        available=sorted(s for s,a in self.assets.items() if a['available'])
        if not available:
            self.message='Sessão conectada, mas nenhum ativo aberto foi recebido da corretora.'
            return
        self.select('EURUSD_otc' if 'EURUSD_otc' in available else available[0],self.period)
    def select(self,symbol,period):
        with self.lock:
            if not self.connected:raise ValueError('Conecte a sessão antes de escolher o ativo.')
            if symbol not in self.assets or not self.assets[symbol]['available']:raise ValueError('Ativo indisponível na sessão atual.')
            if type(period) is not int or period not in TIMEFRAMES:raise ValueError('Tempo de gráfico inválido.')
            if symbol==self.symbol and period==self.period:return
            if self.symbol and self.symbol!=symbol:self.send('unsubscribeSymbol',self.symbol)
            self.symbol=symbol;self.period=period;self.bars={};self.current=None;self.signals.clear();self.requests.clear()
            self.last_source=0;self.received=0;self.history_requested=False;self.epoch+=1
            self.send('subscribeSymbol',symbol);self.send('changeSymbol',{'asset':symbol,'period':period});self.send('subfor',symbol)
            self.message='Aguardando cotações reais de '+symbol
    def request_history(self):
        if self.history_requested or not self.last_source:return
        idx=str(time.time_ns()//1000000);self.requests[idx]=(self.symbol,self.period,self.epoch)
        self.send('loadHistoryPeriod',{'asset':self.symbol,'index':int(idx),'offset':min(172800,self.period*300),'period':self.period,'time':int(self.last_source)//self.period*self.period})
        self.history_requested=True;self.last_history=time.time()
    def tick(self,t,p):
        if t>1e12:t/=1000
        # Strict source time + local arrival freshness: stale packets cannot issue signals.
        if not math.isfinite(t) or not math.isfinite(p) or p<=0 or t<=self.last_source or abs(time.time()-t)>30:return
        self.last_source=t;self.received=time.time();bucket=int(t)//self.period*self.period
        if self.current and bucket>self.current['time']:
            c=self.current
            complete=(c['first']-c['time']<=min(5,self.period*.15) and c['last']>=c['time']+self.period-min(5,self.period*.15)
                      and c['max_gap']<=min(5,self.period*.35))
            if complete:
                self.bars[c['time']]={k:c[k] for k in ('time','open','high','low','close')}
                if bucket==c['time']+self.period and t-bucket<=min(3,self.period*.25):
                    s=evaluate(sorted(self.bars.values(),key=lambda b:b['time']),self.period)
                    if s:self.signals.append(s)
            self.current=None
        if self.current is None:
            self.current={'time':bucket,'open':p,'high':p,'low':p,'close':p,'first':t,'last':t,'max_gap':0}
        else:
            self.current['max_gap']=max(self.current['max_gap'],t-self.current['last'])
            self.current['high']=max(p,self.current['high']);self.current['low']=min(p,self.current['low']);self.current['close']=p;self.current['last']=t
        self.message='Recebendo cotações reais da Pocket Option.'
        self.request_history()
        if len(self.bars)>500:self.bars={k:self.bars[k] for k in sorted(self.bars)[-500:]}
    def history(self,rows):
        if not isinstance(rows,list) or not self.last_source:return
        start=int(self.last_source)//self.period*self.period
        grouped={}
        for r in rows[:50000]:
            if isinstance(r,(list,tuple)) and len(r)>=2 or isinstance(r,dict) and 'price' in r:
                try:
                    t=float(r[0] if isinstance(r,(list,tuple)) else r.get('time',r.get('t',0)))
                    p=float(r[1] if isinstance(r,(list,tuple)) else r['price']);t=t/1000 if t>1e12 else t
                    if not math.isfinite(t) or not math.isfinite(p) or p<=0:continue
                    bucket=int(t)//self.period*self.period
                    if start-500*self.period<=bucket<start:grouped.setdefault(bucket,[]).append((t,p))
                except (ValueError,TypeError,OverflowError):pass
                continue
            if not isinstance(r,dict):continue
            try:
                t=float(r.get('time',r.get('t',0)));t=t/1000 if t>1e12 else t
                b={'time':int(t),**{k:float(r[k]) for k in ('open','high','low','close')}}
                if valid_bar(b) and b['time']%self.period==0 and start-500*self.period<=b['time']<start:
                    self.bars.setdefault(b['time'],b)
            except (ValueError,TypeError,KeyError,OverflowError):continue
        for bucket,ticks in grouped.items():
            ticks=sorted(ticks);edge=min(5,self.period*.15)
            if ticks[0][0]-bucket>edge or ticks[-1][0]<bucket+self.period-edge:continue
            if max((b[0]-a[0] for a,b in zip(ticks,ticks[1:])),default=self.period)>min(5,self.period*.35):continue
            prices=[p for _,p in ticks]
            self.bars.setdefault(bucket,{'time':bucket,'open':prices[0],'high':max(prices),'low':min(prices),'close':prices[-1]})
        # Historical OHLC is context only. Never emit historical trading signals.
        self.last_history=time.time()
    def snapshot(self):
        with self.lock:
            now=time.time()
            if self.connected and now-self.last_ping>=20:
                try:self.send('ps');self.last_ping=now
                except Exception:self.connected=False
            fresh=bool(self.connected and self.received and now-self.received<=3 and abs(now-self.last_source)<=3)
            bars=sorted(self.bars.values(),key=lambda b:b['time'])[-400:]
            ctx=structure(bars,self.period)
            current={k:self.current[k] for k in ('time','open','high','low','close')} if self.current else None
            return {'connected':self.connected,'message':self.message,'assets':sorted(self.assets.values(),key=lambda a:a['name']),
                    'symbol':self.symbol,'period':self.period,'bars':bars,'current':current,'structure':ctx,'fresh':fresh,
                    'age':round(now-self.received,1) if self.received else None,'source_time':self.last_source or None,
                    'signals':list(self.signals),'epoch':self.epoch,'history_received':bool(self.bars),'history_requested':self.history_requested}
    def close(self):
        self.closed=True;self.connected=False;self.auth={}
        if self.ws:self.ws.close()

class NativeFeed(Feed):
    """Analyze the existing demo socket on the phone. Never opens another login."""
    def __init__(self):
        super().__init__({});self.commands=deque(maxlen=32);self.message='Abra a Pocket Option no Android e selecione DEMO.'
        self.diagnostic={};self.stream_rows=0;self.selected_rows=0;self.native_seen=0;self.last_diagnostic_log=0
    def start(self):pass
    def send(self,event,data=None):
        if event not in READ_EVENTS or event=='auth':raise ValueError('Comando de leitura inválido.')
        if event!='ps':self.commands.append({'event':event,'data':data})
    def drain(self):
        with self.lock:
            result=list(self.commands);self.commands.clear();return result
    def ingest(self,events):
        if not isinstance(events,list) or len(events)>12:raise ValueError('Lote inválido.')
        with self.lock:
            for item in events:
                if not isinstance(item,dict):continue
                name=item.get('event');data=item.get('data')
                self.native_seen=time.time()
                if name=='diagnostic' and isinstance(data,dict):
                    self.diagnostic={k:int(v) for k,v in data.items() if k in ('streamPackets','streamRows','commandsReceived','commandsSent','parseErrors','sockets') and type(v) is int and 0<=v<=1000000000}
                    if time.time()-self.last_diagnostic_log>15:
                        print(json.dumps({'component':'native-market','receivedRows':self.stream_rows,'selectedRows':self.selected_rows,**self.diagnostic}),flush=True)
                        self.last_diagnostic_log=time.time()
                    continue
                if name=='updateStream' and isinstance(data,list):
                    self.stream_rows+=len(data)
                    self.selected_rows+=sum(1 for r in data if isinstance(r,list) and len(r)>=3 and r[0]==self.symbol)
                if name=='disconnected':
                    self.connected=False;self.message='A conexão demo no celular foi encerrada. Reconecte pelo botão Conectar.'
                elif name in ('successauth','updateAssets','updateStream','loadHistoryPeriodFast','errorauth','failauth'):
                    self.event(name,data)
    def snapshot(self):
        result=super().snapshot()
        if self.connected and self.native_seen and time.time()-self.native_seen>15:
            result['connected']=False;result['fresh']=False
            result['message']='O Android parou de transmitir dados. Volte à conta demo ou reconecte.'
        result['diagnostic']={**self.diagnostic,'receivedRows':self.stream_rows,'selectedRows':self.selected_rows,
                              'relayAge':round(time.time()-self.native_seen,1) if self.native_seen else None}
        return result
    def close(self):
        super().close();self.commands.clear()
