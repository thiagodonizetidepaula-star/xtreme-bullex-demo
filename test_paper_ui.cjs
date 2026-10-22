const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes={},requests=[];let selected='';
function node(tag='div'){return {dataset:{},tag,children:[],value:'',checked:false,files:[],textContent:'',disabled:false,classList:{remove(){},add(){}},append(x){this.children.push(x);if(x.id)nodes[x.id]=x},replaceChildren(){this.children=[]},click(){},requestSubmit(){this.requested=true}}}
const get=id=>nodes[id]||(nodes[id]=node());
class File{constructor(parts,name){this.name=name;this.data=parts.join('');this.size=this.data.length}text(){return Promise.resolve(this.data)}}
class DataTransfer{constructor(){this.files=[];this.items={add:f=>this.files.push(f)}}}
const empty={total:0,wins:0,losses:0,ties:0,win_rate:null,wilson95:null,expectancy_units:null,net_units:0,drawdown_units:0,max_loss_streak:0,break_even:null};
const response={status:'EXPERIMENTAL',mode:'PAPER_TRADING',orders_sent:0,source:'FICTÍCIO',development:empty,validation:empty,metrics:empty,quality:{M1:{rows:1800,gaps:0,excluded_open_or_future:0},M5:{rows:360,gaps:0,excluded_open_or_future:0}},m5_conflicts:0,version:'v1',validation_start:1710050000,data_hash:'abc',comparison_validation:{},sensitivity:[],events:[],trades:[],limits:[],interruptions:[]};
const c={document:{getElementById:get,createElement:node},showPanel:x=>selected=x,File,DataTransfer,Math,Date,Number,Object,JSON,Error,Blob,URL,setTimeout,fetch:async(url,opts)=>{requests.push([url,JSON.parse(opts.body)]);return {ok:true,json:async()=>response}}};vm.createContext(c);vm.runInContext(fs.readFileSync('multifilter-ui.js','utf8'),c);
(async()=>{
 assert.equal(selected,'analysis');assert.equal(nodes.mfLiveParams.children.length,11);assert.equal(nodes.paperParams.children.length,16);
 get('paperExpiry').value='1';get('paperCompare').checked=true;get('paperDemo').onclick();
 assert(get('paperSource').value.includes('FICTÍCIOS'));assert(get('paperM1').files[0].name.includes('FICTICIO'));assert.equal(get('paperM1').files[0].data.split('\n').length,1801);assert.equal(get('paperM5').files[0].data.split('\n').length,361);assert(get('paperForm').requested);
 await get('paperForm').onsubmit({preventDefault(){}});
 assert.equal(requests.length,1);assert.equal(requests[0][0],'/api/paper/evaluate');assert.equal(requests[0][1].hypothetical_settlement,true);assert.equal(requests[0][1].params.expiry_minutes,1);assert.equal(requests[0][1].params.max_distance_atr,1.5);assert(get('paperVerdict').textContent.includes('0 ordens'));assert.equal(get('paperRun').disabled,false);
 get('paperM1').files=[{size:1500001}];await get('paperForm').onsubmit({preventDefault(){}});assert.equal(requests.length,1);assert(get('paperMessage').textContent.includes('1,5 MB'));
 console.log('Paper UI: default panel, parameters, explicit fictitious fixture, CSV-only request, zero-order report and upload limit passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
