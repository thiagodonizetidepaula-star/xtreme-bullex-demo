"""Browser voice announcer: Android toggle, dedupe and multi-trade outcomes.

These tests simulate speechSynthesis. No actual broker calls, no API charges.
"""
import pathlib,shutil,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class VoiceNotifications(unittest.TestCase):
    def test_markup_is_visible_and_receives_server_events(self):
        html=(ROOT/'templates/mesa.html').read_text(encoding='utf-8')
        self.assertIn('id="mesaVoiceToggle"',html)
        self.assertIn('id="mesaVoiceTest"',html)
        self.assertIn('id="mesaVoiceVolume"',html)
        self.assertLess(html.index('id="mesaVoiceToggle"'),html.index('id="advancedSettings"'))
        self.assertIn('window.MesaVoice.update(s)',html)
        self.assertIn('mesa-voice.js?v=voice1',html)
    def test_javascript_simulation_three_trades_and_results(self):
        node=shutil.which('node')
        if not node:
            source=(ROOT/'static/mesa-voice.js').read_text(encoding='utf-8')
            self.assertIn('window.MesaVoice={update}',source)
            self.assertIn('t.status==="WIN"||t.status==="LOSS"',source)
            self.assertIn('if(!initialized)',source)
            return
        source=ROOT/'static/mesa-voice.js'
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const speech=[];
let on={};
function element(){
  return {value:"80",textContent:"",disabled:false,listeners:{},
    setAttribute(k,v){this[k]=v},
    addEventListener(ev,fn){this.listeners[ev]=fn}};
}
const els={};
const ids=['mesaVoiceToggle','mesaVoiceTest','mesaVoiceVolume','mesaVoiceVolumeValue','mesaVoiceStatus'];
ids.forEach(id=>els[id]=element());
class Utterance{constructor(text){this.text=text}}
const native={
 speak(u){speech.push(u.text)}, cancel(){speech.push("CANCEL")},
 getVoices(){return [{lang:"pt-BR",localService:true,name:"Português Brasil"}]},
 addEventListener(){}
};
const window={speechSynthesis:native,SpeechSynthesisUtterance:Utterance};
const document={readyState:"complete",getElementById:id=>els[id]};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document,Date,Math,Number,String,Map});
const now=new Date().toISOString();
const first={event_key:"a",time:now,asset:"EURUSD-OTC",status:"ABERTA",direction:"call",expiry_minutes:2};
const later={event_key:"b",time:now,asset:"GBPJPY-OTC",status:"ABERTA",direction:"put",expiry_minutes:5};
const third={event_key:"c",time:now,asset:"AUDUSD-OTC",status:"ABERTA",direction:"call",expiry_minutes:1};
const incoming=trades=>({trades,server_now:Date.now()/1000});
// Initial poll cannot repeat old events.
window.MesaVoice.update(incoming([first]));
assert.equal(speech.length,0);
els.mesaVoiceToggle.listeners.click();
assert.equal(speech.length,1);
assert(speech[0].includes("ativada"));
window.MesaVoice.update(incoming([first,later,third]));
assert.equal(speech.length,3);
assert(speech[1].includes("VENDA"));
assert(speech[2].includes("COMPRA"));
window.MesaVoice.update(incoming([first,later,third]));
assert.equal(speech.length,3);
const win={...first,status:"WIN",profit:1.7,result_time:now};
const loss={...later,status:"LOSS",profit:-2,result_time:now};
const tie={...third,status:"EMPATE",result_time:now};
window.MesaVoice.update(incoming([win,loss,tie]));
assert.equal(speech.length,5);
assert(speech[3].includes("WIN"));
assert(speech[4].includes("LOSS"));
window.MesaVoice.update(incoming([win,loss,tie]));
assert.equal(speech.length,5);
const ignored={event_key:"d",asset:"EURCHF",time:now,status:"IGNORADA"};
window.MesaVoice.update(incoming([win,loss,tie,ignored]));
assert.equal(speech.length,5);
els.mesaVoiceToggle.listeners.click();
assert.equal(speech.at(-1),"CANCEL");
const after={event_key:"e",time:now,asset:"CADUSD",status:"ABERTA",direction:"put"};
window.MesaVoice.update(incoming([win,loss,tie,ignored,after]));
assert.equal(speech.at(-1),"CANCEL");
console.log("speech simulations passed");
"""
        result=subprocess.run([node,'-e',script,str(source)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('speech simulations passed',result.stdout)
    def test_grammar_parses_with_node(self):
        node=shutil.which('node')
        if node:
            result=subprocess.run([node,'--check',str(ROOT/'static/mesa-voice.js')],
                                  capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":unittest.main()
