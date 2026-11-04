"""Forward-only Pulse research lab. No training on outcome candles, no broker orders.

Hypotheses are deterministic, named research templates; this is not a generative
AI or proof of a broker manipulating quotes. Only the following candle settles
the research prediction. Ranking is based solely on observed forward outcomes.
"""
from collections import deque
from hashlib import sha256
from math import isfinite,sqrt
from statistics import median
from threading import RLock

EXPERIMENTS = {
    "impulse_follow": {"name":"Pulso Direcional","version":"v1","description":"Corpo forte alinhado ao avanço de fechamentos; testa continuidade"},
    "wick_reversal": {"name":"Rejeição de Extremo","version":"v1","description":"Pavio dominante após avanço prévio; testa reversão"},
    "compression_break": {"name":"Ruptura da Compressão","version":"v1","description":"Faixa estreita seguida de expansão e fechamento direcional"},
    "three_step": {"name":"Ritmo Três Velas","version":"v2","description":"Três velas direcionais com confirmação de momentum"},
    "pullback_resume": {"name":"Retomada Pós-Recuo","version":"v1","description":"Impulso, uma correção e retomada no sentido do impulso"},
}

def candidates(bars):
    if len(bars)<25:return []
    b,p,q=bars[-1],bars[-2],bars[-3]
    recent=bars[-19:-1]
    scale=median(x['high']-x['low'] for x in recent)
    if not isfinite(scale) or scale<=0:return []
    span=b['high']-b['low']
    if not 0<span<3.5*scale:return []
    body=abs(b['close']-b['open'])
    sign=1 if b['close']>b['open'] else -1 if b['close']<b['open'] else 0
    if not sign:return []
    progress=(b['close']-bars[-5]['close'])/scale
    upper=b['high']-max(b['open'],b['close'])
    lower=min(b['open'],b['close'])-b['low']
    out=[]
    def add(key,direction,why):
        out.append({'key':key,'name':EXPERIMENTS[key]['name'],'direction':direction,
                    'reason':why,'version':EXPERIMENTS[key]['version']})
    if body/span>=.65 and abs(progress)>=1.25 and sign*progress>0 and span<=2.4*scale:
        add('impulse_follow','ALTA' if sign>0 else 'BAIXA','Corpo forte e fechamento avançando')
    if b['close']>b['open'] and upper>=2.1*body and upper>.55*span and bars[-6]['close']<b['high']-.7*scale:
        add('wick_reversal','BAIXA','Rejeição superior após avanço')
    elif b['close']<b['open'] and lower>=2.1*body and lower>.55*span and bars[-6]['close']>b['low']+.7*scale:
        add('wick_reversal','ALTA','Rejeição inferior após queda')
    compressed=median(x['high']-x['low'] for x in bars[-5:-1])<.7*scale
    high=max(x['high'] for x in bars[-5:-1])
    low=min(x['low'] for x in bars[-5:-1])
    if compressed and body/span>=.55 and b['close']>high+.1*scale:
        add('compression_break','ALTA','Saída confirmada acima da compressão')
    if compressed and body/span>=.55 and b['close']<low-.1*scale:
        add('compression_break','BAIXA','Saída confirmada abaixo da compressão')
    last3=bars[-3:]
    if all(x['close']>x['open'] for x in last3) and body/span>=.50 and progress>1.1:
        add('three_step','ALTA','Três fechamentos compradores sequenciais')
    if all(x['close']<x['open'] for x in last3) and body/span>=.50 and progress<-1.1:
        add('three_step','BAIXA','Três fechamentos vendedores sequenciais')
    if q['close']>q['open'] and p['close']<p['open'] and b['close']>p['high'] and body>=.5*scale:
        add('pullback_resume','ALTA','Recuo vendedor seguido de retomada compradora')
    if q['close']<q['open'] and p['close']>p['open'] and b['close']<p['low'] and body>=.5*scale:
        add('pullback_resume','BAIXA','Recuo comprador seguido de retomada vendedora')
    return out

