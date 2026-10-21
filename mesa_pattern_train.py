"""Weekly research-only pattern miner. No Bullex login / NO broker orders.
Install: pip install -r requirements-learning.txt
Run: python mesa_pattern_train.py --days 7 --train-days 2 --expiration 1
Requires MESA_HISTORY_API_URL and MESA_HISTORY_TOKEN in PRIVATE environment.
Never publishes patterns if data, payouts or out-of-sample approval are insufficient.
"""
import argparse,bisect,collections,datetime,hashlib,json,math,time
from statistics import NormalDist
from mesa_pattern_client import PatternGateway,PatternGatewayError
from mesa_pattern_features import features_for_closed,MODEL_FEATURES
from mesa_quant import breakeven,wilson,metrics
from strategy import analyze_selected

UTC=datetime.timezone.utc
def utc(epoch):return datetime.datetime.fromtimestamp(epoch,UTC).isoformat()
def stamp(text):return int(datetime.datetime.fromisoformat(text.replace("Z","+00:00")).timestamp())
def get_all(gateway,kind,since,until,maxrows=1800000):
 out=[];offset=0
 while offset<maxrows:
  part=gateway.rows(kind,utc(since),utc(until),offset=offset,limit=1000)
  if not isinstance(part,list):raise RuntimeError("Invalid research input")
  out.extend(part);offset+=len(part)
  if len(part)<1000:break
 if offset>=maxrows:raise RuntimeError("Dataset exceeds validated memory/row budget")
 return out

def count_m5_feature_rows(candles):
 """Compute indicator vectors for every available closed M5 after warmup;
 current trade approval uses only M1 vectors to ensure live-feature parity."""
 by_asset=collections.defaultdict(list)
 for b in candles:
  if b.get("timeframe")!=5:continue
  try:
   by_asset[b["asset"]].append({"from":stamp(b["candle_time"]),
      "o":float(b["o"]),"h":float(b["h"]),"l":float(b["l"]),"c":float(b["c"])})
  except (KeyError,ValueError,TypeError):continue
 calculated=0
 for asset,rows in by_asset.items():
  rows.sort(key=lambda x:x["from"])
  for i in range(109,len(rows)):
   if features_for_closed(rows[max(0,i-125):i+1],timeframe=5) is not None:
    calculated+=1
 return calculated

def last_payout(lookup,asset,when):
 obs=lookup.get(asset,[])
 if not obs:return None
 i=bisect.bisect_right(obs,(when,101))-1
 if i<0:return None
 at,p=obs[i]
 # Only actual observations from BEFORE entry; no retroactive hourly payout.
 return p if 0<=when-at<=3600 else None

def prepare(candles,payouts,expiration,min_payout=80):
 quotes=collections.defaultdict(list)
 for p in payouts:
  try:
   at=stamp(p["observed_at"]);v=float(p["payout"])
   if 0<v<=100:quotes[p["asset"]].append((at,v))
  except (KeyError,ValueError,TypeError):continue
 for a in quotes:quotes[a].sort()
 groups=collections.defaultdict(list)
 for b in candles:
  if b.get("timeframe")!=1:continue
  try:
   bar={"from":stamp(b["candle_time"]),"o":float(b["o"]),"h":float(b["h"]),
        "l":float(b["l"]),"c":float(b["c"])}
   groups[b["asset"]].append(bar)
  except (KeyError,ValueError,TypeError):pass
 samples=[]
 for asset,rows in groups.items():
  rows.sort(key=lambda b:b["from"])
  # Form bounded 130 candle windows to guarantee same calculations in LIVE.
  for i in range(125,len(rows)-expiration):
   old=rows[i-125:i+expiration+1]
   if any(old[j]["from"]-old[j-1]["from"]!=60 for j in range(1,len(old))):
    continue
   entry=rows[i+1]["from"]
   payout=last_payout(quotes,asset,entry)
   if payout is None or payout<min_payout:continue
   f=features_for_closed(rows[i-125:i+1])
   if not f:continue
   opening=rows[i+1]["o"];closing=rows[i+expiration]["c"]
   outcome="EMPATE" if closing==opening else "CALL" if closing>opening else "PUT"
   if any(f.get(x) is None or not math.isfinite(f[x]) for x in MODEL_FEATURES):continue
   samples.append({"asset":asset,"t":entry,"features":f,"payout":payout,
                   "outcome":outcome,"expiration":expiration,
                   "bars":rows[i-119:i+1]})
 return sorted(samples,key=lambda r:(r["t"],r["asset"]))

