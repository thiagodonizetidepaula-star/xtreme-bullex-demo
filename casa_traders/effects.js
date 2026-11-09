/* Casa dos Traders — UI effects based on verified PRACTICE settlements ONLY.
 * Usage: const house = window.CasaTraderEffects.create({ container: root });
 * await house.unlockAudio() from a user click; house.update(serverSideBoard).
 * Never put broker credentials or a Supabase service role key in this file.
 */
(function (global) {
  "use strict";
  const DEFAULT_COLOR = ["#F1C75B","#58D6C6","#7AB9FF","#CFAAFF","#F58D9D"];
  const safe = v => v == null ? "" : String(v);
  function create({ container, onEvent, goalText } = {}) {
    if (!container) throw Error("Provide a leaderboard container.");
    let known = new Set(),knownGoals = new Set(),firstFrame = true,context = null;
    let audioUnlocked = false,hasLoaded = false;
    const AudioCtx = global.AudioContext || global.webkitAudioContext;
    function tone(freq,start,duration,kind) {
      if (!context) return;
      const o=context.createOscillator(),gain=context.createGain();
      o.type=kind; o.frequency.setValueAtTime(freq,start);
      gain.gain.setValueAtTime(.0001,start);
      gain.gain.exponentialRampToValueAtTime(.15,start+.03);
      gain.gain.exponentialRampToValueAtTime(.0001,start+duration);
      o.connect(gain);gain.connect(context.destination);
      o.start(start);o.stop(start+duration+.015);
    }
    function horn() {
      if (!audioUnlocked || document.hidden) return;
      const t=context.currentTime+.04;
      // Original short horn rhythm; not a prerecorded copyrighted sound.
      [340,395,460].forEach((f,i)=>tone(f,t+i*.27,.24,"sawtooth"));
    }
    function winChime() {
      if (!audioUnlocked || document.hidden) return;
      const t=context.currentTime+.04;
      [660,870,1100].forEach((f,i)=>tone(f,t+i*.16,.14,"triangle"));
    }
    function lossChime() {
      if (!audioUnlocked || document.hidden) return;
      const t=context.currentTime+.04;
      [385,300].forEach((f,i)=>tone(f,t+i*.30,.27,"sine"));
    }
    function confetti() {
      if (global.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
      const overlay=document.createElement("div");
      overlay.setAttribute("aria-hidden","true");
      Object.assign(overlay.style,{position:"fixed",inset:"0",zIndex:"10000",
        pointerEvents:"none",overflow:"hidden"});
      document.body.append(overlay);
      // 44 particles, no canvas/WebGL and no animation loop.
      for(let i=0;i<44;i++){
        const piece=document.createElement("span");
        const spin=document.createElement("span");
        const x=Math.random()*100;
        Object.assign(piece.style,{position:"absolute",left:x+"%",top:"-8%",
          width:"8px",height:"15px",background:DEFAULT_COLOR[i%DEFAULT_COLOR.length],
          borderRadius:"2px",transform:"rotate("+(i*31)+"deg)"});
        const animation=piece.animate([
          {transform:"translate(0,-20px) rotate(0deg)",opacity:1},
          {transform:"translate("+(Math.random()*230-115)+"px,110vh) rotate("+(400+i*21)+"deg)",opacity:0}
        ],{duration:2300+Math.random()*1250,easing:"cubic-bezier(.19,.56,.35,1)",fill:"forwards"});
        animation.onfinish=()=>piece.remove();
        overlay.append(piece);
      }
      setTimeout(()=>overlay.remove(),4000);
    }
    const make=(tag,text)=>{const o=document.createElement(tag);if(text!=null)o.textContent=safe(text);return o;};
    function render(board) {
      container.replaceChildren();
      const title=make("h2","🏆 Mural dos Melhores Traders");
      title.style.cssText="margin:0 0 12px;font-weight:850;letter-spacing:.02em";
      container.append(title);
      const info=make("p","Somente resultados reais de ordens confirmadas na PRACTICE.");
      info.style.cssText="color:#8ca2b7;font-size:12px;margin:0 0 14px";
      container.append(info);
      const list=document.createElement("div");
      Object.assign(list.style,{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(225px,1fr))",gap:"10px"});
      for (const trader of (board.traders || [])) {
        const card=document.createElement("div");
        card.style.cssText="padding:14px;border:1px solid #335674;border-radius:14px;background:#101e33;color:#fff";
        const name=make("strong",(trader.rank===1?"🥇 ":trader.rank===2?"🥈 ":trader.rank===3?"🥉 ":"")+trader.name);
        const strategy=make("div",trader.strategy);
        strategy.style.cssText="font-size:12px;color:#9fc1d8;margin:6px 0";
        const pnl=make("div","Resultado DEMO: US$ "+Number(trader.profit||0).toFixed(2));
        pnl.style.cssText="font-weight:800;color:"+(Number(trader.profit)>0?"#76e2ad":Number(trader.profit)<0?"#f5a2a9":"#e9f1ff");
        const record=make("div",(trader.wins||0)+" WIN · "+(trader.losses||0)+" LOSS · "+(trader.draws||0)+" EMPATE");
        record.style.cssText="font-size:12px;margin-top:6px;color:#bdd2e6";
        const sample=make("div",trader.accuracy==null?"Sem amostra":"Assertividade: "+trader.accuracy+"% ("+trader.orders+" ordens)");
        sample.style.cssText="font-size:11px;color:#92abc0;margin-top:5px";
        card.append(name,strategy,pnl,record,sample);list.append(card);
      }
      container.append(list);
      const note=make("p","📚 Beatriz — Contabilidade: acompanha o financeiro, sem executar ordens nem entrar no ranking.");
      note.style.cssText="color:#9ebdd3;font-size:12px;margin-top:13px";
      container.append(note);
    }
    async function unlockAudio() {
      if(!AudioCtx)throw Error("Navegador sem WebAudio");
      if(!context)context=new AudioCtx();
      await context.resume(); audioUnlocked=true;
      horn(); // Sound check only upon explicit click
    }
    function update(board) {
      if (!board || board.account_mode !== "PRACTICE" || board.source !== "broker-confirmed-only")
        throw Error("Somente feed autêntico de ordens DEMO confirmadas");
      render(board);
      const events=Array.isArray(board.events)?board.events:[];
      const goals=Array.isArray(board.goal_events)?board.goal_events:[];
      if(!hasLoaded){
        // Preexisting results never trigger horns or confetti on page load.
        known=new Set(events.map(e=>e.id));
        knownGoals=new Set(goals.map(g=>g.trade_id+":"+g.target));
        hasLoaded=true;return;
      }
      for(const event of events){
        if(!event?.id||known.has(event.id))continue;
        known.add(event.id);
        if(event.status==="WIN") { winChime();horn(); }
        if(event.status==="LOSS")lossChime();
        if(typeof onEvent==="function")onEvent(event);
      }
      for(const goal of goals){
        const id=goal.trade_id+":"+goal.target;
        if(knownGoals.has(id))continue;
        knownGoals.add(id);
        confetti();horn();
        if(typeof goalText==="function")goalText(goal);
      }
      // Limit per-page memory while keeping recent IDs to suppress polls.
      if(known.size>500)known=new Set(events.map(e=>e.id));
      if(knownGoals.size>200)knownGoals=new Set(goals.map(g=>g.trade_id+":"+g.target));
    }
    return { update,unlockAudio };
  }
  global.CasaTraderEffects={create};
})(window);
