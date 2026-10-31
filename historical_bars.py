"""Broker-sourced history validation for DEMO ZigZag, no invented OHLC.

Historical broker data is for indicator context ONLY. Importing historical
bars can never create a trading signal; the next live, completed candle must
trigger any BUY/SELL. Reject missing/future/ambiguous or sparse bars.
"""
import math
from collections import defaultdict


def number(value):
    if isinstance(value,bool):
        return None
    try:
        value=float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def timestamp(value):
    t=number(value)
    if t is None or t<=0:
        return None
    return t/1000 if t>1e12 else t


def _closed_ohlc(rows,period,current_start):
    output=[]
    for item in rows:
        if not isinstance(item,dict):
            continue
        t=timestamp(item.get('time',item.get('t')))
        if t is None or int(t)%period:
            continue
        t=int(t)
        if t>=current_start or t<current_start-90*period:
            continue
        values={name:number(item.get(name)) for name in ('open','high','low','close')}
        if any(v is None or v<=0 for v in values.values()):
            continue
        if (values['high']<max(values['open'],values['close']) or
            values['low']>min(values['open'],values['close']) or
            values['high']<values['low']):
            continue
        output.append({'t':t,**values})
    return output


def _closed_ticks(rows,period,current_start):
    grouped=defaultdict(list)
    for item in rows:
        if isinstance(item,dict):
            t=timestamp(item.get('time',item.get('t')))
            p=number(item.get('price'))
        elif isinstance(item,(list,tuple)) and len(item)>=2:
            t=timestamp(item[0])
            p=number(item[1])
        else:
            continue
        if t is None or p is None or p<=0:
            continue
        s=int(t)
        start=s//period*period
        if current_start-90*period<=start<current_start:
            grouped[start].append((t,p))
    output=[]
    for start,ticks in sorted(grouped.items()):
        ticks=sorted(ticks)
        seconds={int(t) for t,_ in ticks}
        first=min(seconds)-start
        last=max(seconds)-start
        if period==120:
            enough=(len(seconds)>=28 and first<=10 and last>=110 and last-first>=105)
        elif period==60:
            enough=(len(seconds)>=18 and first<=5 and last>=53)
        else:
            enough=(len(seconds)>=2 and first<=2 and last>=3 and last-first>=2)
        if not enough:
            continue
        prices=[p for _,p in ticks]
        output.append({'t':start,'open':prices[0],'high':max(prices),
                       'low':min(prices),'close':prices[-1]})
    return output


def extract_closed_history(raw,period,anchor,maxbars=90):
    """Return last contiguous closed history from genuine broker packet rows.

    anchor is the last independently received verified *live broker* timestamp;
    do not accept future candles or stale history without it.
    """
    if period not in (5,60,120) or isinstance(raw,(str,bytes,dict)) or not isinstance(raw,(list,tuple)):
        return []
    anchor=timestamp(anchor)
    if anchor is None:
        return []
    start=int(anchor)//period*period
    if not raw:
        return []
    if any(isinstance(x,dict) and all(k in x for k in ('open','high','low','close')) for x in raw):
        parsed=_closed_ohlc(raw,period,start)
    else:
        parsed=_closed_ticks(raw,period,start)
    by_time={b['t']:b for b in parsed}
    suffix=[]
    for t in sorted(by_time,reverse=True):
        if not suffix or suffix[-1]['t']-t==period:
            suffix.append(by_time[t])
        else:
            break
    return list(reversed(suffix[:maxbars]))


def merge_historical_bars(engine,history,anchor):
    """Seed indicator context from closed bars only, never call evaluate().

    The forming live candle stays unchanged. The next real tick closes it.
    """
    if not history or not hasattr(engine,'collector'):
        return 0
    period=getattr(engine,'bar_seconds',60)
    anchor=timestamp(anchor)
    if anchor is None:
        return 0
    current_start=int(anchor)//period*period
    existing=list(engine.bars)
    candidate={b['t']:b for b in history if b['t']<current_start}
    for b in existing:
        if b['t']<current_start:
            candidate[b['t']]=b
    end=current_start-period
    # If recent history stops earlier, it can only help if a contiguous live
    # history already joins it all the way to the latest CLOSED candle.
    if end not in candidate:
        return 0
    continuous=[]
    for t in range(end,end-300*period,-period):
        if t not in candidate:
            break
        continuous.append(candidate[t])
    continuous.reverse()
    if len(continuous)<=len(existing):
        return 0
    engine.bars.clear()
    engine.bars.extend(continuous)
    engine.collector.completed_bars=max(engine.collector.completed_bars,len(continuous))
    engine.direction=None
    engine.signal_at=0
    engine.strength=None
    engine.reason=('Histórico real da corretora validado: %d candles de %s; '
                   'aguardando NOVO fechamento para emitir sinal'%
                   (len(continuous),{5:'5s',60:'M1',120:'M2'}[period]))
    return len(continuous)
