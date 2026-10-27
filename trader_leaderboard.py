"""PRACTICE-only trader leaderboard based on broker-confirmed closed orders.

Historical research accuracy and ignored/unconfirmed orders are NOT wins.
On Render's current stateless service, records span only the current worker
session; data persistence is a separate future feature.
"""
from dual_motor import TRADERS
from math import isfinite

def leaderboard(trades):
    entries=[]
    for index,name in enumerate(TRADERS):
        confirmed=[]
        for trade in trades or []:
            if not isinstance(trade,dict) or trade.get('id') is None:
                continue
            if trade.get('status') not in ('WIN','LOSS','EMPATE'):
                continue
            if trade.get('trader_index') is None:
                owner=0 if trade.get('strategy_key')=='sniper' else -1
            else:
                owner=trade.get('trader_index')
            if owner!=index:continue
            value=trade.get('profit')
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value):
                continue
            confirmed.append(trade)
        wins=sum(t['status']=='WIN' for t in confirmed)
        losses=sum(t['status']=='LOSS' for t in confirmed)
        ties=sum(t['status']=='EMPATE' for t in confirmed)
        profit=round(sum(t['profit'] for t in confirmed),2)
        decisions=wins+losses
        rate=round(wins*100/decisions,1) if decisions else None
        entries.append({'index':index,'name':name,'wins':wins,'losses':losses,
            'ties':ties,'trades':len(confirmed),'profit':profit,'win_rate':rate,
            'strategy':confirmed[-1].get('strategy','') if confirmed else '',
            'has_results':bool(confirmed),'small_sample':decisions<10,
            'rank':None})
    ranked=sorted([r for r in entries if r['has_results']],
                  key=lambda r:(-r['profit'],-r['wins'],
                                -(r['win_rate'] or 0),-r['trades'],r['index']))
    for i,entry in enumerate(ranked,1):entry['rank']=i
    return {'scope':'SESSAO_ATUAL','broker_mode':'PRACTICE',
            'ranking':ranked,'traders':entries,
            'total_confirmed':sum(x['trades'] for x in entries),
            'ranking_basis':'Lucro e WIN/LOSS de ordens confirmadas; não usa backtests.'}
