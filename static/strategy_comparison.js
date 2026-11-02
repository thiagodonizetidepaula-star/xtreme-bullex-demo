'use strict';
// Official DEMO results only. A signal, paper result or pending order is NOT a trade.
// Pure function: safely combine broker-session history with user's persisted RLS history.
const XT_STRATEGY_NAMES=Object.freeze({
 zigzag_fractal:'ZigZag + Fractal',
 triangle:'Triângulo Breakout',
 trend_ema:'Tendência · EMA + ADX',
 swing_pullback:'Swing / Pullback',
 sr_breakout:'Suporte / Resistência · Rompimento',
 sr_reversal:'Suporte / Resistência · Rejeição',
 bollinger_breakout:'Canal / Rompimento · Bollinger',
 rsi_bollinger:'RSI + Bollinger',
 candle_patterns:'Padrões de Velas',
 macd_adx:'MACD + ADX',
 standard:'Estratégia anterior',
 unknown:'Antiga · não identificada'
});
function xtNormalizeOfficialTrade(raw){
 if(!raw||typeof raw!=='object'||!raw.id)return null;
 const detail=raw.result&&typeof raw.result==='object'?raw.result:{};
 const status=raw.status;
 if(!['WIN','LOSS','EMPATE'].includes(status))return null;
 const amount=Number(raw.amount);
 const net=Number(raw.net??detail.net);
 const expiry=Number(raw.expiry??detail.expiry);
 if(!Number.isFinite(amount)||amount<=0||!Number.isFinite(net))return null;
 if((status==='WIN'&&net<=0)||(status==='LOSS'&&net>=0)||
    (status==='EMPATE'&&net!==0))return null;
 const profile=String(raw.strategy||detail.strategy||'unknown');
 return {id:String(raw.id),profile,amount,net,expiry:
   Number.isFinite(expiry)&&expiry>0?expiry:null,status};
}
function xtSummarizeStrategies(sessionRows,storedRows,expiryFilter=null){
 const trades=new Map();
 // The current live broker status is newer than asynchronous DB persistence.
 for(const raw of [...(Array.isArray(storedRows)?storedRows:[]),
                   ...(Array.isArray(sessionRows)?sessionRows:[])]){
  const trade=xtNormalizeOfficialTrade(raw);
  if(trade)trades.set(trade.id,trade);
 }
 const groups=new Map();
 for(const t of trades.values()){
  if(expiryFilter!=null&&t.expiry!==Number(expiryFilter))continue;
  if(!groups.has(t.profile))groups.set(t.profile,{
   profile:t.profile,name:XT_STRATEGY_NAMES[t.profile]||t.profile,
   trades:0,wins:0,losses:0,ties:0,net:0,stake:0,expiries:new Set()});
  const g=groups.get(t.profile);
  g.trades++;
  g.wins+=Number(t.status==='WIN');
  g.losses+=Number(t.status==='LOSS');
  g.ties+=Number(t.status==='EMPATE');
  g.net+=t.net;
  g.stake+=t.amount;
  if(t.expiry!=null)g.expiries.add(t.expiry);
 }
 return [...groups.values()].map(g=>({
  profile:g.profile,name:g.name,trades:g.trades,wins:g.wins,
  losses:g.losses,ties:g.ties,net:g.net,stake:g.stake,
  winRate:g.wins+g.losses?100*g.wins/(g.wins+g.losses):null,
  roi:g.stake?100*g.net/g.stake:null,
  expiries:[...g.expiries].sort((a,b)=>a-b),
  initialSample:g.trades<30
 })).sort((a,b)=>
  Number(a.initialSample)-Number(b.initialSample)||
  (a.initialSample?b.trades-a.trades:(b.roi??-Infinity)-(a.roi??-Infinity))||
  b.trades-a.trades||a.name.localeCompare(b.name,'pt-BR'));
}
