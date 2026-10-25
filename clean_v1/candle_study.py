"""Independent, PAPER-ONLY candle-pattern observer for Bullex PRACTICE.

No execution worker reference, no broker order commands, no trading strategy edits.
Studies genuine broker closed M1 and M5 candles in a separate daemon thread.
Never fabricates complete 24h coverage, results, or guaranteed accuracy.
"""
import hashlib,json,math,os,queue,threading,time,urllib.request
from datetime import datetime,timezone
from urllib.parse import quote
from engine import normalized
from clean_v1.m5_bars import normalized5

TABLE='xtreme_candle_study_events'
PATTERN_VERSION='study_v1_closed_forward'
MAX_LOCAL=4000

def configured():
    return bool(os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_ROLE_KEY'))

def _rest(method,query='',records=None):
    if not configured():raise RuntimeError('Supabase não configurado no servidor')
    url=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+TABLE+query
    key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
    headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    if method=='POST':headers['Prefer']='resolution=merge-duplicates,return=minimal'
    req=urllib.request.Request(url,method=method,headers=headers,
          data=json.dumps(records,ensure_ascii=False).encode('utf-8') if records is not None else None)
    with urllib.request.urlopen(req,timeout=8) as res:
        return json.loads(res.read()) if method=='GET' else None

def patterns(candles):
    if len(candles)<24:return []
    c,p=candles[-1],candles[-2]
    span=c['h']-c['l'];body=abs(c['c']-c['o'])
    if span<=0:return []
    upper=c['h']-max(c['c'],c['o']);lower=min(c['c'],c['o'])-c['l']
    prior=candles[-21:-1]
    roof=max(x['h'] for x in prior);floor=min(x['l'] for x in prior)
    out=[]
    if p['c']<p['o'] and c['c']>c['o'] and c['o']<=p['c'] and c['c']>=p['o'] and body/span>=.48:
        out.append(('Engolfo de alta','CALL'))
    if p['c']>p['o'] and c['c']<c['o'] and c['o']>=p['c'] and c['c']<=p['o'] and body/span>=.48:
        out.append(('Engolfo de baixa','PUT'))
    if span>0 and .12<=body/span<=.36 and lower/span>=.56 and upper/span<=.16:
        out.append(('Martelo (rejeição de baixa)','CALL'))
    if span>0 and .12<=body/span<=.36 and upper/span>=.56 and lower/span<=.16:
        out.append(('Estrela cadente (rejeição de alta)','PUT'))
    if c['c']>roof and c['c']>c['o'] and body/span>=.55:
        out.append(('Rompimento de resistência','CALL'))
    if c['c']<floor and c['c']<c['o'] and body/span>=.55:
        out.append(('Rompimento de suporte','PUT'))
    # Wick beyond price range followed by a close back inside it:
    # a false breakout, NOT evidence of deliberate market manipulation.
    if c['h']>roof and c['c']<roof and upper/span>=.40:
        out.append(('Falso rompimento de resistência','PUT'))
    if c['l']<floor and c['c']>floor and lower/span>=.40:
        out.append(('Falso rompimento de suporte','CALL'))
    return out

def wilson_lower(wins,n):
    if not n:return 0.
    p=wins/n;z=1.96
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n)

def summarize(rows,limit=10000):
    totals={'observations':0,'evaluated':0,'wins':0,'losses':0,'draws':0,'pending':0}
    grouped={}
    for x in rows:
        status=x.get('status','')
        if status not in ('WIN','LOSS','EMPATE','PENDENTE','SEM_COTACAO'):continue
        totals['observations']+=1
        if status=='PENDENTE':totals['pending']+=1
        if status=='WIN':totals['wins']+=1
        if status=='LOSS':totals['losses']+=1
        if status=='EMPATE':totals['draws']+=1
        if status in ('WIN','LOSS','EMPATE'):totals['evaluated']+=1
        k=(x['pattern'],int(x['timeframe']))
        grouped.setdefault(k,[]).append(x)
    patterns_out=[]
    for (name,frame),entries in grouped.items():
        done=sorted([x for x in entries if x['status'] in ('WIN','LOSS','EMPATE')],key=lambda x:x['candle_closed_at'])
        decisive=[x for x in done if x['status'] in ('WIN','LOSS')]
        wins=sum(x['status']=='WIN' for x in decisive);n=len(decisive)
        # First 30 decisive observations only establish the candidate.
        # Later observations are held out to evaluate chronological stability.
        hold=decisive[30:]
        n_oos=len(hold);w_oos=sum(x['status']=='WIN' for x in hold)
        acc=100*wins/n if n else None
        oos=100*w_oos/n_oos if n_oos else None
        low=100*wilson_lower(w_oos,n_oos) if n_oos else None
        strong=bool(n>=60 and n_oos>=30 and oos>60 and low>50)
        patterns_out.append({'pattern':name,'timeframe':frame,'events':len(entries),'wins':wins,'losses':n-wins,'draws':len(done)-n,
            'accuracy':round(acc,1) if acc is not None else None,
            'validation_events':n_oos,'validation_accuracy':round(oos,1) if oos is not None else None,
            'validation_lower_95':round(low,1) if low is not None else None,
            'candidate':strong,'stage':'PROMISSORA · APENAS ESTUDO' if strong else 'EM VALIDAÇÃO',
            'approved':False,'executable':False})
    patterns_out.sort(key=lambda x:(x['candidate'],x['validation_accuracy'] if x['validation_accuracy'] is not None else -1,x['wins']+x['losses']),reverse=True)
    return {'totals':totals,'patterns':patterns_out,'qualified':sum(x['candidate'] for x in patterns_out),'sample_limited':len(rows)>=limit}

