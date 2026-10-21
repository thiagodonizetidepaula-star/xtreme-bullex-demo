"""Offline chronological M1 binary-options backtest. RESEARCH ONLY.

Usage:
 python mesa_backtest.py --csv historical_m1.csv --out research_report.json
CSV UTC columns: asset,from,open,max,min,close,payout
'from' = epoch seconds UTC of M1 bar start. 'payout' = quoted at start
of THAT bar (not afterwards). Separate asset series, >=121 candles per asset.
Optional --news-file contains verified high-impact events; absent => news filter
blocks every candidate instead of assuming no important news.

ASSUMPTIONS: fill at next M1 open, settle at its close (60s), no spread, no
latency or slippage. No evidence that demo broker will actually fill this
price/payout; live-demo outcomes take precedence. This module places NO orders.
"""
import argparse,csv,json,math
from datetime import datetime,timezone
from pathlib import Path
from collections import defaultdict
from mesa_strategy import analyze_mesa
from mesa_quant import (breakeven,check_filters,automatic_blacklist,metrics,
                        snapshot,MIN_APPROVAL_TRADES)

def read_candles(filename):
    by_asset=defaultdict(list)
    with open(filename,encoding="utf-8-sig",newline="") as f:
        source=csv.DictReader(f)
        needed={"asset","from","open","max","min","close","payout"}
        if not needed.issubset(source.fieldnames or []):
            raise ValueError("CSV exige colunas "+",".join(sorted(needed)))
        for row in source:
            try:
                asset=row["asset"].strip()
                t=int(row["from"])
                o,h,l,c,p=(float(row[k]) for k in ("open","max","min","close","payout"))
            except (ValueError,KeyError,TypeError) as exc:
                raise ValueError("Dados OHLC ou payout inválidos") from exc
            if not asset or t%60 or not all(math.isfinite(v) for v in (o,h,l,c,p)) or min(o,h,l,c)<=0 or l>min(o,c) or h<max(o,c) or not 0<p<=100:
                raise ValueError("Candle/payout inválido no CSV")
            by_asset[asset].append({"asset":asset,"from":t,"open":o,"max":h,"min":l,"close":c,"payout":p})
    if not by_asset:raise ValueError("Histórico vazio")
    for asset,rows in by_asset.items():
        rows.sort(key=lambda b:b["from"])
        if len({r["from"] for r in rows})!=len(rows):
            raise ValueError("Timestamps duplicados em "+asset)
    return by_asset

def candidate_events(by_asset):
    """Generate only from closed M1 bars; order entry at following bar open.
    Expiration one complete M1 bar after signal closes. No future-derived features.
    All bars are sorted and contiguous locally; gaps reset a warmup window.
    """
    events=[]
    for asset,rows in by_asset.items():
        for i in range(120,len(rows)-1):
            signal=rows[i];entry=rows[i+1]
            if entry["from"]!=signal["from"]+60:continue
            prior=rows[i-119:i+1]
            if any(b["from"]-a["from"]!=60 for a,b in zip(prior,prior[1:])):
                continue
            now=signal["from"]+60+1
            a=analyze_mesa(prior,now)
            side=a.get("direction") or a.get("candidate_direction")
            votes=a.get("votes") or {}
            if not side or max(votes.get("call",0),votes.get("put",0))<4:continue
            # DATA ALIGNMENT: entry bar's payout must have been recorded at entry
            # time; never substitute payout observed after entry or at settlement.
            ts=entry["from"]
            # Counterfactual 4/6 is SHADOW ONLY; live bot stays at >=5/6.
            a={**a,"direction":side}
            pnl=entry["payout"]/100 if (entry["close"]>entry["open"] and side=="call") or (entry["close"]<entry["open"] and side=="put") else -1 if entry["close"]!=entry["open"] else 0
            f=snapshot(asset,a,signal,ts,entry["payout"],1)
            evt={"asset":asset,"time":ts,"signal_time":now,"direction":side,
                 "payout":entry["payout"],"status":"WIN" if pnl>0 else "LOSS" if pnl<0 else "EMPATE",
                 "profit":pnl,"stake":1,"timestamp_utc":f["timestamp_utc"],
                 "features":f,"signal_index":i,"_bars":prior,"_analysis":a}
            events.append(evt)
    return sorted(events,key=lambda t:(t["time"],t["asset"]))

def evaluate(events,config="baseline",adx_min=25,news=None,blacklist=None):
    """Exactly ONE optional filter versus baseline. One global trade per minute."""
    if config in ("baseline","votes_4","votes_5","votes_6"):enabled={}
    elif config.startswith("adx_"):
        enabled={"adx":True}
        adx_min=int(config.split("_")[1])
    else:enabled={config:True}
    taken=[];busy_until=-1
    for e in events:
        if e["time"]<busy_until:continue
        required=4 if config=="votes_4" else 6 if config=="votes_6" else 5
        if e["features"]["confirmed_filters"]<required:continue
        checks=check_filters(e["_analysis"],e["_bars"],e["time"],e["asset"],
               switches=enabled,adx_min=adx_min,events=news,bad_segments=blacklist)
        if not checks["allowed"]:continue
        outcome={k:v for k,v in e.items() if not k.startswith("_")}
        outcome.pop("signal_index",None)
        outcome["filter_config"]=config
        outcome["filter_checks"]=checks["checks"]
        taken.append(outcome)
        busy_until=e["time"]+60
    return taken