class ResearchLab:
    def __init__(self):
        self.lock=RLock()
        self.enabled=True
        self.ledger=deque(maxlen=4000)
        self.pending={}
        self.seen=set()
        self.anomalies=deque(maxlen=120)
        self.anomaly_seen=set()
        self.scans=0
        self.last_scan=None
        self.rejected_late=0
        self.errors=0
        self.last_error=None
        self.dirty={}
        self.persisted_records=0
        self.store_status='CONFIGURANDO'
        self.storage_error=None
        self._last_models_at=0
    def observe(self,asset,tf,bars,now):
        """Observe closed bars only; issue prediction BEFORE a full future entry candle opens."""
        if tf not in (60,300) or len(bars)<25 or not bars:return
        latest=bars[-1]
        if not 0<=now-(latest['from']+tf)<=max(15,tf*.1):return
        with self.lock:
            if not self.enabled:return
            self.scans+=1
            self.last_scan=now
            by_time={b['from']:b for b in bars}
            for k,record in list(self.pending.items()):
                if record['asset']!=asset or record['tf']!=tf:continue
                candle=by_time.get(record['entry_at'])
                if candle and now>=record['expires_at'] and record['issued_at'] <= record['entry_at']-5:
                    delta=candle['close']-candle['open']
                    record['result']='EMPATE' if delta==0 else ('WIN' if (delta>0)==(record['direction']=='ALTA') else 'LOSS')
                    record['entry_price']=candle['open']
                    record['exit_price']=candle['close']
                    record['settled_at']=now
                    self.ledger.append(record)
                    self._mark_dirty(record)
                    del self.pending[k]
                elif now>record['expires_at']+tf:
                    record['result']='SEM DADOS'
                    record['settled_at']=now
                    self.ledger.append(record)
                    self._mark_dirty(record)
                    del self.pending[k]
            candle_id=(asset,tf,latest['from'])
            if candle_id in self.seen:return
            self.seen.add(candle_id)
            if len(self.seen)>12000:self.seen=set(list(self.seen)[-6000:])
            self._anomaly(asset,tf,bars,now)
            # Detection uses a bar that ended at latest['from']+tf. Because broker
            # responses arrive after that boundary, predicting the very next
            # candle would claim an entry at a price already in the past.
            # Research therefore waits one full interval: signal is locked now
            # for the candle AFTER the immediately starting candle.
            entry=latest['from']+2*tf
            minimum_lead=5 if tf==60 else 10
            if not entry-now>=minimum_lead:
                self.rejected_late+=1
                return
            for found in candidates(bars):
                k=(asset,tf,entry,found['key'])
                if k in self.pending:continue
                self.pending[k]={**found,'asset':asset,'tf':tf,'basis_at':latest['from'],
                                 'entry_at':entry,'expires_at':entry+tf,'issued_at':now,
                                 'minimum_lead_seconds':minimum_lead,
                                 'clock_guard':'v2_future_entry','execution':'PAPER_ONLY_NOT_EXECUTED',
                                 'result':'PENDENTE'}
                self._mark_dirty(self.pending[k])
    def _anomaly(self,asset,tf,bars,now):
        recent=bars[-21:-1]
        scale=median(x['high']-x['low'] for x in recent)
        b,p=bars[-1],bars[-2]
        flags=[]
        if scale>0 and b['high']-b['low']>4.0*scale:flags.append('Amplitude extrema de vela')
        if scale>0 and abs(b['open']-p['close'])>1.5*scale:flags.append('Gap entre velas')
        if scale>0 and (b['high']-b['low'])<.08*scale:flags.append('Amplitude muito baixa')
        for flag in flags:
            key=(asset,tf,b['from'],flag)
            if key in self.anomaly_seen:continue
            self.anomaly_seen.add(key)
            anomaly={'asset':asset,'tf':tf,'at':b['from']+tf,'event':flag,
                     'interpretation':'Anomalia estatística, não prova de manipulação'}
            self.anomalies.append(anomaly)
            self._mark_dirty(anomaly,kind='ANOMALY')
        if len(self.anomaly_seen)>2500:self.anomaly_seen=set(list(self.anomaly_seen)[-1000:])
    @staticmethod
    def event_key(record,kind='FORECAST'):
        if kind=='ANOMALY':
            raw='anomaly|%s|%s|%s|%s'%(record['asset'],record['tf'],record['at'],record['event'])
        else:
            raw='forecast|%s|%s|%s|%s|%s|%s'%(record['asset'],record['tf'],
                record['entry_at'],record['key'],record.get('version','v1'),record['direction'])
        return sha256(raw.encode()).hexdigest()

    def _mark_dirty(self,record,kind='FORECAST'):
        event_key=self.event_key(record,kind)
        payload=dict(record)
        self.dirty[event_key]={
            'event_key':event_key,'kind':kind,'asset':record['asset'],
            'timeframe':int(record['tf']),
            'entry_at':int(record['entry_at'] if kind=='FORECAST' else record['at']),
            'issued_at':record.get('issued_at') if kind=='FORECAST' else None,
            'experiment_id':record['key'] if kind=='FORECAST' else 'anomaly_'+
                sha256(record['event'].encode()).hexdigest()[:12],
            'status':record['result'] if kind=='FORECAST' else 'REGISTRADA',
            'payload':payload}

    def dirty_batch(self,limit=160):
        with self.lock:
            return [(k,dict(v)) for k,v in list(self.dirty.items())[:limit]]

    def confirm_saved(self,batch):
        with self.lock:
            for key,value in batch:
                if self.dirty.get(key)==value:self.dirty.pop(key,None)
            self.persisted_records+=len(batch)

    def restore(self,events):
        """Merge restored, already-settled forecasts with local observations.
        A saved final result always wins over an older PENDENTE state."""
        with self.lock:
            by_key={}
            for r in [*self.ledger,*self.pending.values()]:
                try:by_key[self.event_key(r)]=r
                except (KeyError,ValueError):continue
            anoms={self.event_key(x,'ANOMALY'):x for x in self.anomalies}
            for item in events:
                try:
                    kind=item['kind'];payload=item['payload'];key=item['event_key']
                    if not isinstance(payload,dict):continue
                    if kind=='ANOMALY':
                        anoms.setdefault(key,payload)
                        continue
                    if kind!='FORECAST' or payload.get('clock_guard')!='v2_future_entry':
                        continue
                    if self.event_key(payload)!=key:continue
                    old=by_key.get(key)
                    if old is None or old.get('result')=='PENDENTE' and payload.get('result')!='PENDENTE':
                        by_key[key]=payload
                    self.seen.add((payload['asset'],int(payload['tf']),int(payload['basis_at'])))
                except (KeyError,ValueError,TypeError):continue
            ordered=sorted(by_key.values(),key=lambda x:(x.get('entry_at',0),x.get('key','')))
            self.ledger=deque((x for x in ordered if x.get('result')!='PENDENTE'),maxlen=4000)
            self.pending={(x['asset'],x['tf'],x['entry_at'],x['key']):x for x in ordered
                          if x.get('result')=='PENDENTE'}
            self.anomalies=deque(sorted(anoms.values(),key=lambda x:x.get('at',0))[-120:],maxlen=120)
            self.anomaly_seen={(a['asset'],int(a['tf']),int(a['at'])-int(a['tf']),a['event'])
                               for a in self.anomalies}

    @staticmethod
    def wilson_lower(wins,total):
        if total<1:return 0.0
        z=1.96;p=wins/total;denom=1+z*z/total
        return max(0.0,(p+z*z/(2*total)-z*sqrt((p*(1-p)+z*z/(4*total))/total))/denom)

    def _ranking(self):
        all_rows=list(self.ledger);ranking=[]
        for key,exp in EXPERIMENTS.items():
            for tf in (60,300):
                rows=[x for x in all_rows if x.get('key')==key and x.get('tf')==tf
                      and x.get('result') in ('WIN','LOSS') and
                      x.get('clock_guard')=='v2_future_entry' and
                      x.get('issued_at',float('inf'))<=x.get('entry_at',0)-5]
                ordered=sorted(rows,key=lambda x:(x['entry_at'],x['asset']))
                n=len(ordered);w=sum(x['result']=='WIN' for x in ordered)
                split=max(1,int(n*.6))
                validation=ordered[split:];v_n=len(validation)
                v_w=sum(x['result']=='WIN' for x in validation)
                rate=w/n if n else None
                v_rate=v_w/v_n if v_n else None
                lower=self.wilson_lower(v_w,v_n)
                recent=ordered[-20:]
                recent_rate=sum(x['result']=='WIN' for x in recent)/len(recent) if recent else None
                # This is a research-only, provisional gate, not a calibrated edge.
                # 80 independent *forecasts* with >=30 later validation observations.
                # Lower Wilson 95% bound must exceed an approximate 80% payout
                # break-even (55.56%); the broker's true payout is checked separately.
                qualified=(n>=80 and v_n>=30 and rate>=.60 and v_rate>=.68 and
                           lower>.556 and recent_rate>=.55)
                if n<15:status='EM DESCOBERTA'
                elif qualified:status='PROMISSORA'
                elif n>=80 and v_n>=30 and (v_rate<.52 or recent_rate<.45):
                    status='REPROVADA'
                else:status='EM VALIDAÇÃO'
                # No promotion on stale setups.
                if qualified and ordered[-1]['entry_at']<__import__('time').time()-3*86400:
                    status='PAUSADA'
                ranking.append({'id':key,'name':exp['name']+' '+exp['version'],
                                'description':exp['description'],'tf':tf,
                                'signals':n,'wins':w,'losses':n-w,'rate':rate,
                                'validation_signals':v_n,'validation_wins':v_w,
                                'validation_rate':v_rate,'validation_lower_95':lower,
                                'recent_rate':recent_rate,'active':status=='PROMISSORA',
                                'status':status})
        ranking.sort(key=lambda r:(r['status']!='PROMISSORA',-(r['validation_rate'] or 0),-r['signals'],r['name']))
        return ranking

    def model_rows(self):
        with self.lock:
            rows=[]
            for r in self._ranking():
                model_key=r['id']+'_'+str(r['tf'])
                exp=EXPERIMENTS[r['id']]
                rows.append({
                    'model_key':model_key,'experiment_id':r['id'],'timeframe':r['tf'],
                    'name':exp['name'],'version':exp['version'],
                    'status':r['status'],'active':bool(r['active']),
                    'total':r['signals'],'wins':r['wins'],
                    'validation_n':r['validation_signals'],
                    'validation_wins':r['validation_wins'],
                    'validation_lower_95':r['validation_lower_95'],
                    'rules':{'thresholds':{'min_total':80,'min_validation':30,
                              'min_oos_win_rate':.68,'min_total_win_rate':.60,
                              'min_wilson_lower_95':.556},
                             'rule':exp['description']},
                    'reason':'Seleção automática de pesquisa, sinais simulados; sem execução de ordens.'})
            return rows

    def promoted_candidates(self,bars,tf,now):
        if tf not in (60,300) or not bars:return []
        if not 0<=now-(bars[-1]['from']+tf)<=10:return []
        with self.lock:
            if not self.enabled:return []
            approved={x['id']:x for x in self._ranking() if x['tf']==tf and x['active']}
        if not approved:return []
        found=[]
        for result in candidates(bars):
            rank=approved.get(result['key'])
            if not rank:continue
            # The live signal still passes the independent preflight, asset
            # open/rechecked, one-signal-per-time gate and manual execution.
            score=min(5.5,4.0+8*(rank['validation_rate']-.6))
            found.append({'strategy':'research_'+result['key'],
                'name':result['name']+' '+result['version'],
                'direction':result['direction'],
                'reason':result['reason'],
                'strengths':['Critérios de padrão fechado cumpridos',
                    'Validação em resultados posteriores com limites mínimos'],
                'risks':['Resultados de pesquisa, não operações reais',
                    'Padrão pode perder consistência e será automaticamente pausado'],
                'confirmations':[result['name']],
                'research_validation':{'total':rank['signals'],
                    'oos_total':rank['validation_signals'],
                    'oos_rate':round(rank['validation_rate'],4),
                    'wilson_lower_95':round(rank['validation_lower_95'],4)},
                'score':round(score,3),
                'strategy_version':result['version'],
                'selection':'Laboratório validado prospectivamente; sempre sujeito a filtro pré-entrada'})
        return found

    # User-requested research hypotheses, allowed only as lower-priority
    # read-only SIGNAL candidates during supervised testing. This does not
    # modify the independently validated "PROMISSORA" approval flag.
    PILOT_KEYS=frozenset({'wick_reversal','three_step','impulse_follow','pullback_resume'})

    def pilot_list(self):
        with self.lock:
            ranking=self._ranking()
            # A minimum set of independently timestamped results limits
            # tiny-sample W streaks. M1/M5 remain distinct.
            return [
                {'key':r['id'],'name':r['name'],'tf':r['tf'],
                 'samples':r['signals'],'rate':r['rate'],
                 'status':r['status']}
                for r in ranking
                if r['id'] in self.PILOT_KEYS
                and r['tf'] in (60,300)
                and r['signals']>=20
                and r['rate'] is not None and r['rate']>=.50
                and (r['recent_rate'] is None or r['recent_rate']>=.45)
                and r['status'] not in ('REPROVADA','PAUSADA')
                and self._latest_result_at(r['id'],r['tf'])>=__import__('time').time()-86400
            ]

    def _latest_result_at(self,key,tf):
        return max((x['entry_at'] for x in self.ledger
                    if x.get('key')==key and x.get('tf')==tf and
                    x.get('result') in ('WIN','LOSS') and
                    x.get('clock_guard')=='v2_future_entry'),default=0)

    def pilot_candidates(self,bars,tf,now):
        """Optional user-requested M1/M5 pilot; NEVER auto-place an order.
        These hypotheses remain in validation, not in the approved registry.
        """
        if tf not in (60,300) or not bars or not 0<=now-(bars[-1]['from']+tf)<=10:
            return []
        with self.lock:
            if not self.enabled:return []
            allowed={r['key']:r for r in self.pilot_list() if r['tf']==tf}
        if not allowed:return []
        out=[]
        for raw in candidates(bars):
            record=allowed.get(raw['key'])
            if not record:continue
            out.append({'strategy':'research_'+raw['key'],
                'name':raw['name']+' '+raw['version']+' · TESTE',
                'direction':raw['direction'],'reason':raw['reason'],
                'strengths':['Padrão confirmado em vela fechada',
                    'Incluída a pedido para testes no motor de sinais'],
                'risks':['Estratégia ainda EM VALIDAÇÃO; não possui aprovação estatística',
                    'O resultado virtual não representa uma ordem enviada à Bulex'],
                'confirmations':[raw['name']],
                'research_validation':{'total':record['samples'],
                    'rate':round(record['rate'],4),
                    'status':record['status']},
                'score':2.9,'pilot':True,
                'strategy_version':raw['version'],
                'selection':'Candidata experimental M'+str(tf//60)+' no motor de sinais; sem ordens automáticas'})
        return out

    def report_error(self,exc):
        with self.lock:
            self.errors+=1
            # Do not leak broker credentials, account information, or error internals.
            self.last_error=type(exc).__name__

    def export(self):
        with self.lock:
            return {'schema_version':'research_v2_future_entry',
                    'exported_at':__import__('time').time(),
                    'history':list(self.ledger),
                    'pending':list(self.pending.values()),
                    'anomalies':list(self.anomalies),
                    'note':'Resultados virtuais, não são operações executadas. Arquivo completo do laboratório, sem tokens de sessão.'}

    def snapshot(self):
        with self.lock:
            all_rows=list(self.ledger)
            ranking=self._ranking()
            valid=[x for x in all_rows if x['result'] in ('WIN','LOSS')]
            unique={(x['asset'],x['tf'],x['entry_at'],x['direction']) for x in valid}
            delayed=sum(x.get('issued_at',0)>=x['entry_at'] for x in all_rows)
            return {'enabled':self.enabled,'scans':self.scans,'last_scan':self.last_scan,
                    'schema_version':'research_v2_future_entry',
                    'ranking':ranking,'pending':len(self.pending),
                    'settled':len(self.ledger),'unique_opportunities':len(unique),
                    'hypothesis_outcomes':len(valid),'duplicate_hypotheses':len(valid)-len(unique),
                    'invalid_timing':delayed,'rejected_late':self.rejected_late,
                    'errors':self.errors,'last_error':self.last_error,
                    'storage_status':self.store_status,
                    'storage_error':self.storage_error,
                    'pending_writes':len(self.dirty),
                    'persisted_records':self.persisted_records,
                    'promoted_count':sum(x['active'] for x in ranking),
                    'anomalies':list(self.anomalies)[-30:][::-1],
                    'recent':list(self.ledger)[-50:][::-1],
                    'note':'Pesquisa virtual prospectiva, intervalo mínimo de antecedência e validação futura. Estratégias PROMISSORAS entram no motor de escolha de sinais, nunca em ordens automáticas. Estratégias REPROVADAS não participam. O Supabase preserva resultados quando conectado.'}
