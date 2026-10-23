"""Independent APEX-inspired confluence. Not proprietary APEX logic or true order flow."""
from math import isfinite
def ema(seq,n):
    v=seq[0];out=[]
    for x in seq:
        v+=2/(n+1)*(x-v);out.append(v)
    return out
def rsi(seq,n=14):
    changes=[seq[i]-seq[i-1] for i in range(1,len(seq))]
    if len(changes)<n+1:return 50
    gains=sum(max(0,x) for x in changes[:n])/n
    losses=sum(max(0,-x) for x in changes[:n])/n
    for x in changes[n:]:
        gains=(gains*(n-1)+max(0,x))/n
        losses=(losses*(n-1)+max(0,-x))/n
    return 100 if losses==0 and gains>0 else 50 if gains==losses==0 else 100-100/(1+gains/losses)
def decision(bars):
    # bars are chronological, closed and checked by engine.normalized.
    if len(bars)<55 or any(y['t']-x['t']!=60 for x,y in zip(bars[-55:],bars[-54:])):return 0
    a=bars[-55:];close=[x['c'] for x in a];fast=ema(close,9);slow=ema(close,21)
    curr=a[-1];prev=a[-2];span=curr['h']-curr['l']
    if span<=0:return 0
    body=abs(curr['c']-curr['o'])/span
    # Candle pressure proxy, not broker order-book/order-flow data.
    pressure=(curr['c']-curr['o'])/span
    recent_hi=max(x['h'] for x in a[-21:-1])
    recent_lo=min(x['l'] for x in a[-21:-1])
    momentum=rsi(close)
    if fast[-1]>slow[-1] and fast[-1]>fast[-2] and 53<=momentum<=72 and pressure>=.48 and body>=.48 and curr['c']>prev['c'] and curr['c']<recent_hi:return 1
    if fast[-1]<slow[-1] and fast[-1]<fast[-2] and 28<=momentum<=47 and pressure<=-.48 and body>=.48 and curr['c']<prev['c'] and curr['c']>recent_lo:return -1
    return 0
