"""Chronological out-of-sample PAPER validation for TriangleBreakout.

No future candles in signal engine, no trades based solely on simulated results.
Expiry shorter than candle period cannot be settled from OHLC (requires raw ticks).
Entry modeled at NEXT bar open, expiry at close of last elapsed bar. The test is
not a broker fill or spread/slippage guarantee. Require separate actual DEMO
execution results before considering any automatic production activation.
"""
from collections import defaultdict
from datetime import datetime,timezone
from triangle_breakout import TriangleBreakout


def walkforward(candles,symbol,period,expiry,payout,style='both',
                use_adx=False,use_ema=False,margin=.22):
    base={'symbol':symbol,'timeframe':period,'expiry':expiry,
          'payout':payout,'status':'BLOQUEADO','approved':False,
          'reason':'Aguardando dados OHLC reais suficientes, fora da amostra',
          'train':{'trades':0,'wins':0,'losses':0,'net':0.,'win_rate':None},
          'test':{'trades':0,'wins':0,'losses':0,'net':0.,'win_rate':None},
          'by_hour':{},'mode':'PAPER_SIMULADO_SEM_EXECUCAO'}
    if (period not in (5,60,120,300) or
        expiry not in (3,5,60,120,180,300) or
        expiry<period or expiry%period or len(candles)<250):
        base['reason']='Sem candles suficientes (mín. 250) ou expiração não mensurável por OHLC'
        return base
    if any(candles[i]['t']-candles[i-1]['t']!=period for i in range(1,len(candles))):
        base['reason']='Lacuna entre candles: recusar backtest'
        return base
    engine=TriangleBreakout(period,style,use_adx,use_ema,margin)
    n=len(candles);cut=int(n*.7);bars_ahead=expiry//period
    trades=[]
    next_free=0
    for i,bar in enumerate(candles):
        engine.bars.append(dict(bar))
        # Start indicators only once the REQUIRED warmup has fully closed;
        # never use candle i+1 while computing the signal at candle i.
        direction=engine.evaluate(bar['t']+period) if i>=engine.warmup_bars-1 else None
        if direction not in ('call','put') or i<next_free:
            continue
        if i+bars_ahead>=n:continue
        entry=candles[i+1]['open']
        settled=candles[i+bars_ahead]['close']
        # Equal close is conservative LOSS in simulated binary outcome.
        win=(settled>entry) if direction=='call' else (settled<entry)
        net=(payout/100) if win else -1.
        hour=datetime.fromtimestamp(bar['t'],timezone.utc).strftime('%H:00 UTC')
        trades.append({'i':i,'win':win,'net':net,'hour':hour})
        next_free=i+bars_ahead+1
    def summarize(rows):
        n=len(rows);w=sum(t['win'] for t in rows)
        return {'trades':n,'wins':w,'losses':n-w,
                'net':round(sum(t['net'] for t in rows),4),
                'win_rate':round(100*w/n,2) if n else None}
    train=[t for t in trades if t['i']<cut]
    test=[t for t in trades if t['i']>=cut]
    base['train']=summarize(train)
    base['test']=summarize(test)
    hours=defaultdict(list)
    for t in trades:hours[t['hour']].append(t)
    base['by_hour']={h:summarize(v) for h,v in hours.items()}
    # Strict holdout, representative sample and positive payout-adjusted
    # performance. These are *paper* statistics, not demo execution proof.
    if len(train)<60 or len(test)<25:
        base['reason']='Amostra insuficiente: exige pelo menos 60 sinais treino e 25 fora da amostra'
    elif base['train']['net']<=0 or base['test']['net']<=0:
        base['reason']='Backtest sem retorno líquido positivo em treino e validação'
    else:
        base['status']='PAPER_APROVADO'
        base['reason']='Backtest de papel positivo; falta validação real de execução DEMO, spread e latência'
        # approved remains false because synthetic OHLC cannot validate
        # broker order acceptance/actual entry and expiry settlement.
    return base