def stats_for(rows):
 n=len(rows);wins=sum(x["win"] for x in rows)
 avg=sum(x["payout"] for x in rows)/n if n else None
 lower,upper=wilson(wins,n)
 exp=sum((x["payout"]/100 if x["win"] else -1) for x in rows)/n if n else None
 return {"occurrences":n,"wins":wins,"win_rate":wins/n if n else None,
         "ci95":[lower,upper] if n else [0,1],
         "average_payout":avg,"breakeven":breakeven(avg) if avg else None,
         "expectancy_per_stake":exp}

def tree_paths(tree,features):
 from sklearn.tree import _tree
 out=[]
 t=tree.tree_
 def visit(node,path):
  if t.feature[node]==_tree.TREE_UNDEFINED:
   counts=t.value[node][0];winner=int(counts.argmax())
   side=tree.classes_[winner]
   if side in ("CALL","PUT") and len(path)>=1:
    out.append((node,side,path))
   return
  key=features[t.feature[node]];v=float(t.threshold[node])
  visit(t.children_left[node],path+[{"feature":key,"op":"<=","value":v}])
  visit(t.children_right[node],path+[{"feature":key,"op":">","value":v}])
 visit(0,[])
 return out

def matches(path,features):
 for step in path:
  v=features[step["feature"]]
  if not (v<=step["value"] if step["op"]=="<=" else v>step["value"]):return False
 return True

