"""Research-only multiasset Xtreme strategy scanner, separate from live order engine.

Uses historical CLOSED M1/M5 candles. "Approved >50%" means shortlisted for
paper signals only. Neither 50% candle direction nor a backtest guarantees
profit: with an 80% payout, break-even is ~55.56% before further costs.
"""
import math
import threading
import time
from collections import deque
from sniper_lab40 import (
    CANDIDATES, evaluate, WARMUP, _sma, _wma5, _trail, _pattern
)
from strategy import sniper_buffers

MIN_SAMPLES = 30
DISPLAY_THRESHOLD = 50.0
MIN_PAYOUT_EXCLUSIVE = 80.0
MAX_ASSETS = 180
MAX_RECENT_SIGNALS = 35


def aggregate_m5(closed_m1):
    """Only truly completed and contiguous groups of five M1 candles count."""
    buckets = {}
    for bar in closed_m1:
        t = int(bar['from'])
        buckets.setdefault(t // 300 * 300, []).append(bar)
    out = []
    for t, group in sorted(buckets.items()):
        group = sorted(group, key=lambda b: int(b['from']))
        if len(group) != 5 or [int(b['from']) for b in group] != [t + k*60 for k in range(5)]:
            continue
        out.append({
            'from': t, 'open': group[0]['open'], 'close': group[-1]['close'],
            'max': max(float(b['max']) for b in group),
            'min': min(float(b['min']) for b in group),
        })
    return out


def latest_direction(bars, spec):
    """Generate a signal only from the most recent CLOSED candle.

    Does not shift back by -1 used solely for visual plotting in the Lua file.
    """
    if len(bars) < WARMUP + 1:
        return None
    i = len(bars) - 1
    pos = _trail(bars)
    if spec.get('principal'):
        fast, slow = sniper_buffers(bars, 'hl2')
        if len(fast) < 2:
            return None
        sign = 1 if fast[-1] > slow[-1] and fast[-2] < slow[-2] else -1 if fast[-1] < slow[-1] and fast[-2] > slow[-2] else 0
        return ('call' if sign == 1 else 'put') if sign and pos[i] == sign else None
    source = spec['source']
    prices = [(b['max']+b['min'])/2 if source == 'hl2' else b['close'] for b in bars]
    sm34 = _sma(prices, 34)
    fast = [prices[j] - sm34[j] if sm34[j] is not None else None for j in range(len(bars))]
    slow = _wma5(fast)
    sign = 1 if fast[i] > slow[i] else -1 if fast[i] < slow[i] else 0
    if not sign:
        return None
    if spec['confirmation'] == 'recent':
        if not any(
            fast[j] is not None and slow[j] is not None and
            fast[j-1] is not None and slow[j-1] is not None and
            sign * (fast[j]-slow[j]) > 0 >= sign * (fast[j-1]-slow[j-1])
            for j in range(max(40,i-3),i+1)
        ):
            return None
    if spec['trend'] == 'atr18':
        if pos[i] != sign:
            return None
    elif sign * (bars[i]['close'] - _sma([b['close'] for b in bars],34)[i]) <= 0:
        return None
    direction = 'call' if sign == 1 else 'put'
    if not _pattern(spec['pattern'],bars,i,direction,_sma([b['close'] for b in bars],34)[i]):
        return None
    return direction


def shortlist(outcome, payout, now=None):
    """Generate informational, non-executable candidates from OOS tests."""
    if not isinstance(outcome, dict) or not isinstance(payout,(float,int)) or not math.isfinite(payout) or payout <= MIN_PAYOUT_EXCLUSIVE:
        return []
    seconds = 60 if outcome.get('timeframe') == 'M1' else 300
    if outcome.get('timeframe') not in ('M1','M5'):
        return []
    rows = [outcome.get('primary')] + list(outcome.get('strategies',[]))
    chosen = []
    for row in rows:
        if not isinstance(row,dict):
            continue
        n = int(row.get('samples',0))
        wins = int(row.get('wins',0))
        losses = int(row.get('losses',0))
        if n < MIN_SAMPLES or n != wins+losses or not 100*wins > n*DISPLAY_THRESHOLD:
            continue
        rate = wins/n*100
        net = (rate/100)*(payout/100) - (1-rate/100)
        chosen.append({
            'id':row['id'],'name':row['name'],'principal':bool(row.get('principal')),
            'asset':outcome['asset'],'timeframe':outcome['timeframe'],'samples':n,
            'wins':wins,'losses':losses,'accuracy':round(rate,2),
            'payout_m1':round(float(payout),1),
            'expected_net_per_unit_if_payout_matches':round(net,4),
            'passes_break_even_math':net>0,
            'status':'ESTUDO_CANDIDATO_NAO_EXECUTAVEL',
            'time':int(outcome['to']+seconds),
        })
    return sorted(chosen,key=lambda x:(-x['accuracy'],-x['samples']))[:25]


class ResearchRegistry:
    def __init__(self):
        self.lock=threading.RLock()
        self.market={}
        self.market_at=0
        self.records={}
        self.last_bars={}
        self.seen={}
        self.events=deque(maxlen=MAX_RECENT_SIGNALS)
        self.running=True
        self.error=None
        self.updated=0
        self.published=0

    def set_market(self, candidates):
        now=time.time()
        if not isinstance(candidates,list):
            return
        eligible={str(a['asset']):float(a['payout'])
             for a in candidates if isinstance(a,dict) and isinstance(a.get('asset'),str)
             and isinstance(a.get('payout'),(int,float)) and
             math.isfinite(a['payout']) and a['payout']>MIN_PAYOUT_EXCLUSIVE and a.get('open',True)}
        with self.lock:
            self.market=dict(list(eligible.items())[:MAX_ASSETS])
            self.market_at=now
            for key in list(self.records):
                if key[0] not in self.market:
                    self.records.pop(key,None)
            self.error=None

    def ingest(self, asset, timeframe, bars, source='stream'):
        if timeframe not in ('M1','M5'):
            raise ValueError('Período de estudo inválido')
        key=(asset,timeframe)
        with self.lock:
            if asset not in self.market:
                return False
            payout=self.market[asset]
            previous=self.records.get(key)
            last=previous['to'] if previous else None
        merged=self._merge(self.last_bars.get(key,[]),bars,timeframe) if bars else []
        if not merged:
            return False
        t=merged[-1]['from']
        if last is not None and t<=last:
            return False
        step=60 if timeframe=='M1' else 300
        # Strict validation and honest "insufficient sample" states.
        if len(merged)<WARMUP+2:
            outcome=None
        else:
            try:
                outcome=evaluate(merged,asset,timeframe=timeframe)
            except ValueError:
                outcome=None
        candidate_rows=shortlist(outcome,payout) if outcome else []
        signal=[]
        if outcome and candidate_rows:
            lookups={c['id']:c for c in [outcome['primary'],*outcome['strategies']]}
            for c in candidate_rows:
                direction=latest_direction(merged,lookups[c['id']])
                if direction:
                    signal.append({**c,'direction':direction,
                      'candle_close':int(t+step),'signal_status':'SINAL_PARA_ACOMPANHAMENTO',
                      'timeframe_payout_verified':timeframe=='M1'})
        with self.lock:
            if asset not in self.market or self.market[asset]!=payout:
                return False
            self.last_bars[key]=merged
            self.records[key]={'asset':asset,'timeframe':timeframe,'bars':len(merged),
                               'to':t,'source':source,'payout_m1':payout,
                               'updated':time.time(),'status':'ANALISADO' if outcome else 'AMOSTRA_INSUFICIENTE',
                               'results':outcome,'shortlist':candidate_rows}
            self.updated=time.time()
            self.published+=1
            for one in signal:
                unique=(one['asset'],one['timeframe'],one['id'],one['candle_close'])
                if unique in self.seen:
                    continue
                self.seen[unique]=time.time()
                self.events.appendleft(one)
            if len(self.seen)>600:
                expire=time.time()-3600
                self.seen={k:v for k,v in self.seen.items() if v>expire}
        return True

    def snapshot(self):
        with self.lock:
            records=list(self.records.values())
            shortlist_rows=[s for r in records for s in r.get('shortlist',[])]
            shortlist_rows=sorted(shortlist_rows,key=lambda x:(-x['accuracy'],-x['samples']))[:65]
            return {
                'enabled':self.running,'source':'BULLEX_PRACTICE_HISTORICAL_CANDLES',
                'mode':'RESEARCH_ONLY','threshold':DISPLAY_THRESHOLD,
                'min_validation':MIN_SAMPLES,'minimum_payout_exclusive':MIN_PAYOUT_EXCLUSIVE,
                'asset_count':len(self.market),'researched_assets':len(set(r['asset'] for r in records)),
                'studies':len(records),'updated':self.updated,'market_at':self.market_at,
                'ready_by_timeframe':{tf:sum(r['timeframe']==tf and r['status']=='ANALISADO' for r in records) for tf in ('M1','M5')},
                'candidates':shortlist_rows,'signals':list(self.events)[:25],
                'break_even_accuracy_at_80_payout':round(100/1.8,2),
                'm5_execution_supported':False,'parallel_orders_supported':False,
                'status':self.error or ('ANALISANDO' if records else 'AGUARDANDO_VELAS'),
                'catalog': [{'asset':a,'payout_m1':p} for a,p in list(self.market.items())[:90]],
            }


def is_closed_m1(bars,now):
    return [b for b in bars if isinstance(b,dict) and isinstance(b.get('from'),(int,float)) and b['from']+60<=now]
