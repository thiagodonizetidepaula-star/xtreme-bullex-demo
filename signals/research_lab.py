"""Forward-only Pulse research lab. No training on outcome candles, no broker orders.

Hypotheses are deterministic, named research templates; this is not a generative
AI or proof of a broker manipulating quotes. Only the following candle settles
the research prediction. Ranking is based solely on observed forward outcomes.
"""
from collections import deque
from math import isfinite
from statistics import median
from threading import RLock
from datetime import datetime, timezone

EXPERIMENTS = {
    "impulse_follow": {"name":"Pulso Direcional","version":"v1","description":"Corpo forte alinhado ao avanço de fechamentos; testa continuidade"},
    "wick_reversal": {"name":"Rejeição de Extremo","version":"v1","description":"Pavio dominante após avanço prévio; testa reversão"},
    "compression_break": {"name":"Ruptura da Compressão","version":"v1","description":"Faixa estreita seguida de expansão e fechamento direcional"},
    "three_step": {"name":"Ritmo Três Velas","version":"v1","description":"Duas velas direcionais com confirmação de momentum"},
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
    def observe(self,asset,tf,bars,now):
        """Observe closed bars ONLY. A prediction for t+tf is settled on later reads."""
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
                if candle:
                    delta=candle['close']-candle['open']
                    record['result']='EMPATE' if delta==0 else ('WIN' if (delta>0)==(record['direction']=='ALTA') else 'LOSS')
                    record['entry_price']=candle['open']
                    record['exit_price']=candle['close']
                    record['settled_at']=now
                    self.ledger.append(record)
                    del self.pending[k]
                elif now>record['entry_at']+tf*2:
                    record['result']='SEM DADOS'
                    record['settled_at']=now
                    self.ledger.append(record)
                    del self.pending[k]
            candle_id=(asset,tf,latest['from'])
            if candle_id in self.seen:return
            self.seen.add(candle_id)
            if len(self.seen)>12000:self.seen=set(list(self.seen)[-6000:])
            self._anomaly(asset,tf,bars,now)
            for found in candidates(bars):
                entry=latest['from']+tf
                k=(asset,tf,entry,found['key'])
                if k in self.pending:continue
                self.pending[k]={**found,'asset':asset,'tf':tf,'basis_at':latest['from'],
                                 'entry_at':entry,'expires_at':entry+tf,'issued_at':now,
                                 'result':'PENDENTE'}
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
            self.anomalies.append({'asset':asset,'tf':tf,'at':b['from']+tf,'event':flag,
                                   'interpretation':'Anomalia estatística, não prova de manipulação'})
        if len(self.anomaly_seen)>2500:self.anomaly_seen=set(list(self.anomaly_seen)[-1000:])
    def snapshot(self):
        with self.lock:
            all_rows=list(self.ledger)
            ranking=[]
            for key,exp in EXPERIMENTS.items():
                for tf in (60,300):
                    rows=[x for x in all_rows if x['key']==key and x['tf']==tf and x['result'] in ('WIN','LOSS')]
                    n=len(rows);w=sum(x['result']=='WIN' for x in rows)
                    # Deterministic time split; validation uses later forward predictions.
                    ordered=sorted(rows,key=lambda x:(x['entry_at'],x['asset']))
                    split=max(1,int(len(ordered)*.6))
                    validation=ordered[split:]
                    v_n=len(validation)
                    v_win=sum(x['result']=='WIN' for x in validation)
                    v_rate=v_win/v_n if v_n else None
                    rate=w/n if n else None
                    if n<30 or v_n<12:status='EM DESCOBERTA' if n<12 else 'EM VALIDAÇÃO'
                    elif v_rate>=.62 and (rate is not None and rate>=.58):status='PROMISSORA'
                    elif v_rate<.48:status='REPROVADA'
                    else:status='EM VALIDAÇÃO'
                    ranking.append({'id':key,'name':exp['name']+' '+exp['version'],'description':exp['description'],
                                    'tf':tf,'signals':n,'wins':w,'losses':n-w,'rate':rate,
                                    'validation_signals':v_n,'validation_wins':v_win,
                                    'validation_rate':v_rate,'status':status})
            ranking.sort(key=lambda r:(r['status']!='PROMISSORA',-(r['validation_rate'] or 0),-r['signals'],r['name']))
            return {'enabled':self.enabled,'scans':self.scans,'last_scan':self.last_scan,
                    'ranking':ranking,'pending':len(self.pending),
                    'settled':len(self.ledger),'anomalies':list(self.anomalies)[-30:][::-1],
                    'recent':list(self.ledger)[-50:][::-1],
                    'note':'Pesquisa de hipóteses pré-definidas, somente na memória deste processo. Resultados não são lucros, não atestam manipulação e se perdem no reinício do servidor.'}