def week_validate(samples,training_days=2,expiration=1,min_oos=300):
 try:
  from sklearn.tree import DecisionTreeClassifier
  from sklearn.ensemble import RandomForestClassifier
 except ImportError as e:raise RuntimeError("pip install -r requirements-learning.txt") from e
 if not samples:return [],{"warning":"Sem candles ou payouts históricos com cobertura temporal suficiente."}
 first=samples[0]["t"]//86400*86400
 split=first+training_days*86400
 train=[r for r in samples if r["t"]<split]
 remaining=[r for r in samples if r["t"]>=split]
 days=sorted({r["t"]//86400 for r in remaining})
 if len(days)<2 or len(train)<500:
  return [],{"warning":"Amostra insuficiente: precisa de 2 dias de treino e 2+ dias futuros para walk-forward.",
             "train":len(train),"test":len(remaining),"days":len(days)}
 X=[[x["features"][key] for key in MODEL_FEATURES] for x in train]
 y=[x["outcome"] for x in train]
 tree=DecisionTreeClassifier(max_depth=3,min_samples_leaf=200,random_state=42)
 forest=RandomForestClassifier(n_estimators=60,max_depth=4,min_samples_leaf=150,
                               n_jobs=2,random_state=42)
 tree.fit(X,y);forest.fit(X,y)
 patterns=tree_paths(tree,MODEL_FEATURES)
 candidate_count=len(patterns)
 final=[]
 # Compare models daily, using the SAME frozen trees; test days never fit models.
 benchmark={"tree":[],"forest":[],"baseline_5of6":[]}
 byday=collections.defaultdict(list)
 for r in remaining:byday[r["t"]//86400].append(r)
 for d,items in sorted(byday.items()):
  xt=[[r["features"][k] for k in MODEL_FEATURES] for r in items]
  for name,model in [("tree",tree),("forest",forest)]:
   ys=model.predict(xt)
   decisions=[{"win":str(v)==r["outcome"],"payout":r["payout"]}
              for v,r in zip(ys,items) if str(v) in ("CALL","PUT")]
   benchmark[name].append({"day":d,"metrics":stats_for(decisions)})
  # Exact production 5/6 logic on closed M1, as comparison only.
  # This is expensive offline, intentionally not used by live trading.
  baseline=[]
  for r in items:
   bars=[{"from":b["from"],"open":b["o"],"max":b["h"],"min":b["l"],"close":b["c"]} for b in r["bars"]]
   try:
    a=analyze_selected(bars,r["t"]+1,"mesa")
   except (ValueError,KeyError,TypeError):continue
   side=(a.get("direction") or "").upper()
   if side in ("CALL","PUT"):
    baseline.append({"win":side==r["outcome"],"payout":r["payout"]})
  benchmark["baseline_5of6"].append({"day":d,"metrics":stats_for(baseline)})
 for node,side,rule in patterns:
  daily=[]
  for d,items in sorted(byday.items()):
   matched=[{"win":side==r["outcome"],"payout":r["payout"]}
            for r in items if matches(rule,r["features"])]
   daily.append({"day":d,"rows":matched,"stats":stats_for(matched)})
  all_events=[r for p in daily for r in p["rows"]]
  s=stats_for(all_events)
  # Day-to-day stability checks: each supporting day must be >= break-even,
  # and minimum TWO separate out-of-sample days must have >=30 observations.
  supported=[p for p in daily if len(p["rows"])>=30]
  stable=sum(p["stats"]["win_rate"]>=p["stats"]["breakeven"] for p in supported)
  raw_95=s["ci95"][0]
  # Extra multiple-testing protection, not a substitute for independent test:
  z=NormalDist().inv_cdf(1-.05/(2*max(1,candidate_count)))
  corrected=wilson(s["wins"],s["occurrences"],z)[0]
  eligible=s["occurrences"]>=min_oos and stable>=2 and len(supported)>=2 and (
    corrected>s["breakeven"] and s["expectancy_per_stake"]>0) if s["occurrences"] and s["breakeven"] is not None else False
  if not eligible:continue
  token=hashlib.sha256(json.dumps([side,expiration,rule],sort_keys=True).encode()).hexdigest()[:18]
  final.append({"pattern_id":"mesa-"+token,"source_model":"shallow_tree",
    "direction":side,"expiration_m1":expiration,"rule":rule,
    "trained_until":utc(split),"oos_start":utc(split),
    "oos_end":utc(max(r["t"] for r in remaining)+60),
    "oos_occurrences":s["occurrences"],"oos_wins":s["wins"],
    "oos_lower_95":raw_95,"equilibrium_rate":s["breakeven"],
    "expectancy_per_stake":s["expectancy_per_stake"],
    "stable_folds":stable,"approved":True,"active":True})
 return final,{"train":len(train),"test":len(remaining),"test_days":len(days),
              "candidate_patterns":candidate_count,"approved":len(final),
              "models_vs_original_5of6":benchmark,
              "warning":"OOS com payout observado por hora; não representa ordens executadas. Nenhuma garantia de 60-70%."}

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--days",type=int,default=7)
 parser.add_argument("--train-days",type=int,default=2)
 parser.add_argument("--expiration",type=int,choices=[1,5],default=1)
 parser.add_argument("--report",default="mesa_pattern_report.json")
 parser.add_argument("--publish",action="store_true",
                     help="Publica lista validada, inclusive vazia, desativando padrões antigos")
 args=parser.parse_args()
 if not 3<=args.days<=7:parser.error("Retenção gratuita é no máximo 7 dias.")
 gateway=PatternGateway()
 if not gateway.enabled:raise SystemExit("Faltam credenciais privadas do gateway Supabase.")
 end=int(time.time());start=end-args.days*86400
 rows=get_all(gateway,"candles",start,end)
 pay=get_all(gateway,"payouts",start,end)
 samples=prepare(rows,pay,args.expiration)
 approved,report=week_validate(samples,args.train_days,args.expiration)
 report.update({"collected_candles":len(rows),"m5_feature_rows_computed":count_m5_feature_rows(rows),"quotes":len(pay),"expiry_m1":args.expiration,
   "approved_patterns":approved,"generated_utc":utc(end),
   "data_window":{"from":utc(start),"to":utc(end)}})
 with open(args.report,"w",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
 if args.publish:
  if args.expiration!=1:raise SystemExit("Expiração M5 só para pesquisa; bot atual executa M1.")
  reply=gateway.publish(approved)
  print("Supabase atualizado:",reply)
 print("Relatório:",args.report,"padrões APROVADOS:",len(approved))
 if not approved:print("SEM PADRÃO APROVADO; robô em modo aprendizado NÃO enviará ordens.")
if __name__=="__main__":main()