class CandleStudy:
    def __init__(self,state,proc_call):
        self.state=state;self.proc_call=proc_call;self.queue=queue.Queue(maxsize=3)
        self.stop=threading.Event();self.lock=threading.RLock()
        self.last={};self.pending={};self.local={};self.saved=0
        self.last_data=0;self.last_market=0;self.assets=[];self.rot=0
        self.message='Iniciando observação em modo estudo';self.error=''
        self.last_heartbeat=0;self.processed=0;self.seeded=0
        self.thread=threading.Thread(target=self._loop,name='XtremeCandleStudy',daemon=True)
    def start(self):
        self.thread.start()
    def close(self):
        self.stop.set()
    def offer(self,snapshot):
        if self.stop.is_set():return
        try:self.queue.put_nowait(snapshot)
        except queue.Full:
            try:self.queue.get_nowait()
            except queue.Empty:pass
            try:self.queue.put_nowait(snapshot)
            except queue.Full:pass
    def _save(self,rows):
        if not rows:return
        if not configured():
            self.error='Supabase não configurado: estudo somente na memória desta sessão'
            return
        try:
            _rest('POST','?on_conflict=event_key',rows)
            self.saved+=len(rows);self.error=''
        except Exception as e:
            self.error='Gravação indisponível no Supabase ('+type(e).__name__+'). Verifique as credenciais do Render.'
    def _resume(self):
        if not configured():return
        try:
            account=quote(self.state['archive_account'],safe='')
            rows=_rest('GET','?select=*&account_key=eq.'+account+'&status=eq.PENDENTE&order=candle_closed_at.desc&limit=1000')
            for rec in rows:
                self.pending[rec['event_key']]=rec
                self.local[rec['event_key']]=rec
        except Exception:
            self.error='Não foi possível recuperar previsões pendentes do Supabase'
    def _process(self,snapshot):
        now=float(snapshot.get('now') or time.time())
        updated=[]
        account=self.state['archive_account']
        for item in snapshot.get('items',[])[:32]:
            asset=str(item.get('asset',''))[:80]
            if not asset:continue
            for frame,seconds,candles in (
              (1,60,normalized(item.get('candles',[]),now)),
              (5,300,normalized5(item.get('candles5',[]),now))):
                if not candles:continue
                last=candles[-1];key=(asset,frame)
                latest=last['t']
                # Close outcomes for pending events only when the NEXT candle
                # really is closed. Entry = open of that next candle.
                mapped={c['t']:c for c in candles}
                for event_id,event in list(self.pending.items()):
                    if event['asset']!=asset or event['timeframe']!=frame:continue
                    target=int(datetime.fromisoformat(event['candle_closed_at'].replace('Z','+00:00')).timestamp())
                    # target is the start time of the NEXT candle
                    following=mapped.get(target)
                    if following:
                        delta=following['c']-following['o']
                        if event['direction']=='PUT':delta=-delta
                        event.update(status='WIN' if delta>0 else 'LOSS' if delta<0 else 'EMPATE',
                            entry_price=following['o'],exit_price=following['c'],
                            settled_at=datetime.fromtimestamp(target+seconds,timezone.utc).isoformat())
                        self.local[event_id]=event
                        self.pending.pop(event_id,None)
                        updated.append(event.copy())
                    elif latest>target+seconds*5:
                        event.update(status='SEM_COTACAO',settled_at=datetime.now(timezone.utc).isoformat())
                        self.local[event_id]=event;self.pending.pop(event_id,None);updated.append(event.copy())
                last_seen=self.last.get(key)
                if last_seen is None:
                    self.last[key]=latest;self.seeded+=1
                    continue
                if latest<=last_seen:continue
                self.last[key]=latest;self.processed+=1
                # No historical replay: generate proposals only for freshly
                # observed current candle, not missed/stale snapshots.
                if latest+seconds!=int(now//seconds)*seconds:continue
                for pattern,direction in patterns(candles):
                    candle_closed=latest+seconds
                    event_key=hashlib.sha256(
                        (PATTERN_VERSION+'|'+account+'|'+asset+'|'+str(frame)+'|'+str(candle_closed)+'|'+pattern+'|'+direction).encode()).hexdigest()
                    if event_key in self.local:continue
                    rec={'event_key':event_key,'account_key':account,'asset':asset,'timeframe':frame,
                         'pattern':pattern,'direction':direction,
                         'candle_closed_at':datetime.fromtimestamp(candle_closed,timezone.utc).isoformat(),
                         'expiry_minutes':frame,'status':'PENDENTE'}
                    self.local[event_key]=rec;self.pending[event_key]=rec
                    updated.append(rec.copy())
        if len(self.local)>MAX_LOCAL:
            recent=sorted(self.local.values(),key=lambda r:r['candle_closed_at'],reverse=True)[:MAX_LOCAL]
            keep={r['event_key']:r for r in recent}
            keep.update(self.pending)
            self.local=keep
        self._save(updated)
        self.last_data=time.time()
    def _read(self,command,timeout):
        lock=self.state['read_lock']
        if not lock.acquire(blocking=False):return None
        try:
            if self.stop.is_set() or self.state.get('running'):return None
            return self.proc_call(self.state['proc'],command,timeout)
        finally:lock.release()
    def _poll_idle(self):
        now=time.time()
        if now-self.last_market>=120:
            market=self._read({'op':'market','payout':80,'strategy':'sniper'},22)
            if market:
                self.assets=sorted((a['asset'] for a in market.get('assets',[]) if a.get('payout',0)>=80))
                self.last_market=now
        if not self.assets:return None
        take=min(12,len(self.assets));start=self.rot%len(self.assets)
        selected=[self.assets[(start+i)%len(self.assets)] for i in range(take)]
        self.rot+=take
        return self._read({'op':'snapshot','assets':selected,'sniper_only':True,'enable_m5':True},18)
    def _loop(self):
        self._resume()
        while not self.stop.is_set():
            self.last_heartbeat=time.time()
            try:
                if self.state.get('running'):
                    try:snap=self.queue.get(timeout=3)
                    except queue.Empty:snap=None
                    if snap:self._process(snap)
                    self.message='Observando sinais do scanner em leitura, sem interferir nas ordens'
                else:
                    snap=self._poll_idle()
                    if snap:self._process(snap)
                    self.message='Observando velas M1/M5, sem enviar ordens'
                    self.stop.wait(3)
            except Exception as e:
                self.message='Estudo aguardando nova leitura: '+type(e).__name__
                self.stop.wait(8)
    def status(self):
        return {'connected':not self.stop.is_set(),'reading':time.time()-self.last_data<120,
                'started':self.last_heartbeat>0,'message':self.message,'last_data_at':self.last_data,
                'heartbeat_at':self.last_heartbeat,'processed_candles':self.processed,
                'assets_seeded':self.seeded,'events_in_memory':len(self.local),
                'supabase_enabled':configured(),'saves_confirmed_this_session':self.saved,'storage_error':self.error}
    def report(self):
        status=self.status()
        if configured():
            try:
                result=[]; account=quote(self.state['archive_account'],safe='')
                for offset in range(0,10000,1000):
                    q='?select=event_key,pattern,timeframe,status,candle_closed_at&account_key=eq.'+account
                    q+='&order=candle_closed_at.desc&limit=1000&offset='+str(offset)
                    batch=_rest('GET',q)
                    if not isinstance(batch,list):raise RuntimeError('Resposta inesperada')
                    result.extend(batch)
                    if len(batch)<1000:break
                status.update(summarize(result))
                status['source']='Supabase'
            except Exception as e:
                status.update(summarize(list(self.local.values())))
                status['source']='memória da sessão'
                status['storage_error']='Consulta ao Supabase indisponível ('+type(e).__name__+')'
        else:
            status.update(summarize(list(self.local.values())))
            status['source']='memória da sessão · não persistida'
        return status
