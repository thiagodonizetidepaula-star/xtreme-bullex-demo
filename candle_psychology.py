"""Conservative candle-psychology filter for real CLOSED 5-second bars.

The measures describe OHLC patterns; they do not predict win probability.
No data synthesis, repaint, current-forming candle, or look-ahead.
"""
import math
from statistics import median

WINDOW=12

def candle_psychology(bars,direction):
    """Return whether a completed-bar BUY/SELL setup passes candle quality."""
    info={'ready':False,'reason':'Velas insuficientes para contar força compradora/vendedora',
          'direction':direction, 'same_color_3':0, 'body_pct':0.,
          'efficiency':0.,'spread_ratio':0.}
    if direction not in ('call','put') or len(bars)<WINDOW:
        return info
    recent=bars[-WINDOW:]
    for b in recent:
        if not isinstance(b,dict):
            info['reason']='Formato de vela inválido';return info
        vals=[b.get(k) for k in ('open','high','low','close')]
        if any(isinstance(v,bool) or not isinstance(v,(int,float))
               or not math.isfinite(v) or v<=0 for v in vals):
            info['reason']='OHLC de vela incompleto ou não confiável';return info
        o,h,l,c=vals
        if l>min(o,c) or h<max(o,c) or h<=l:
            info['reason']='OHLC de vela inconsistente';return info
    latest=recent[-1]
    o,h,l,c=(latest[k] for k in ('open','high','low','close'))
    length=h-l
    body=abs(c-o)
    bullish=direction=='call'
    aligned=(c>o if bullish else c<o)
    body_ratio=body/length
    contra_wick=((min(o,c)-l) if bullish else (h-max(o,c)))/length
    close_to_extreme=((h-c) if bullish else (c-l))/length
    count=sum((b['close']>b['open']) if bullish else (b['close']<b['open'])
              for b in recent[-3:])
    # A fresh breakout may reverse an older trend; only last three candles
    # are counted, not the entire down/up leg.
    ranges=[b['high']-b['low'] for b in recent[:-1]]
    normal=median(ranges)
    span=max(b['high'] for b in recent[-10:])-min(b['low'] for b in recent[-10:])
    spread_ratio=span/normal if normal>0 else 0.
    last_closes=[b['close'] for b in recent[-7:]]
    travel=sum(abs(b-a) for a,b in zip(last_closes,last_closes[1:]))
    efficiency=abs(last_closes[-1]-last_closes[0])/travel if travel>0 else 0.
    baseline=median(abs(b['close']-b['open']) for b in recent[:-1])
    info.update(same_color_3=count,body_pct=round(100*body_ratio,1),
                efficiency=round(efficiency,3),spread_ratio=round(spread_ratio,2),
                opposite_wick_pct=round(100*contra_wick,1),
                close_extreme_pct=round(100*close_to_extreme,1),
                candle_range_ratio=round(length/normal,2) if normal else 0.)
    if not aligned:
        info['reason']='Cor contrária à direção da entrada; sem confirmação';return info
    if body_ratio<0.60 or close_to_extreme>0.24 or contra_wick>0.26:
        info['reason']='Candle indeciso / doji / pavio contrário grande: NÃO OPERAR';return info
    if count<2:
        info['reason']='Contagem de cores: menos de 2 das últimas 3 velas na direção';return info
    if body<max(1e-12,baseline*1.10):
        info['reason']='Candle sem força: corpo menor que os anteriores';return info
    if normal<=0 or span<2.50*normal or efficiency<0.29:
        info['reason']='Mercado lateralizado/alternando candles: NÃO OPERAR';return info
    if length<0.78*normal:
        info['reason']='Vela pequena e sem expansão suficiente para confirmar rompimento';return info
    if length>3.25*normal:
        info['reason']='Vela esticada/exaustão: evitar entrada atrasada';return info
    info['ready']=True
    info['reason']='Força confirmada: corpo amplo, pouca sombra, cores 2/3 e movimento direcional'
    return info
