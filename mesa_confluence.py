"""Optional Xtreme confluence, closed M1 candles only (no price lookahead).

These candidate filters are experimental, not a proven increase in win rate:
CALL: RSI14 50..70; Bollinger20 close above mid and strictly below upper.
PUT: RSI14 30..50; Bollinger20 close below mid and strictly above lower.
Each filter can be independently switched off to measure its effect.
"""
import math

def _closes(candles):
    closes=[]
    for b in candles:
        o,h,l,c=(float(b[k]) for k in ("open","max","min","close"))
        if not all(math.isfinite(v) and v>0 for v in (o,h,l,c)):
            raise ValueError("OHLC não numérico")
        if l>min(o,c) or h<max(o,c):raise ValueError("OHLC incompatível")
        closes.append(c)
    return closes

def rsi_wilder(closes,period=14):
    if len(closes)<period+1:raise ValueError("Histórico insuficiente para RSI")
    diffs=[closes[i]-closes[i-1] for i in range(1,len(closes))]
    gain=sum(max(v,0) for v in diffs[:period])/period
    loss=sum(max(-v,0) for v in diffs[:period])/period
    for delta in diffs[period:]:
        gain=(gain*(period-1)+max(delta,0))/period
        loss=(loss*(period-1)+max(-delta,0))/period
    if loss==0:return 100.0 if gain>0 else 50.0
    if gain==0:return 0.0
    rs=gain/loss
    return 100-100/(1+rs)

def bollinger(closes,period=20,deviations=2.0):
    if len(closes)<period:raise ValueError("Histórico insuficiente para Bollinger")
    tail=closes[-period:]
    middle=sum(tail)/period
    sd=math.sqrt(sum((x-middle)**2 for x in tail)/period)
    return {'middle':middle,'upper':middle+deviations*sd,
            'lower':middle-deviations*sd,'width':4*sd}

def evaluate_confluence(candles,direction,enable_rsi=True,enable_bollinger=True):
    """Use only caller-supplied CLOSED candles (from broker M1 snapshot).

    Evaluated ONLY after Sniper + Xtreme Tendência confirms a direction.
    No retuning/threshold optimization is performed on historical test trades.
    """
    if direction not in ('call','put'):raise ValueError("Direção inválida")
    closes=_closes(candles)
    rsi=rsi_wilder(closes)
    bb=bollinger(closes)
    close=closes[-1]
    rsi_ok=(50<=rsi<=70) if direction=='call' else (30<=rsi<=50)
    bb_ok=(bb['middle']<close<bb['upper']) if direction=='call' else (bb['lower']<close<bb['middle'])
    checks={'rsi14':{'enabled':enable_rsi,'passed':rsi_ok,'value':round(rsi,3)},
            'bollinger20':{'enabled':enable_bollinger,'passed':bb_ok,
                           'middle':bb['middle'],'upper':bb['upper'],
                           'lower':bb['lower'],'close':close}}
    failures=[]
    if enable_rsi and not rsi_ok:failures.append('RSI fora da faixa direcional')
    if enable_bollinger and not bb_ok:failures.append('Bollinger sem confirmação ou junto à banda contrária')
    return {'passed':not failures,'reason':' | '.join(failures) if failures else 'RSI/Bollinger alinhados',
            'direction':direction,'rsi14':round(rsi,3),
            'bb20_upper':bb['upper'],'bb20_middle':bb['middle'],
            'bb20_lower':bb['lower'],'checks':checks,
            'filters':{'rsi':enable_rsi,'bollinger':enable_bollinger}}

