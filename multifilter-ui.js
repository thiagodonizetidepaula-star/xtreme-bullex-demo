'use strict';
(()=>{
const get=id=>document.getElementById(id);let result=null;
const fields=[['atr_min_pct','ATR mínimo / preço',.00005,.00001],['atr_max_pct','ATR máximo / preço',.03,.001],['min_spread_atr','Separação mínima das médias / ATR',.15,.01],['min_slope_atr','Inclinação mínima EMA21 / ATR',.03,.01],['max_distance_atr','Distância máxima EMA21 / ATR',1.5,.1],['max_range_atr','Amplitude máxima da vela / ATR',1.8,.1],['touch_atr','Tolerância do toque / ATR',.15,.01],['structure_atr','Tolerância da estrutura EMA50 / ATR',.15,.01],['barrier_atr','Distância mínima de barreira / ATR',.3,.05],['pullback_bars','Velas para buscar pullback',3,1],['min_payout','Payout mínimo (%)',80,1],['stake','Valor fixo por entrada hipotética',1,.01],['max_orders','Máximo de ordens por amostra',50,1],['stop_loss','Stop loss por amostra',10,.1],['stop_win','Stop win por amostra',20,.1],['max_loss_streak','Máximo de LOSS consecutivos',5,1]];
for(const [key,label,value,step] of fields){const l=document.createElement('label'),input=document.createElement('input');l.textContent=label;input.type='number';input.id='paper_'+key;input.value=value;input.step=step;input.required=true;input.min=0;l.append(input);get('paperParams').append(l)}
function row(id,values){const tr=document.createElement('tr');for(const value of values){const td=document.createElement('td');td.textContent=value??'—';tr.append(td)}get(id).append(tr)}
const pct=x=>x==null?'—':(x*100).toFixed(1)+'%',num=x=>x==null?'—':Number(x).toFixed(3),date=x=>new Date(x*1000).toLocaleString('pt-BR');
function show(data){
 result=data;get('paperResults').classList.remove('hidden');get('paperVerdict').textContent=data.status+' · '+data.mode+' · '+data.orders_sent+' ordens enviadas · origem: '+data.source;
 for(const id of ['paperMetrics','paperComparisons','paperDecisions','paperTrades','paperLimits'])get(id).replaceChildren();
 for(const [label,m] of [['Desenvolvimento',data.development],['Validação cronológica',data.validation],['Total (não é aprovação)',data.metrics]])row('paperMetrics',[label,m.total,m.wins,m.losses,m.ties,pct(m.win_rate)+(m.wilson95?' / '+m.wilson95.map(pct).join('–'):''),num(m.expectancy_units),num(m.net_units),num(m.drawdown_units),m.max_loss_streak,pct(m.break_even)]);
 get('paperQuality').textContent='M1: '+data.quality.M1.rows+' velas · M5: '+data.quality.M5.rows+' velas · gaps '+data.quality.M1.gaps+'/'+data.quality.M5.gaps+' · conflitos M1/M5: '+data.m5_conflicts+' · abertas/futuras excluídas: '+(data.quality.M1.excluded_open_or_future+data.quality.M5.excluded_open_or_future);
 get('paperAudit').textContent='Versão '+data.version+' · validação a partir de '+date(data.validation_start)+' · hash '+data.data_hash;
 for(const [name,m] of Object.entries(data.comparison_validation))row('paperComparisons',[name,m.total,m.wins+' / '+m.losses,num(m.expectancy_units),num(m.drawdown_units)]);
 for(const s of data.sensitivity){const m=s.validation;row('paperComparisons',['Sensibilidade '+s.parameter+' = '+s.value.toFixed(3),m.total,m.wins+' / '+m.losses,num(m.expectancy_units),num(m.drawdown_units)])}
 for(const e of data.events.slice(-200).reverse())row('paperDecisions',[date(e.at),e.direction_candidate||'SEM CANDIDATA',num(e.indicators.rsi14),num(e.indicators.atr14),e.payout==null?'Ausente':e.payout+'% · '+e.payout_origin,pct(e.break_even_at_signal),e.data_quality,Object.entries(e.filters).filter(([,ok])=>!ok).map(([name])=>name).join(', '),e.state]);
 for(const t of data.trades.slice().reverse())row('paperTrades',[date(t.entry_at),t.direction,t.entry_price,date(t.expiration),t.exit_price,t.status,num(t.profit_units),t.sample]);
 for(const text of data.limits){const p=document.createElement('p');p.textContent=text;get('paperLimits').append(p)}
 get('paperMessage').textContent=data.events.filter(e=>e.technical_candidate).length+' candidatas técnicas · '+data.trades.length+' operações hipotéticas · '+data.interruptions.length+' interrupções de risco/dados. Nenhuma estratégia aprovada.';
}
get('paperForm').onsubmit=async e=>{e.preventDefault();get('paperRun').disabled=true;get('paperMessage').textContent='Lendo M1/M5 e avaliando filtros, liquidação hipotética e divisão temporal…';try{
 const f1=get('paperM1').files[0],f5=get('paperM5').files[0];if(!f1)throw Error('Escolha o CSV M1.');if(f1.size>1500000||f5?.size>1500000)throw Error('Máximo de 1,5 MB por CSV.');
 const params=Object.fromEntries(fields.map(([key])=>[key,Number(get('paper_'+key).value)]));params.expiry_minutes=Number(get('paperExpiry').value);
 const payload={asset:get('paperAsset').value,source:get('paperSource').value,m1_csv:await f1.text(),m5_csv:f5?await f5.text():'',params,payout:get('paperPayout').value===''?null:Number(get('paperPayout').value),validation_start:get('paperCutoff').value||null,hypothetical_settlement:get('paperModel').checked,compare:get('paperCompare').checked,sensitivity:get('paperSensitivity').checked};
 const r=await fetch('/api/paper/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw Error(data.error||'Falha na análise.');show(data);
 }catch(err){get('paperMessage').textContent=err.message}finally{get('paperRun').disabled=false}};
get('paperDemo').onclick=()=>{
 const bars=[];let previous=100;for(let i=0;i<1800;i++){const close=100+.003*i+.1*Math.sin(i*.55)+.08*Math.sin(i*.07);bars.push([1710000000+i*60,previous,Math.max(previous,close)+.015,Math.min(previous,close)-.015,close,85]);previous=close}
 const five=[];for(let i=0;i<bars.length;i+=5){const a=bars.slice(i,i+5);five.push([a[0][0],a[0][1],Math.max(...a.map(b=>b[2])),Math.min(...a.map(b=>b[3])),a.at(-1)[4],85])}
 const csv=a=>'from,open,high,low,close,payout\n'+a.map(r=>r.join(',')).join('\n');
 for(const [id,rows] of [['paperM1',bars],['paperM5',five]]){const dt=new DataTransfer();dt.items.add(new File([csv(rows)],'FICTICIO-'+id+'.csv',{type:'text/csv'}));get(id).files=dt.files}
 get('paperAsset').value='FICTICIO';get('paperSource').value='DADOS FICTÍCIOS — teste da interface, sem evidência de mercado';get('paperModel').checked=true;get('paperCutoff').value='';get('paperMessage').textContent='Demonstração FICTÍCIA carregada. Nenhum preço de mercado ou resultado real.';get('paperForm').requestSubmit();
};
get('paperExport').onclick=()=>{if(!result)return;const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='multifiltros-paper-'+result.data_hash.slice(0,12)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
showPanel('paper');
})();