CONFIGS=["baseline","votes_4","votes_5","votes_6","sessions","volatility","adx_20","adx_25","adx_30",
         "support_resistance","candle","news","bad_segments"]

def walk_forward(by_asset,news=None):
    all_events=candidate_events(by_asset)
    times=sorted({r["from"] for rows in by_asset.values() for r in rows})
    if len(times)<400:
        raise ValueError("Amostra pequena: forneça pelo menos 400 minutos M1, por vários dias para análise.")
    cut1=times[int(.6*len(times))]
    cut2=times[int(.8*len(times))]
    folds=[
       {"train_before":cut1,"test_from":cut1,"test_until":cut2},
       {"train_before":cut2,"test_from":cut2,"test_until":times[-1]+60},
    ]
    fold_reports=[];oos=defaultdict(list)
    for fold in folds:
        train=[e for e in all_events if e["time"]<fold["train_before"]]
        test=[e for e in all_events if fold["test_from"]<=e["time"]<fold["test_until"]]
        # Only older TRAIN outcomes determine blacklist. Never use test labels.
        blacklist=automatic_blacklist([t for t in evaluate(train,"baseline")])
        training_scores={}
        for c in CONFIGS:
            rows=evaluate(train,c,news=news,blacklist=blacklist)
            training_scores[c]=metrics(rows)
        eligible=[c for c in CONFIGS if training_scores[c]["approved"]]
        # The selector itself is TRAIN ONLY. If no proven edge, retain baseline.
        chosen=(max(eligible,key=lambda c:training_scores[c]["expectancy_per_stake"])
                if eligible else "baseline")
        results={}
        for c in CONFIGS:
            trades=evaluate(test,c,news=news,blacklist=blacklist)
            results[c]=metrics(trades)
            oos[c].extend(trades)
        fold_reports.append({
          "train_before_utc":datetime.fromtimestamp(fold["train_before"],timezone.utc).isoformat(),
          "test_start_utc":datetime.fromtimestamp(fold["test_from"],timezone.utc).isoformat(),
          "test_end_utc":datetime.fromtimestamp(fold["test_until"],timezone.utc).isoformat(),
          "train_results":training_scores,
          "selected_by_train_only":chosen,
          "test_results":results,
        })
    combined={c:metrics(oos[c]) for c in CONFIGS}
    baseline=combined["baseline"]
    improvements={}
    for c in CONFIGS:
        if c=="baseline":continue
        current=combined[c]
        improvements[c]={
           "delta_win_rate":(current["win_rate"]-baseline["win_rate"])
             if current["win_rate"] is not None and baseline["win_rate"] is not None else None,
           "delta_expectancy_per_stake":(current["expectancy_per_stake"]-baseline["expectancy_per_stake"])
             if current["expectancy_per_stake"] is not None and baseline["expectancy_per_stake"] is not None else None,
           "statistically_approved_oos":current["approved"],
           "note":"Efeito de um filtro isolado, em conjunto de TESTE não usado na otimização.",
        }
    return {"schema":"mesa_backtest_v1","candles_per_asset":{k:len(v) for k,v in by_asset.items()},
       "candidate_signals":len(all_events),"assumptions":[
           "Entrada no OPEN do minuto posterior ao fechamento do sinal; saída no CLOSE após 60 s.",
           "Payout obtido no início da vela de ENTRADA, nunca preenchido por média posterior.",
           "Sem spread/slippage/latência; backtest não reproduz qualidade real de execução Bullex.",
           "Ativos podem operar individualmente em horários de volatilidade diferente; a simulação limita a uma ordem global por minuto.",
           "Filtro de notícias requer calendário externo auditável; sem feed o filtro bloqueia todas entradas.",
           "Filtro de pares ruins treina somente com resultados anteriores à janela de teste.",
           "Nenhum ajuste foi validado em amostra insuficiente; sem martingale."
       ],
       "train_fraction_first_fold":.6,"test_folds":fold_reports,
       "out_of_sample_aggregate":combined,"one_filter_at_a_time":improvements,
       "approved_configurations":[c for c in CONFIGS if combined[c]["approved"]],
       "disclaimer":"DEMO e pesquisa, sem garantia de lucro nem promessa de 60-70%."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True,help="Candles M1 UTC com payout por minuto")
    p.add_argument("--out",default="research_report.json")
    p.add_argument("--news-file",help="JSON com eventos validados: [{timestamp_utc,impact:'high'}]")
    a=p.parse_args()
    events=json.loads(Path(a.news_file).read_text(encoding="utf-8")) if a.news_file else None
    results=walk_forward(read_candles(a.csv),events)
    Path(a.out).write_text(json.dumps(results,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print(f"Relatório gerado: {a.out}. Configurações aprovadas (OOS): {results['approved_configurations']}")
    print("Sem dados suficientes, a resposta correta é 'nenhum filtro comprovado'.")

if __name__=="__main__":main()
