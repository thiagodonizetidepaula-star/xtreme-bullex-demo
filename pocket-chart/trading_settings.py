"""Validated demo execution preferences; not an order execution adapter."""
import math
DEFAULTS={'amount':1.0,'expiry':60,'max_concurrent':1,'martingale':False,'multiplier':2.0,'max_steps':1,'stop_loss':20.0,'stop_win':20.0}
def validate(data):
    out={}
    for key,lo,hi in [('amount',.01,100000),('expiry',3,86400),('max_concurrent',1,10),('multiplier',1.01,3),('max_steps',1,5),('stop_loss',.01,1000000),('stop_win',.01,1000000)]:
        value=data.get(key,DEFAULTS[key])
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError(key)
        if key in ('expiry','max_concurrent','max_steps') and type(value) is not int:raise ValueError(key)
        out[key]=value
    if type(data.get('martingale',False)) is not bool:raise ValueError('martingale')
    out['martingale']=data.get('martingale',False)
    return out
