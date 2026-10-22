const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');const start=html.indexOf('function operationView('),end=html.indexOf('function renderOperationLive(',start);assert(start>0&&end>start);const c={};vm.createContext(c);vm.runInContext(html.slice(start,end)+';this.view=operationView',c);
const s={executor:{running:true,connected:true,selected:[{name:'test',h:1}],trades:[]}};
assert.equal(c.view(s,100).phase,'searching');
s.executor.selected=[];assert.equal(c.view(s,100).phase,'waiting');
s.executor.trades=[{status:'ENVIANDO',t:60,h:1}];assert.equal(c.view(s,100).phase,'sending');
s.executor.trades=[{status:'ABERTA',broker_id:123,expiration:180,h:1}];let v=c.view(s,130);assert.equal(v.phase,'open');assert.equal(v.remaining,50);
v=c.view(s,175);assert.equal(v.phase,'finalizing');assert.equal(v.remaining,5);
v=c.view(s,181);assert.equal(v.remaining,0);assert.equal(v.phase,'finalizing');assert(!v.title.includes('WIN'));assert(v.subtitle.includes('confirmar'));
assert.equal(c.view(s,130,true).phase,'offline');
s.executor.trades=[{status:'INCERTA'}];assert.equal(c.view(s,130).phase,'uncertain');
s.executor.trades=[{status:'WIN',finished_at:180,profit:1.7}];assert.equal(c.view(s,181).phase,'result');assert.equal(c.view(s,200).phase,'waiting');
console.log('Live UI: search, qualification, sending, countdown, finalization, stale connection and confirmed result passed.');
const dom={},tableRows={};const elem=id=>dom[id]||(dom[id]={textContent:'',replaceChildren(){tableRows[id]=[]},classList:{toggle(_,hidden){this.hidden=hidden}},setAttribute(k,v){this[k]=v}});
const researchContext={$:elem,cellRow:(id,values)=>(tableRows[id]||=[]).push(values),Date,Number,String};vm.createContext(researchContext);
const rs=html.indexOf('function renderResearch('),re=html.indexOf('function renderExecutor(',rs);
vm.runInContext(html.slice(rs,re)+';this.render=renderResearch',researchContext);
researchContext.render({research:[]});assert(tableRows.bestHistory[0][0].includes('Nenhuma'));
researchContext.render({research:[{name:'Xtreme',h:1,version:2,promoted:true,wins:5,losses:8,ties:1,rate:35.7,profit:-7.5,promoted_at:1000},{name:'Impulso',h:2,version:1,promoted:false,wins:4,losses:1,ties:0,rate:80,profit:4.8,remaining:1}]});
assert.equal(tableRows.bestHistory[0][3],5);assert.equal(tableRows.bestHistory[0][4],8);assert.equal(tableRows.bestHistory[0][7],'-7.50');assert(tableRows.bestHistory[0][9].includes('negativo'));
assert.equal(tableRows.candidateHistory[0][3],'4 / 5');assert.equal(tableRows.candidateHistory[0][7],'1 WIN');
const ps=html.indexOf('function showPanel('),pe=html.indexOf('\n',ps);vm.runInContext(html.slice(ps,pe)+';this.select=showPanel',researchContext);researchContext.select('best');assert.equal(dom.bestPanel.classList.hidden,false);assert.equal(dom.executorPanel.classList.hidden,true);assert.equal(dom.tabBest['aria-pressed'],'true');
console.log('Best tab: empty state, fifth WIN, losses, negative profit, progress and navigation passed.');
const ms=html.indexOf('function mgPreview('),me=html.indexOf('\nfor(const id',ms);vm.runInContext(html.slice(ms,me)+';this.preview=mgPreview',researchContext);
elem('execStake').value='2';elem('execMgLevels').value='2';elem('execMgMultiplier').value='2';elem('execMg').checked=true;researchContext.preview();assert(dom.mgPreview.textContent.includes('Base: 2.00 → Gale 1: 4.00 → Gale 2: 8.00'));assert(dom.mgPreview.textContent.includes('14.00'));
elem('execMg').checked=false;researchContext.preview();assert(dom.mgPreview.textContent.includes('desligado'));console.log('Martingale preview: off state, levels and total sequence loss passed.');
// Waiting diagnostics must be readable and distinguish unassessed filters.
{
 const nodes={};const make=()=>({children:[],textContent:'',style:{},append(...xs){this.children.push(...xs)},replaceChildren(){this.children=[]}});
 const get=id=>nodes[id]||(nodes[id]=make());const ctx={$:get,document:{createElement:make},Date};vm.createContext(ctx);
 const a=html.indexOf('function renderThiagoStatus('),b=html.indexOf('function render(s)',a);assert(a>=0&&b>a);vm.runInContext(html.slice(a,b),ctx);
 const state={connected:true,running:true,server_now:1000,thiago_checks:[{asset:'TEST',at:990,direction:0,reason:'Aguardando o primeiro Sniper a favor da nova tendência.',filters:{toque_na_retracao:null}}]};
 ctx.renderThiagoStatus(state);assert.equal(nodes.thiagoStatusCards.children.length,1);assert(nodes.thiagoStatusCards.children[0].children[1].textContent.includes('primeiro Sniper'));assert(!nodes.thiagoStatusCards.children[0].children[1].textContent.includes('toque_na_retracao'));
 state.server_now=1200;ctx.renderThiagoStatus(state);assert(nodes.thiagoStatusCards.children[0].children[1].textContent.includes('desatualizada'));
 state.thiago_checks=[];ctx.renderThiagoStatus(state);assert(nodes.thiagoSummary.textContent.includes('Aguardando dados'));console.log('Thiago diagnostics: readable waiting reason, stale data and empty state passed.');
}
