import json,os,subprocess,sys,threading,secrets,select,time
from wsgiref.simple_server import make_server
from urllib.parse import urlparse
from http.cookies import SimpleCookie
from pathlib import Path
from socketserver import ThreadingMixIn
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from clean_v1.automation import run as run_bot
from clean_v1.archive import account_id,configured,history
HTML='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Xtreme-Tiger · Análise Contínua</title><style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;color:#eef7ff;font:15px system-ui,Arial;background:radial-gradient(circle at 12% 2%,#17234d 0,transparent 30%),#050b18}main{max-width:900px;margin:auto;padding:18px 14px 40px}.brand{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 18px}.brand h1{font-size:clamp(20px,4.5vw,30px);margin:0;font-weight:900;letter-spacing:.6px}.brand b,.cyan{color:#11dcf5}.brand .x{font-size:39px;background:linear-gradient(135deg,#00eaf6,#9c36ff);color:transparent;background-clip:text;margin-right:7px}.subtitle,.muted{color:#9cb4d3;font-size:13px;line-height:1.6}.online{color:#17e6a7;border:1px solid #086951;border-radius:32px;padding:10px 14px;font-weight:800;white-space:nowrap}.card{background:linear-gradient(145deg,#081529,#0a1023 80%);border:1px solid #284a79;border-radius:22px;padding:20px;margin:0 0 16px;box-shadow:0 10px 28px #0003}.hero{border-color:#2878bc;background:radial-gradient(circle at 80% 70%,#10245a,#071223 63%)}h2{font-size:18px;letter-spacing:.4px;margin:0 0 15px}h3{font-size:14px;color:#b6c8ed;letter-spacing:.8px;margin:0 0 10px}.hero h2{font-size:clamp(23px,5vw,36px);margin:8px 0}.kicker{font-size:13px;letter-spacing:2px;color:#9ab0d4}.status{border:1px solid #156b8b;color:#71e9ff;border-radius:30px;padding:9px 13px;white-space:nowrap;font-size:13px;font-weight:800}.topline{display:flex;gap:12px;justify-content:space-between;align-items:flex-start}.m1{display:inline-block;padding:12px 17px;border:1px solid #05dbea;border-radius:12px;color:#05e5f4;background:#062b48;font-weight:800;margin-top:20px}.m5{display:inline-block;padding:12px 17px;border:1px solid #284467;border-radius:12px;color:#617f9e;margin:20px 0 0 8px}.bar{height:9px;border-radius:20px;background:#182944;overflow:hidden;margin:18px 0 12px}.bar>div{height:100%;width:0%;border-radius:20px;background:linear-gradient(90deg,#00f2e9,#158eff,#b53cff);transition:width .2s linear}.scanbar{height:9px;border-radius:20px;background:#182944;overflow:hidden;margin:15px 0}.scanbar>div{height:100%;width:0%;border-radius:20px;background:linear-gradient(90deg,#00ecb0,#08b7ee);transition:width .3s linear}.radar.eye-radar{position:relative;overflow:hidden;animation:eye-glow 2.8s ease-in-out infinite}.eye-shape{width:80px;height:48px;border:3px solid #31ffc7;border-radius:50%;display:grid;place-items:center;box-shadow:0 0 18px #15f5b650}.eye-pupil{width:25px;height:25px;background:#28edbd;border-radius:50%;box-shadow:0 0 14px #25ffd1;animation:eye-look 2.5s ease-in-out infinite}.eye-radar::after{content:'';position:absolute;width:94px;height:94px;border:1px solid #35dfff55;border-radius:50%;animation:eye-glow 2.8s ease-in-out infinite}@keyframes eye-look{0%,100%{transform:translateX(-15px)}50%{transform:translateX(15px)}}@keyframes eye-glow{0%,100%{box-shadow:0 0 14px #04b7dc44,inset 0 0 20px #6d2eff22}50%{box-shadow:0 0 30px #04b7dc88,inset 0 0 25px #6d2eff55}}.row{display:flex;gap:12px;justify-content:space-between;align-items:center}.clock{font-size:21px;color:#64f3ff;font-weight:900}.duo{display:grid;grid-template-columns:1fr 1fr;gap:14px}.trade{border-color:#087d65}.analyzer{border-color:#7533c4}.pair{font-size:clamp(21px,4vw,34px);font-weight:900;overflow-wrap:anywhere}.signal{padding:18px;border-radius:16px;margin:15px 0;background:#063b36;border:1px solid #03cb92;color:#3bffc1;font-size:27px;font-weight:900}.signal.put{color:#ff668f;background:#341527;border-color:#ae416b}.signal small{font-size:12px;font-weight:600;display:block;margin-top:7px}.radar{height:120px;margin:16px auto;max-width:140px;border-radius:100%;border:2px solid #16d5f3;box-shadow:0 0 18px #04b7dc44,inset 0 0 30px #6d2eff55;display:flex;justify-content:center;align-items:center;color:#53edff;font-size:44px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.score{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{background:#0b1d36;border:1px solid #254669;border-radius:14px;padding:14px;min-width:0}.metric strong{font-size:clamp(18px,4.5vw,29px);display:block;margin-top:6px;overflow-wrap:anywhere}.metric:nth-child(1) strong{color:#27e7a9}.metric:nth-child(2) strong{color:#ff608f}.metric:nth-child(4) strong{color:#18e7c6}.state{background:#0f2d43;border-radius:12px;padding:13px;color:#dffbff;font-weight:700}.btn{border:0;background:#12cfa6;border-radius:12px;padding:13px;color:#002a25;font-weight:850;width:100%;font-size:15px;margin:8px 0}.btn:disabled{opacity:.4}.outline{background:#143655;color:#cbf5ff}label{font-size:12px;color:#abc5e4}input{width:100%;background:#10243f;border:1px solid #385278;padding:12px;margin:5px 0 12px;color:white;border-radius:9px;font-size:16px}p{line-height:1.55;color:#aabdda}details summary{cursor:pointer;font-weight:750;color:#96e5ff;margin-bottom:14px}.green{color:#15e9ad}.pill{color:#0fefae;font-weight:800}.scantext{font-size:13px;color:#a6b5dc}.small{font-size:12px}#opId{font-size:14px;overflow-wrap:anywhere}#lastSignal{overflow-wrap:anywhere}@media(max-width:580px){main{padding:11px}.card{padding:16px}.duo{grid-template-columns:1fr}.score{grid-template-columns:repeat(2,minmax(0,1fr))}.brand h1{font-size:20px}.brand .x{font-size:32px}.hero h2{font-size:27px}}.tiger-watch{position:relative;margin:8px auto 12px;width:min(100%,360px);max-width:100%;height:205px;display:flex;align-items:center;justify-content:center;overflow:hidden;background:radial-gradient(ellipse at 50% 66%,#103454 0%,transparent 67%)}.tiger-watch svg{width:100%;height:100%;filter:drop-shadow(0 0 10px #0cc8f155);animation:tiger-look 5s ease-in-out infinite}.tiger-watch .binocular{transform-origin:170px 175px;animation:tiger-search 5s ease-in-out infinite}.tiger-scan-glow{position:absolute;left:10%;right:10%;bottom:5px;height:2px;background:linear-gradient(90deg,transparent,#1df8d6,transparent);animation:tiger-pulse 2s ease-in-out infinite}@keyframes tiger-look{0%,100%{transform:translateX(-5px) rotate(-1deg)}50%{transform:translateX(5px) rotate(1deg)}}@keyframes tiger-search{0%,100%{transform:translateX(-3px)}50%{transform:translateX(3px)}}@keyframes tiger-pulse{0%,100%{opacity:.2}50%{opacity:1}}@media(prefers-reduced-motion:reduce){.tiger-watch svg,.tiger-watch .binocular,.tiger-scan-glow{animation:none}}.tiger-real{position:relative;width:min(100%,360px);height:240px;margin:8px auto 12px;overflow:hidden;background:radial-gradient(ellipse at center,#102947 0%,transparent 72%)}.tiger-real img{display:block;width:100%;height:100%;object-fit:contain;mix-blend-mode:screen;animation:tiger-real-scan 5s ease-in-out infinite;filter:drop-shadow(0 0 7px #11c6f055)}@keyframes tiger-real-scan{0%,100%{transform:translateX(-4px) scale(1.02)}50%{transform:translateX(4px) scale(1.05)}}@media(prefers-reduced-motion:reduce){.tiger-real img{animation:none}}.tiger-stage{position:relative;isolation:isolate;height:clamp(255px,54vw,365px);margin:0 -16px 10px;overflow:hidden;background:radial-gradient(ellipse 65% 64% at 50% 65%,#0c2947 0%,#09162a 70%,transparent 100%);pointer-events:none}.tiger-stage:after{content:"";position:absolute;inset:0;z-index:5;background:linear-gradient(to bottom,#091529 0%,transparent 15%,transparent 67%,#091529 100%);box-shadow:inset 0 0 18px 10px #09152955;pointer-events:none}.tiger-portrait{position:absolute;z-index:3;inset:-31% -28% -12%;display:flex;align-items:center;justify-content:center;animation:tiger-gaze 6.5s ease-in-out infinite}.tiger-portrait img{display:block;width:100%;height:100%;object-fit:contain;mix-blend-mode:screen;filter:saturate(1.3) contrast(1.12) drop-shadow(0 0 9px #04d9ff44);-webkit-mask-image:linear-gradient(to bottom,transparent 0%,#000 19%,#000 68%,transparent 94%);mask-image:linear-gradient(to bottom,transparent 0%,#000 19%,#000 68%,transparent 94%)}.market-candles{position:absolute;z-index:1;inset:12% 4% 4%;display:flex;justify-content:space-around;align-items:center;opacity:.88}.market-candle{display:block;position:relative;flex:0 0 clamp(4px,1.5vw,9px);height:var(--h);border-radius:1px;background:#13e5fc;box-shadow:0 0 12px #09d4ff8c;transform:translateY(calc((var(--n) % 3) * 5px));animation:candle-float 4s ease-in-out var(--d) infinite alternate}.market-candle:nth-child(3n){background:#973cf8;box-shadow:0 0 12px #973cf8}.market-candle:nth-child(5n){background:#0781fa}.market-candle:before{content:"";position:absolute;top:-13px;bottom:-13px;left:50%;width:1px;transform:translateX(-50%);background:inherit}.tiger-lens-glow{position:absolute;z-index:4;left:23%;right:23%;bottom:20%;height:12%;opacity:.45;background:radial-gradient(ellipse,#12edff7d,transparent 70%);filter:blur(8px);animation:lens-pulse 2.7s ease-in-out infinite}@keyframes tiger-gaze{0%,16%,100%{transform:translateX(-4px) rotate(-.7deg)}42%,60%{transform:translateX(4px) rotate(.8deg)}75%{transform:translateX(0)}}@keyframes candle-float{0%{transform:translateY(15px) scaleY(.76);opacity:.6}100%{transform:translateY(-18px) scaleY(1.18);opacity:1}}@keyframes lens-pulse{50%{opacity:.85;transform:scale(1.08)}}@media(prefers-reduced-motion:reduce){.tiger-portrait,.market-candle,.tiger-lens-glow{animation:none!important}}.ai-market-core{position:relative;isolation:isolate;height:clamp(240px,52vw,345px);width:100%;overflow:hidden;margin:5px auto 12px;background:radial-gradient(ellipse at 50% 52%,#09331c88,transparent 63%);pointer-events:none}.ai-market-core:after{position:absolute;inset:0;content:"";z-index:12;background:linear-gradient(90deg,#091529 0%,transparent 12%,transparent 88%,#091529 100%),linear-gradient(0deg,#091529 0%,transparent 21%,transparent 84%,#091529 100%)}.ai-orb{position:absolute;z-index:5;left:50%;top:44%;width:min(43vw,184px);height:min(43vw,184px);max-width:52%;border-radius:50%;transform:translate(-50%,-50%);background:radial-gradient(circle at 46% 45%,#e3ffdb 0%,#3efa92 4%,#02c657 13%,#0c5832 29%,#061910 53%,#030907 72%);border:6px ridge #6ce98e;box-shadow:0 0 20px #1afa64dd,inset 0 0 35px #50ff6388,0 0 2px 10px #213a2b;animation:ai-heartbeat 4s ease-in-out infinite}.ai-orb-inner{position:absolute;inset:12%;border-radius:50%;border:2px dotted #9fffafaa;box-shadow:inset 0 0 22px #00ef6a;animation:ai-spin 13s linear infinite}.ai-reticle{position:absolute;inset:25%;border:2px solid #caffcf;border-radius:50%;box-shadow:0 0 13px #1aff78;background:radial-gradient(circle,#fcfff8 0 12%,#20f068 15%,transparent 48%)}.ai-orbit{position:absolute;z-index:7;width:min(83%,405px);height:24%;border:8px solid;border-radius:50%;top:42%;left:50%;transform-origin:center;filter:drop-shadow(0 0 9px currentColor);animation:ai-orbit-one 6s linear infinite}.ai-orbit-green{color:#00fa51;border-color:#10fa59 transparent #42ff81 #23ed67;transform:translate(-50%,-50%) rotate(-27deg)}.ai-orbit-red{color:#fa2b3b;border-color:#ff334e #ff2436 transparent #e82839;animation:ai-orbit-two 7s linear infinite reverse}.ai-orbit-white{z-index:4;width:70%;height:17%;color:#c8eaca;border-width:3px;border-color:#f1fff5 transparent #caffd3 transparent;animation:ai-orbit-three 10s linear infinite}.ai-platform{position:absolute;z-index:2;bottom:10%;left:50%;transform:translateX(-50%);width:66%;height:19%;border:5px solid #40ff77;border-radius:50%;background:radial-gradient(ellipse,#0b8f31aa 0%,#06180d 60%,transparent);box-shadow:0 0 17px #16fa55,0 0 0 8px #f6284029,inset 0 0 18px #f31f3aaa;animation:ai-platform-pulse 4s ease-in-out infinite}.ai-energy-beam{position:absolute;z-index:3;top:48%;bottom:13%;left:50%;width:3px;background:#afffc7;box-shadow:0 0 15px 6px #2afb67;animation:ai-beam-pulse 2.8s ease-in-out infinite}.ai-candles{position:absolute;z-index:1;inset:5% 2%;display:flex;align-items:center;justify-content:space-around;gap:2px}.ai-candle{position:relative;display:block;flex:0 0 clamp(3px,1.1vw,7px);height:var(--h);background:#1aff65;box-shadow:0 0 9px #17ff63;animation:ai-candle-bob 3.4s ease-in-out var(--delay) infinite alternate}.ai-candle:nth-child(3n){background:#ff3246;box-shadow:0 0 11px #ff142d}.ai-candle:before{position:absolute;content:"";top:-17px;bottom:-17px;left:50%;width:1px;background:inherit}.ai-particles{position:absolute;inset:0;z-index:1;opacity:.5;background-image:radial-gradient(#1aff6b 1px,transparent 2px),radial-gradient(#ff3449 1px,transparent 2px);background-size:39px 47px,51px 43px;animation:ai-particles-drift 9s linear infinite}@keyframes ai-spin{to{transform:rotate(360deg)}}@keyframes ai-heartbeat{50%{box-shadow:0 0 30px #25fa6a,inset 0 0 39px #50ff83,0 0 2px 10px #213a2b}}@keyframes ai-orbit-one{0%{transform:translate(-50%,-50%) rotate(-25deg) rotateY(0deg)}50%{transform:translate(-50%,-50%) rotate(-25deg) rotateY(180deg)}100%{transform:translate(-50%,-50%) rotate(-25deg) rotateY(360deg)}}@keyframes ai-orbit-two{0%{transform:translate(-50%,-50%) rotate(28deg) rotateY(0deg)}100%{transform:translate(-50%,-50%) rotate(28deg) rotateY(360deg)}}@keyframes ai-orbit-three{0%{transform:translate(-50%,-50%) rotate(80deg)}100%{transform:translate(-50%,-50%) rotate(440deg)}}@keyframes ai-candle-bob{0%{transform:translateY(16px) scaleY(.65)}100%{transform:translateY(-17px) scaleY(1.3)}}@keyframes ai-platform-pulse{50%{opacity:.7;filter:brightness(1.5)}}@keyframes ai-beam-pulse{50%{opacity:.4}}@keyframes ai-particles-drift{to{background-position:0 -47px,0 43px}}@media(prefers-reduced-motion:reduce){.ai-market-core *{animation:none!important}}.ai-market-core{perspective:760px;background:radial-gradient(ellipse at 49% 42%,#124a2380 0%,#09201466 32%,transparent 69%)}.ai-orb{background:radial-gradient(circle at 33% 23%,#eaffdf 0%,#b7ffc2 3%,#49cb74 9%,#17442b 26%,#081d13 48%,#010b07 78%),repeating-linear-gradient(125deg,transparent 0 5px,#3cff7822 6px 7px);border:4px solid #80bb89;box-shadow:inset -17px -19px 28px #000e,inset 12px 11px 21px #c7ff6555,0 16px 28px #0009,0 0 24px #1bff5169,0 0 0 8px #172d2088;will-change:transform}.ai-orb:before{content:"";position:absolute;inset:4%;border-radius:50%;border:1px solid #c7ffc644;background:repeating-linear-gradient(0deg,transparent 0 12px,#38ff4f17 13px 14px),repeating-linear-gradient(90deg,transparent 0 15px,#9aff8911 16px 17px);box-shadow:inset -10px -12px 26px #000c;transform:rotate(-18deg)}.ai-orb:after{content:"";position:absolute;inset:1%;border-radius:50%;background:radial-gradient(ellipse at 29% 17%,#f2fff38a 0%,#cfffac21 13%,transparent 36%);pointer-events:none}.ai-orbit{border-width:5px;border-style:solid;box-shadow:inset 0 2px 2px #fff5,0 3px 5px #0008;filter:drop-shadow(0 0 7px currentColor);backface-visibility:visible;will-change:transform}.ai-orbit-green{border-color:#ecffeb #41f667 #00a42f transparent}.ai-orbit-red{border-color:#fdc7bf transparent #e42538 #ed4454}.ai-orbit-white{border-width:2px}.ai-platform{border-width:3px;background:radial-gradient(ellipse,#0b3e2288 0%,#06180d 54%,transparent 76%);box-shadow:0 0 12px #16fa5588,0 0 0 9px #2af64212,0 0 0 16px #f6284016,inset 0 0 16px #fff5;transform:translateX(-50%) rotateX(22deg)}.ai-candle{border-radius:1px;background:linear-gradient(90deg,#008b29,#23ff64 55%,#78ffc0);box-shadow:0 0 5px #17ff6366}.ai-candle:nth-child(3n){background:linear-gradient(90deg,#a5001c,#ff3443 56%,#ff9797);box-shadow:0 0 6px #ff142d66}.ai-energy-beam{width:2px;background:linear-gradient(to bottom,transparent,#daffe6,#47e46b,transparent);box-shadow:0 0 11px 4px #2afb6788}.ai-particles{opacity:.38}@media(prefers-reduced-motion:reduce){.ai-orb,.ai-orbit,.ai-candle,.ai-platform,.ai-energy-beam{will-change:auto}}.bot-tabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0 0 16px}.bot-tabs button{border:1px solid #2e5472;border-radius:12px;background:#0e2138;color:#9fb7cf;padding:15px;font-size:16px;font-weight:750;cursor:pointer}.bot-tabs button.tab-selected{background:linear-gradient(125deg,#093b39,#12385c);border-color:#14dbc2;color:#38f6c9;box-shadow:inset 0 -2px #1bddae}#botPanel[hidden],#settingsPanel[hidden],.stop-overlay[hidden]{display:none!important}.stop-overlay{position:fixed;z-index:1000;inset:0;background:#010b15c9;display:grid;place-items:center;padding:20px}.stop-dialog{width:min(100%,430px);background:linear-gradient(155deg,#10213a,#071123);border:2px solid #18e5b5;border-radius:24px;box-shadow:0 0 70px #05efa744;padding:26px;text-align:center}.stop-dialog h2{font-size:24px;margin:10px 0;color:#f0ffff}.stop-dialog p{font-size:18px;color:#c6dded}.stop-symbol{font-size:52px;color:#24efb7}.gladiator-frame{position:relative;overflow:hidden;isolation:isolate;width:100%;min-height:240px;aspect-ratio:16/9;margin:8px auto 12px;background:radial-gradient(ellipse at center,#14233c,#081428);pointer-events:none}.gladiator-video{position:absolute;z-index:2;inset:0;width:100%;height:100%;object-fit:cover;display:none}.gladiator-frame.video-ready .gladiator-video{display:block}.gladiator-fallback{height:100%;width:100%;overflow:hidden}.gladiator-fallback .ai-market-core{height:100%;margin:0}.gladiator-frame.video-ready .gladiator-fallback{display:none}.gladiator-frame:after{position:absolute;z-index:3;inset:0;content:"";pointer-events:none;box-shadow:inset 0 0 18px 5px #08142866;background:linear-gradient(0deg,#091528e8,transparent 14%,transparent 92%,#09152866)}.brand .brand-copy{min-width:0;flex:1}.brand .brand-copy h1{display:flex;align-items:baseline;white-space:nowrap;font-size:clamp(18px,3.4vw,30px);letter-spacing:.3px}.brand .brand-copy .x{flex:0 0 auto;font-size:clamp(28px,5vw,39px);line-height:1;margin-right:6px}.brand-tagline{color:#aec8e5;font-size:clamp(11px,2.4vw,13px);font-weight:750;letter-spacing:1.4px;margin-top:5px}.brand-tagline.live{color:#40e7c5;font-size:clamp(10px,2.2vw,12px);font-weight:800;letter-spacing:1.2px;margin-top:2px}.brand .online{flex-shrink:0}@media(max-width:580px){.brand{gap:8px}.brand .brand-copy h1{font-size:clamp(17px,4.75vw,20px);letter-spacing:0}.brand .brand-copy .x{font-size:clamp(27px,7.5vw,32px);margin-right:5px}.brand-tagline{letter-spacing:.9px;font-size:10px}.brand-tagline.live{letter-spacing:.8px;font-size:10px}}@media(prefers-reduced-motion:reduce){.gladiator-video{animation:none}}
/* XTREME TIGER | golden brand skin | presentation only */
:root{--xt-gold:#ffc250;--xt-gold-light:#ffe1a2;--xt-copper:#b57b26;--xt-line:#85541f;--xt-panel:#161007;--xt-muted:#cab593}
body{color:#f9edda;background:radial-gradient(ellipse at 50% -8%,#3f270d 0%,transparent 41%),linear-gradient(180deg,#0c0905 0%,#070605 100%)}
.brand{gap:10px;align-items:center}
.brand .brand-copy{min-width:0;flex:1}
.xtreme-logo{display:block;width:min(100%,520px);height:auto;max-height:175px;object-fit:contain;object-position:left center;filter:drop-shadow(0 0 14px #e88e1245)}
.brand-tagline{color:#ead3a9;letter-spacing:1.6px}
.brand-tagline.live{color:#ffba43}
.brand .online{color:#ffcf75;background:#28190a;border:1px solid #b37b24;box-shadow:inset 0 0 12px #ffba2117}
.card{background:linear-gradient(145deg,#1a130b,#0e0b08 82%);border-color:#66421b;box-shadow:inset 0 1px #e6b85c0d,0 12px 28px #0005}
.hero{border-color:#bd872e;background:radial-gradient(circle at 84% 75%,#42260d,#130e09 65%)}
.trade{border-color:#a4702b}
.analyzer{border-color:#ae772a}
h2,h3{color:#f5dcad}
.brand b,.cyan,.clock{color:#ffd071}
.kicker{color:#e4c08c}
.subtitle,.muted,p,.scantext,label{color:#cbb89b}
.status{border-color:#a26d26;background:#271809;color:#ffd47c}
.m1{border-color:#d89e37;background:#35200a;color:#ffd37d}
.m5{border-color:#59452d;background:#1d160e;color:#9e8d75}
.bar,.scanbar{background:#352718}
.bar>div{background:linear-gradient(90deg,#e88d18,#ffd057,#ffae34)}
.scanbar>div{background:linear-gradient(90deg,#d9871c,#ffcf54)}
.metric{background:#1d150d;border-color:#775025}
.metric:nth-child(4) strong{color:#ffc665}
.state{background:#2b1e10;color:#ffebbe}
.btn{background:linear-gradient(120deg,#ffd979,#f0a52d 75%,#d78310);color:#221304;border:1px solid #e4a844;box-shadow:inset 0 1px #fff0af35}
.outline{background:#30200f;color:#f6d8a2;border-color:#895923}
.bot-tabs button{border-color:#7a5427;background:#21180f;color:#dcc49f}
.bot-tabs button.tab-selected{background:linear-gradient(120deg,#57350e,#38240e);border-color:#f3b43e;color:#ffdc86;box-shadow:inset 0 -2px #f6ba44,0 0 15px #ffae1415}
input{background:#21180f;border-color:#8c632d;color:#fff2dc}
input:focus-visible,button:focus-visible{outline:2px solid #ffbf4b;outline-offset:2px}
details summary{color:#ffd17a}
.stop-dialog{background:linear-gradient(155deg,#2a1c0e,#100c08);border-color:#e8af45;box-shadow:0 0 65px #ecaa2840}
.stop-dialog h2{color:#fff0d0}
.stop-dialog p{color:#e4cba1}
.stop-symbol{color:#ffc65a}
a{color:#ffd075}
@media(max-width:580px){.xtreme-logo{width:100%;max-height:none}.brand{align-items:center;gap:7px}.brand .online{font-size:11px;padding:8px 10px}.brand-tagline{letter-spacing:.8px;font-size:10px}.brand-tagline.live{letter-spacing:.8px;font-size:10px}}
/* Animated logo: responsive, seamless and isolated from the trade interface */
.xtreme-logo-wrap{position:relative;display:block;width:min(100%,640px);aspect-ratio:1270/346;min-width:0;max-width:100%;overflow:hidden;isolation:isolate}
.xtreme-logo-wrap>.xtreme-logo-fallback,.xtreme-logo-video{position:absolute;inset:0;display:block;width:100%;height:100%;max-height:none;object-fit:contain;object-position:left center}
.xtreme-logo-video{opacity:0;transition:opacity .18s ease;background:transparent;pointer-events:none}
.xtreme-logo-wrap.logo-playing .xtreme-logo-video{opacity:1}
.xtreme-logo-wrap.logo-playing .xtreme-logo-fallback{opacity:0}
@media(max-width:580px){.xtreme-logo-wrap{width:100%;aspect-ratio:1270/346}.brand{gap:8px}.brand .brand-copy{min-width:0;flex:1}.brand .online{flex-shrink:0}}
@media(min-width:581px){.xtreme-logo-wrap{width:min(100%,780px)}}
/* Keep the animated logo entirely visible; move the live label inside the tiger analyzer card. */
.brand{display:block}
.brand .brand-copy{width:100%;flex:none}
.xtreme-logo-wrap{width:100%;max-width:780px}
.analyzer-title{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}
.analyzer-title h3{margin:0}
.analysis-live{display:inline-flex;align-items:center;gap:5px;border:1px solid #a87726;border-radius:999px;padding:6px 10px;color:#ffd180;background:#352309;font-weight:800;font-size:11px;letter-spacing:.8px;white-space:nowrap}
@media(max-width:580px){.xtreme-logo-wrap{width:100%;max-width:100%}.analysis-live{font-size:10px}}
.operation-heading{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:13px}.operation-heading h3{margin:0}.operation-timeframe{display:inline-flex;align-items:center;gap:7px;border:1px solid #b47b29;border-radius:999px;padding:6px 10px;background:#30200d;color:#e5c494;font-size:10px;font-weight:800;letter-spacing:.4px;white-space:nowrap}.operation-timeframe strong{font-size:13px;color:#ffdc83}@media(max-width:580px){.operation-heading{align-items:flex-start;gap:8px}.operation-timeframe{padding:5px 9px}}
/* Header aligned with content inset of the cards, desktop and mobile. */
.brand{padding-inline:20px;margin-bottom:14px}
.brand .brand-copy{display:flex;flex-direction:column;align-items:flex-start;width:100%;min-width:0}
.brand .xtreme-logo-wrap{display:block;width:100%;max-width:780px;margin:0;aspect-ratio:1270/346}
.brand .brand-tagline{display:block;align-self:flex-start;margin:2px 0 0;padding:0;line-height:1.25;text-align:left;font-weight:800;letter-spacing:1.3px}
@media(max-width:580px){.brand{padding-inline:16px;margin-bottom:12px}.brand .xtreme-logo-wrap{width:100%;max-width:100%}.brand .brand-tagline{margin-top:2px;font-size:11px;letter-spacing:1px}}
/* Mobile card overflow fix — affects content cards only, never the animated logo. */
#botPanel,#settingsPanel{min-width:0;max-width:100%}
#botPanel>.card,#settingsPanel>.card,#botPanel>.duo{min-width:0;max-width:100%}
.duo{min-width:0;max-width:100%;grid-template-columns:repeat(2,minmax(0,1fr))}
.duo>.card,.grid>.metric,.score>.metric{min-width:0;max-width:100%}
.trade,.analyzer{min-width:0;max-width:100%;overflow-wrap:break-word}
.trade .pair,.trade .signal,.analyzer .gladiator-frame,.analyzer .scanbar{min-width:0;max-width:100%}
.operation-heading{min-width:0;max-width:100%}
.operation-heading .operation-timeframe{max-width:100%;white-space:normal;overflow-wrap:normal;line-height:1.3}
.metric,.metric strong,#opId,#parallelCandidate{min-width:0;max-width:100%;overflow-wrap:anywhere}
@media(max-width:760px){
  .duo{grid-template-columns:minmax(0,1fr)}
  .duo>.card{width:100%;min-width:0}
  .operation-heading{align-items:flex-start;flex-wrap:wrap}
  .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .grid>.metric{padding:clamp(10px,3vw,14px)}
  .row{flex-wrap:wrap}
  .bot-tabs{grid-template-columns:repeat(2,minmax(0,1fr))}
  .bot-tabs button{min-width:0;overflow-wrap:anywhere}
}
@media(max-width:340px){
  .operation-heading{flex-direction:column;align-items:flex-start}
}
/* Configurable binary expiration: only affects the settings form. */
#expirationMinutes{width:100%;max-width:100%;background:#21180f;border:1px solid #8c632d;padding:12px;margin:5px 0 12px;color:#fff2dc;border-radius:9px;font-size:16px}
#expirationMinutes:focus-visible{outline:2px solid #ffbf4b;outline-offset:2px}
/* Supabase history view in Settings; no effect on trading cards or logo. */
.archive-tools{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:end;margin:10px 0}
.archive-tools label{grid-column:1/-1}.archive-tools select{min-width:0;width:100%;background:#21180f;border:1px solid #8c632d;border-radius:10px;padding:11px;color:#fff2dc;font-size:15px}
.archive-tools .btn{margin:0;width:auto;min-width:145px;white-space:nowrap}
.archive-totals{padding:13px;margin:12px 0;border:1px solid #7f5425;border-radius:12px;background:#24170a;color:#ffe0a5;font-weight:700;overflow-wrap:anywhere}
.archive-days{display:grid;gap:10px}.archive-day{border:1px solid #704b23;border-radius:13px;overflow:hidden;background:#180f08;min-width:0}
.archive-day summary{cursor:pointer;padding:12px;font-weight:800;display:grid;grid-template-columns:1fr auto;gap:8px;color:#f8dbaa}
.archive-day .archive-date{font-weight:850}.archive-day .archive-balance{grid-column:1/-1;font-size:13px;color:#cfb898}
.archive-operations{display:grid;gap:7px;padding:7px 10px 12px}.archive-operation{border-top:1px solid #513718;padding:9px 2px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px;font-size:13px;overflow-wrap:anywhere}
.archive-operation strong{font-size:14px}.archive-operation small{display:block;color:#d2bfa5;margin-top:2px}.archive-win{color:#22e4a0}.archive-loss{color:#ff6789}.archive-draw{color:#f6c670}
@media(max-width:560px){.archive-tools{grid-template-columns:1fr}.archive-tools .btn{width:100%}.archive-day summary{grid-template-columns:1fr}.archive-operation{grid-template-columns:minmax(0,1fr) auto}}
/* Broker picker — dark-gold responsive style. */
#brokerSelect{width:100%;min-width:0;background:#21180f;border:1px solid #8c632d;padding:12px;margin:5px 0 10px;color:#fff2dc;border-radius:9px;font-size:16px}
#brokerSelect:focus-visible{outline:2px solid #ffbf4b;outline-offset:2px}
#brokerSelect:disabled{opacity:.7}
</style></head><body><main>
<div class="brand"><div class="brand-copy"><div class="xtreme-logo-wrap" aria-label="Logo Xtreme Tiger animada"><img class="xtreme-logo xtreme-logo-fallback" src="/assets/xtreme_tiger_logo.webp?v=1" alt="Xtreme Tiger — tigre dourado com gráficos de mercado" width="600" height="200" loading="eager" decoding="async"><video id="xtremeLogoVideo" class="xtreme-logo-video" autoplay muted loop playsinline preload="metadata" poster="/assets/xtreme_tiger_logo.webp?v=1" aria-label="Xtreme Tiger animado"><source src="/assets/xtreme_tiger_logo_animada.mp4?v=1" type="video/mp4"></video></div></div></div>
<nav class="bot-tabs" aria-label="Abas do aplicativo"><button type="button" id="tabBot" class="tab-selected" aria-selected="true">◉ Bot</button><button type="button" id="tabSettings" aria-selected="false">⚙ Configurações</button></nav><div id="botPanel"><section class="card"><h2>CONTROLE DA AUTOMAÇÃO</h2><div class="state" id="livePhase">● Robô parado</div><div class="state" id="state">● Desconectado</div><form id="brokerForm"><label for="brokerSelect">Escolha a corretora</label><select id="brokerSelect" name="broker" required><option value="bullex">Bullex · PRACTICE</option><option value="iqoption">IQ Option · PRACTICE</option></select><p id="brokerChoiceInfo" class="muted">Conexão exclusiva à conta de demonstração. Para trocar, desconecte primeiro.</p><label id="emailLabel" for="email">E-mail Bullex</label><input id="email" type="email" autocomplete="username" required><label id="passwordLabel" for="password">Senha Bullex</label><input id="password" type="password" autocomplete="current-password" required><button class="btn" id="connectBtn">Conectar Bullex · DEMO</button></form><p id="brokerDetail" class="muted"></p><button class="btn" id="preflight" disabled>Iniciar operações automáticas</button><p id="preflightStatus" class="muted">Aguardando executor.</p><button class="btn outline" id="stopBot" disabled>Parar robô</button><button class="btn outline" id="disconnectBtn" hidden>Desconectar</button></section>
<section class="card"><div class="row"><div><h2 id="runnerText">Robô parado</h2><div class="subtitle">Executor PRACTICE · análise contínua</div></div><div class="clock" id="mainTimer">—</div></div><div class="bar" role="progressbar" aria-label="Tempo restante da operação"><div id="orderProgressBar"></div></div><div class="small green" id="activeStatus">● AGUARDANDO ENTRADA</div><p class="muted" id="botStatus">Robô parado.</p><p class="muted" id="limitStatus">Limite configurado: 10 operações · Stop Win US$ 20 · Stop Loss US$ 10</p></section>
<div class="duo"><section class="card trade"><div class="operation-heading"><h3>OPERAÇÃO ATUAL</h3><span class="operation-timeframe" aria-label="Tempo gráfico da estratégia: M1">TEMPO GRÁFICO <strong>M1</strong></span></div><div class="pair" id="opAsset">—</div><p class="muted">Somente ordens confirmadas pela Bullex</p><p class="muted">Estratégia: <b>Xtreme Sniper + Tendência ATR 18×2 · M1</b></p><p class="muted">Expiração selecionada: <b id="selectedExpiry">M1</b></p><div class="signal" id="opDirection">—<small>SEM ENTRADA ATIVA</small></div><div class="grid"><div class="metric">Ordem Bullex<strong id="opId">—</strong></div><div class="metric">Tempo restante<strong id="opClock">—</strong></div></div><p class="muted" id="opNotice">Aguardando confirmação real.</p><p class="muted" id="lastResult">Última operação: nenhuma</p></section>
<section class="card analyzer"><div class="analyzer-title"><h3>ANÁLISE CONTÍNUA</h3><span class="analysis-live" aria-label="Análise ao vivo">● ANÁLISE AO VIVO</span></div><p class="muted">Enquanto uma ordem está ativa, o scanner procura a próxima oportunidade. Apenas uma ordem por vez.</p><div class="gladiator-frame" aria-label="Animação do tigre com binóculos analisando oportunidades"><video id="gladiatorVideo" class="gladiator-video" autoplay muted loop playsinline preload="metadata" poster="" aria-label="Tigre animado com binóculos e gráficos de mercado"><source src="/assets/tigre_binoculos.mp4?v=1" type="video/mp4"></video><div id="gladiatorFallback" class="gladiator-fallback" aria-hidden="true"><div class="ai-market-core" role="img" aria-label="Núcleo holográfico do scanner com anéis vermelhos e verdes entrelaçados e velas decorativas animadas"><div class="ai-candles"><i class="ai-candle" style="--i:0;--h:22px;--delay:-0s"></i><i class="ai-candle" style="--i:1;--h:39px;--delay:-0.41s"></i><i class="ai-candle" style="--i:2;--h:56px;--delay:-0.82s"></i><i class="ai-candle" style="--i:3;--h:73px;--delay:-1.23s"></i><i class="ai-candle" style="--i:4;--h:26px;--delay:-1.64s"></i><i class="ai-candle" style="--i:5;--h:43px;--delay:-2.05s"></i><i class="ai-candle" style="--i:6;--h:60px;--delay:-2.46s"></i><i class="ai-candle" style="--i:7;--h:77px;--delay:-0s"></i><i class="ai-candle" style="--i:8;--h:30px;--delay:-0.41s"></i><i class="ai-candle" style="--i:9;--h:47px;--delay:-0.82s"></i><i class="ai-candle" style="--i:10;--h:64px;--delay:-1.23s"></i><i class="ai-candle" style="--i:11;--h:81px;--delay:-1.64s"></i><i class="ai-candle" style="--i:12;--h:34px;--delay:-2.05s"></i><i class="ai-candle" style="--i:13;--h:51px;--delay:-2.46s"></i><i class="ai-candle" style="--i:14;--h:68px;--delay:-0s"></i><i class="ai-candle" style="--i:15;--h:85px;--delay:-0.41s"></i><i class="ai-candle" style="--i:16;--h:38px;--delay:-0.82s"></i><i class="ai-candle" style="--i:17;--h:55px;--delay:-1.23s"></i><i class="ai-candle" style="--i:18;--h:72px;--delay:-1.64s"></i><i class="ai-candle" style="--i:19;--h:25px;--delay:-2.05s"></i><i class="ai-candle" style="--i:20;--h:42px;--delay:-2.46s"></i><i class="ai-candle" style="--i:21;--h:59px;--delay:-0s"></i><i class="ai-candle" style="--i:22;--h:76px;--delay:-0.41s"></i><i class="ai-candle" style="--i:23;--h:29px;--delay:-0.82s"></i></div><div class="ai-particles"></div><div class="ai-platform"></div><div class="ai-orb"><div class="ai-orb-inner"><div class="ai-reticle"></div></div></div><div class="ai-orbit ai-orbit-green"></div><div class="ai-orbit ai-orbit-red"></div><div class="ai-orbit ai-orbit-white"></div><div class="ai-energy-beam"></div></div></div></div><div class="scanbar" role="progressbar" aria-label="Varredura de ativos"><div id="scannerProgressBar"></div></div><h2 class="cyan" id="parallelStatus">Aguardando análise</h2><div class="metric">Último sinal analisado<strong id="parallelCandidate">—</strong></div><p class="muted" id="marketStatus">Ativos: 0 · Preparados: 0 · Sinais: 0</p><p class="muted" id="rejectStatus">Aguardando sinais</p><p class="muted" id="lastSignal"></p></section></div>
<section class="card"><div class="row"><h2>PLACAR DE OPERAÇÕES</h2><span class="muted">SESSÃO DEMO</span></div><div class="score"><div class="metric">WIN<strong id="wins">0</strong></div><div class="metric">LOSS<strong id="losses">0</strong></div><div class="metric">OPERAÇÕES<strong id="orders">0</strong></div><div class="metric">RESULTADO (USD)<strong id="pnl">0,00</strong></div></div><p class="muted">Assertividade desta sessão: <b id="accuracy">—</b> · Histórico real confirmado, sem porcentagens simuladas.</p></section>
</div><div id="settingsPanel" hidden><section class="card"><h2>CONFIGURAÇÕES DE RISCO · PRACTICE</h2><p class="muted">Altere os valores com o robô parado. Eles serão restaurados no mesmo navegador ao reconectar.</p><div><div class="grid"><div><label>Entrada (US$)</label><input value="2" type="number" readonly></div><div><label>Payout mínimo (%)</label><input value="80" type="number" readonly></div><div><label>Stop Loss (US$)</label><input id="stopLoss" type="number" min="2" max="500" step=".01" value="10"></div><div><label>Stop Win (US$)</label><input id="stopWin" type="number" min="2" max="500" step=".01" value="20"></div></div><div><label for="expirationMinutes">Tempo de expiração da operação</label><select id="expirationMinutes" aria-label="Tempo de expiração" required><option value="1">M1 — 1 minuto</option><option value="2">M2 — 2 minutos</option><option value="3">M3 — 3 minutos</option><option value="5">M5 — 5 minutos</option></select><p class="muted">A estratégia continua analisando o gráfico M1; a expiração define quando a ordem termina.</p></div><div><label>Máximo de operações por sessão DEMO</label><input id="maxOrders" type="number" min="10" max="1000" step="1" value="10"></div><button class="btn outline" id="saveSettings">Salvar configurações</button><p class="muted" id="saveStatus">Configure antes de iniciar.</p></div></section>
<section class="card"><h2>ESTUDO DOS WIN E LOSS</h2><p class="muted">Pavios, doji e engolfos são observados; não bloqueiam entradas.</p><p class="muted" id="researchSummary">Nenhuma operação observada nesta sessão.</p></section>
<section class="card" id="archiveCard"><h2>HISTÓRICO POR DATA · PRACTICE</h2><p class="muted">Placar de operações confirmadas pela Bullex, gravadas no Supabase por conta e data. Nenhuma ordem simulada.</p><div class="archive-tools"><label for="archiveDate">Data</label><select id="archiveDate"><option value="">Todas as datas</option></select><button class="btn outline" id="loadArchive" type="button">Atualizar histórico</button></div><p class="muted" role="status" aria-live="polite" id="archiveInfo">Conecte sua conta PRACTICE para consultar os registros.</p><div id="archiveTotals" class="archive-totals" hidden></div><div id="archiveDays" class="archive-days"></div></section>
</div><div class="stop-overlay" id="stopOverlay" role="alertdialog" aria-modal="true" aria-labelledby="stopTitle" hidden><div class="stop-dialog"><div class="stop-symbol" id="stopSymbol">■</div><h2 id="stopTitle">Limite atingido</h2><p id="stopDescription"></p><button class="btn outline" type="button" id="dismissStop">Entendi</button></div></div></main><script>
const el=id=>document.getElementById(id);let lastState={};let lastStopShown='';function switchTab(which){let bot=which==='bot';el('botPanel').hidden=!bot;el('settingsPanel').hidden=bot;el('tabBot').classList.toggle('tab-selected',bot);el('tabSettings').classList.toggle('tab-selected',!bot);el('tabBot').setAttribute('aria-selected',String(bot));el('tabSettings').setAttribute('aria-selected',String(!bot));}el('tabBot').onclick=()=>switchTab('bot');el('tabSettings').onclick=()=>switchTab('settings');let brokerLoginError='';function brokerName(value){return value==='iqoption'?'IQ Option':'Bullex'}function updateBrokerPicker(){const name=brokerName(el('brokerSelect').value);el('emailLabel').textContent='E-mail '+name;el('passwordLabel').textContent='Senha '+name;el('connectBtn').textContent='Conectar '+name+' · DEMO';el('brokerChoiceInfo').textContent=name==='IQ Option'?'Integração comunitária não oficial; autenticação e execução exigem validação da conta PRACTICE.':'Bullex PRACTICE · integração atual do Xtreme-Tiger.';}el('brokerSelect').addEventListener('change',()=>{brokerLoginError='';updateBrokerPicker();el('brokerDetail').textContent='';});updateBrokerPicker();el('dismissStop').onclick=()=>{el('stopOverlay').hidden=true};let riskDirty=false;let settingsSaving=false;for(const id of ['stopLoss','stopWin','maxOrders','expirationMinutes']){el(id).addEventListener('input',()=>{riskDirty=true;el('saveStatus').textContent='Alterações não salvas';});}let scannerPos=0;setInterval(()=>{const bar=el('scannerProgressBar');if(!bar)return;if(lastState.running){scannerPos=(scannerPos+3)%101;bar.style.width=scannerPos+'%'}else{scannerPos=0;bar.style.width='0%'}},350);function clock(){const expiry=Number(lastState.expire_ts)||0;if(!expiry||!lastState.current_order_id){el('opClock').textContent='—';el('mainTimer').textContent='—';el('orderProgressBar').style.width='0%';return}let left=Math.max(0,Math.ceil(expiry-Date.now()/1000));el('opClock').textContent=String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0');el('mainTimer').textContent=el('opClock').textContent;const duration=Math.max(1,expiry-(Number(lastState.entry_ts)||expiry-60));el('orderProgressBar').style.width=(100*Math.min(1,left/duration)).toFixed(2)+'%';if(left===0&&lastState.phase==='running_order')el('opNotice').textContent='Tempo encerrado · aguardando resultado confirmado pela Bullex';}setInterval(clock,250);
async function send(path,body){const res=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const v=await res.json();if(!res.ok)throw Error(v.error||'Erro ao conectar');return v}
function show(v){lastState=v;if(v.stop_reason&&v.stop_reason!==lastStopShown){lastStopShown=v.stop_reason;el('stopTitle').textContent=v.stop_reason.startsWith('Stop Win')?'STOP WIN ATINGIDO':v.stop_reason.startsWith('Stop Loss')?'STOP LOSS ATINGIDO':'LIMITE DE OPERAÇÕES';el('stopSymbol').textContent=v.stop_reason.startsWith('Stop Win')?'✓':'■';el('stopDescription').textContent=v.stop_reason;el('stopOverlay').hidden=false;}if(!v.stop_reason)lastStopShown='';const active=!!v.current_order_id;el('activeStatus').textContent=active?'● EM ANDAMENTO':'● AGUARDANDO ENTRADA';el('parallelStatus').textContent=v.running?'Analisando a próxima oportunidade em paralelo':'Aguardando início do robô';el('parallelCandidate').textContent=v.last_signal?(v.last_signal.asset+' · '+v.last_signal.direction):'Nenhum ativo selecionado';el('accuracy').textContent=(Number(v.wins||0)+Number(v.losses||0))?(((v.wins||0)/(Number(v.wins||0)+Number(v.losses||0))*100).toFixed(1)+'%'):'—';el('runnerText').textContent=v.running?(active?'Operação automática em andamento':'Procurando entrada válida'):'Robô parado';const research=v.research_summary||{};const labels={doji:'Doji',opposing_wick:'Pavio contrário',long_wick:'Pavio longo',engulf_against:'Engolfo contrário',near_range_edge:'Próximo a suporte/resistência'};el('researchSummary').textContent=Object.entries(labels).map(([k,name])=>name+': '+(research[k]?.wins||0)+' WIN / '+(research[k]?.losses||0)+' LOSS').join(' · ');const names={catalog:'Lendo ativos',reconnecting:'Reconectando leitura do mercado',scan:'Analisando mercado',signal:'Sinal encontrado',sending:'Enviando ordem',running_order:'Operação em andamento',result:'Resultado confirmado',uncertain:'Confirmação incerta',error:'Erro na análise'};el('livePhase').textContent='● '+(names[v.phase]||(v.running?'Preparando análise':'Robô parado'));el('marketStatus').textContent='Ativos: '+(v.markets||0)+' · Preparados: '+(v.ready||0)+' · Sinais: '+(v.signals||0);const z=v.rejections||{};el('rejectStatus').textContent='Sinais ignorados: fora da janela '+(z.late||0)+' · preparação '+(z.preflight||0)+' · ordem em curso '+(z.busy||0)+' · corretora '+(z.broker||0)+' · lateral '+(z.lateral||0)+' · fluxo cansado '+(z.exhausted||0);el('opAsset').textContent=v.current_asset||'—';el('opDirection').textContent=v.current_direction||'—';el('opId').textContent=v.current_order_id||'—';el('lastResult').textContent=v.last_result?('Última operação: '+v.last_result.asset+' · '+v.last_result.direction+' · '+v.last_result.status+' · '+Number(v.last_result.profit).toFixed(2)+' USD'):'Última operação: nenhuma';el('opNotice').textContent=v.current_order_id?'Expiração informada pela Bullex · resultado depende da corretora':'Aguardando ordem confirmada; sem contador simulado.';clock();el('state').textContent=v.connected?'● '+brokerName(v.broker)+' PRACTICE · '+v.balance+' '+v.currency:'● Desconectado';el('brokerSelect').disabled=!!v.connected;if(v.connected){el('brokerSelect').value=v.broker||'bullex';updateBrokerPicker();}el('brokerForm').hidden=!!v.connected;el('preflight').disabled=!v.executor_connected||!!v.running;el('stopBot').disabled=!v.running;if(v.settings&&!riskDirty&&!settingsSaving){el('stopLoss').value=v.settings.stop_loss;el('stopWin').value=v.settings.stop_win;el('maxOrders').value=v.settings.max_orders;el('expirationMinutes').value=String(v.settings.expiration_minutes||1);}el('selectedExpiry').textContent='M'+(v.settings?.expiration_minutes||1);el('expirationMinutes').disabled=!!v.running||!!v.pending;el('saveSettings').disabled=!!v.running||!!v.pending;el('botStatus').textContent=v.stop_reason||v.message||(v.running?'Analisando':'Robô parado');el('limitStatus').textContent=v.settings?('Limite configurado: '+v.settings.max_orders+' operações · Stop Win US$ '+v.settings.stop_win+' · Stop Loss US$ '+v.settings.stop_loss):'Conecte à PRACTICE para configurar limites';el('wins').textContent=v.wins||0;el('losses').textContent=v.losses||0;el('orders').textContent=v.orders||0;el('pnl').textContent=(v.profit||0).toFixed(2);el('lastSignal').textContent=v.last_signal?'Último sinal: '+v.last_signal.asset+' '+v.last_signal.direction:'';el('disconnectBtn').hidden=!v.connected;if(v.connected)brokerLoginError='';el('brokerDetail').textContent=v.connected?(v.executor_connected?'Leitura e executor '+brokerName(v.broker)+' conectados à PRACTICE.':'Leitura '+brokerName(v.broker)+' conectada; executor ainda indisponível.'):(brokerLoginError||'Conta real não permitida. Conecte a uma corretora em PRACTICE.')}
el('brokerForm').onsubmit=async e=>{e.preventDefault();el('connectBtn').disabled=true;brokerLoginError='';el('brokerDetail').textContent='Autenticando na '+brokerName(el('brokerSelect').value)+' PRACTICE (leitura e executor)...';const pwd=el('password').value;el('password').value='';try{let v=await send('/api/connect',{email:el('email').value,password:pwd,broker:el('brokerSelect').value});show(v);let saved=null;try{saved=JSON.parse(localStorage.getItem('xtreme-demo-settings-v1')||'null')}catch(_e){}if(saved&&Number.isInteger(saved.max_orders)&&saved.max_orders>=10&&saved.max_orders<=1000&&Number(saved.stop_loss)>=2&&Number(saved.stop_win)>=2){try{v=await send('/api/settings',saved);show(v);el('saveStatus').textContent='Configurações anteriores restauradas e confirmadas na PRACTICE'}catch(e){el('saveStatus').textContent='Não foi possível restaurar configurações: '+e.message}}}catch(err){brokerLoginError='Não foi possível conectar a '+brokerName(el('brokerSelect').value)+': '+(err.message||'erro desconhecido');el('brokerDetail').textContent=brokerLoginError;}finally{el('connectBtn').disabled=false}};
el('disconnectBtn').onclick=async()=>{show(await send('/api/disconnect',{}))};el('preflight').onclick=async()=>{try{show(await send('/api/start',{}))}catch(e){el('botStatus').textContent=e.message}};
el('saveSettings').onclick=async()=>{if(settingsSaving)return;settingsSaving=true;try{let v=await send('/api/settings',{stop_loss:Number(el('stopLoss').value),stop_win:Number(el('stopWin').value),max_orders:Number(el('maxOrders').value),expiration_minutes:Number(el('expirationMinutes').value)});riskDirty=false;settingsSaving=false;show(v);try{localStorage.setItem('xtreme-demo-settings-v1',JSON.stringify({stop_loss:v.settings.stop_loss,stop_win:v.settings.stop_win,max_orders:v.settings.max_orders,expiration_minutes:v.settings.expiration_minutes}))}catch(_e){}el('saveStatus').textContent='Configurações salvas nesta sessão e neste navegador'}catch(e){settingsSaving=false;el('saveStatus').textContent=e.message}};el('stopBot').onclick=async()=>{try{show(await send('/api/stop',{}))}catch(e){el('botStatus').textContent=e.message}};
setInterval(()=>fetch('/api/state',{credentials:'same-origin'}).then(r=>r.json()).then(show).catch(()=>{}),3000);
fetch('/api/state',{credentials:'same-origin'}).then(r=>r.json()).then(show).catch(()=>{});
</script><script>
const archiveEl=id=>document.getElementById(id);
let archiveData=null, archiveBusy=false, archiveLoadedForSession=false;
function archiveNode(tag,text,className){
 const node=document.createElement(tag);
 if(text!==undefined)node.textContent=String(text);
 if(className)node.className=className;
 return node;
}
function formatArchiveDay(day){const a=String(day).split('-');return a.length===3?a[2]+'/'+a[1]+'/'+a[0]:day;}
function formatArchiveMoney(n){return 'US$ '+Number(n||0).toFixed(2);}
function displayArchive(){
 const root=archiveEl('archiveDays'),totalsBox=archiveEl('archiveTotals');
 root.replaceChildren();
 if(!archiveData){totalsBox.hidden=true;return;}
 const filter=archiveEl('archiveDate').value;
 const all=archiveData.days||[];
 const shown=filter?all.filter(x=>x.date===filter):all;
 const totals=filter?shown.reduce((a,d)=>({trades:a.trades+Number(d.trades),wins:a.wins+Number(d.wins),losses:a.losses+Number(d.losses),draws:a.draws+Number(d.draws),profit:a.profit+Number(d.profit)}),{trades:0,wins:0,losses:0,draws:0,profit:0}):(archiveData.totals||{trades:0,wins:0,losses:0,draws:0,profit:0});
 totalsBox.hidden=false;
 totalsBox.textContent='OPERAÇÕES: '+totals.trades+'  ·  WIN: '+totals.wins+'  ·  LOSS: '+totals.losses+'  ·  EMPATE: '+totals.draws+'  ·  RESULTADO: '+formatArchiveMoney(totals.profit);
 if(!shown.length){root.append(archiveNode('p','Nenhuma operação confirmada para esta data.','muted'));return;}
 for(const d of shown){
  const block=archiveNode('details',undefined,'archive-day');
  const sum=archiveNode('summary');
  sum.append(archiveNode('span',formatArchiveDay(d.date),'archive-date'));
  sum.append(archiveNode('span',d.trades+' operações · '+d.wins+' WIN / '+d.losses+' LOSS / '+d.draws+' EMPATE'));
  sum.append(archiveNode('span','Resultado do dia: '+formatArchiveMoney(d.profit),'archive-balance'));
  block.append(sum);
  const list=archiveNode('div',undefined,'archive-operations');
  for(const trade of (d.operations||[])){
   const line=archiveNode('div',undefined,'archive-operation');
   const first=archiveNode('div');
   first.append(archiveNode('strong',trade.asset+' · '+trade.direction));
   first.append(archiveNode('small',trade.time+' · Ordem '+trade.order_id));
   line.append(first);
   line.append(archiveNode('strong',trade.status+' · '+formatArchiveMoney(trade.profit),trade.status==='WIN'?'archive-win':trade.status==='LOSS'?'archive-loss':'archive-draw'));
   list.append(line);
  }
  block.append(list);
  root.append(block);
 }
}
async function refreshArchive(){
 if(archiveBusy)return;
 archiveBusy=true;
 archiveEl('loadArchive').disabled=true;
 archiveEl('archiveInfo').textContent='Consultando gravações no Supabase...';
 try{
  const res=await fetch('/api/history',{credentials:'same-origin',cache:'no-store'});
  const data=await res.json();
  if(!res.ok)throw Error(data.error||'Histórico indisponível; conecte sua conta PRACTICE.');
  if(!data.enabled){
   archiveData=null;displayArchive();
   archiveEl('archiveInfo').textContent='Supabase ainda não conectado no Render. A gravação só funcionará quando as credenciais privadas forem configuradas.';
   return;
  }
  archiveData=data;
  archiveLoadedForSession=true;
  const picker=archiveEl('archiveDate'),chosen=picker.value;
  picker.replaceChildren(archiveNode('option','Todas as datas'));
  picker.firstElementChild.value='';
  for(const day of (data.days||[])){const option=archiveNode('option',formatArchiveDay(day.date));option.value=day.date;picker.append(option);}
  picker.value=(data.days||[]).some(x=>x.date===chosen)?chosen:'';
  displayArchive();
  archiveEl('archiveInfo').textContent=(data.days||[]).length?'Histórico carregado do Supabase.'+(data.truncated?' Mostrando até 10.000 operações recentes.':''):'Banco conectado. Ainda não há operações confirmadas gravadas nesta conta.';
 }catch(e){
  archiveData=null;displayArchive();
  archiveEl('archiveInfo').textContent='Erro ao carregar o histórico: '+(e.message||'falha desconhecida');
 }finally{archiveBusy=false;archiveEl('loadArchive').disabled=false;}
}
archiveEl('loadArchive').addEventListener('click',refreshArchive);
archiveEl('archiveDate').addEventListener('change',displayArchive);
archiveEl('tabSettings').addEventListener('click',()=>{if(lastState.connected)refreshArchive();});

</script><script>(function(){const v=document.getElementById('gladiatorVideo'),f=document.querySelector('.gladiator-frame');if(!v||!f)return;v.addEventListener('loadeddata',()=>{f.classList.add('video-ready');const p=v.play();if(p&&p.catch)p.catch(()=>{});});v.addEventListener('error',()=>{f.classList.remove('video-ready');if(!v.dataset.fallback){v.dataset.fallback='1';v.src='/assets/gladiador_bot.mp4';v.load();const p=v.play();if(p&&p.catch)p.catch(()=>{});}});})();</script><script>(function(){const v=document.getElementById("xtremeLogoVideo");if(!v)return;const wrap=v.closest(".xtreme-logo-wrap");const show=()=>wrap&&wrap.classList.add("logo-playing");const hide=()=>wrap&&wrap.classList.remove("logo-playing");v.muted=true;v.addEventListener("playing",show);v.addEventListener("error",hide);v.addEventListener("stalled",hide);if(v.readyState>=2&&!v.paused)show();const p=v.play();if(p&&typeof p.catch==="function")p.catch(hide);})();</script></body></html>'''
ROOT=Path(__file__).resolve().parent.parent
sessions={}
guard=threading.RLock()
def respond(start,status,data,headers=None):
    raw=json.dumps(data).encode()
    start(status,[('Content-Type','application/json'),('Content-Length',str(len(raw))),('Cache-Control','no-store')]+(headers or []))
    return [raw]
def proc_call(proc,data,timeout=50):
    proc.stdin.write(json.dumps(data)+'\n');proc.stdin.flush()
    ready,_,_=select.select([proc.stdout],[],[],timeout)
    if not ready:raise RuntimeError('Bullex não respondeu no tempo limite')
    line=proc.stdout.readline()
    if not line:raise RuntimeError('Conexão com worker encerrada')
    result=json.loads(line)
    if not result.get('ok'):raise RuntimeError(result.get('error','Falha no conector'))
    return result['data']
def state_view(v):
    if not v:return {'connected':False}
    return {k:v.get(k) for k in ('broker','balance','currency','running','pending','message','phase','current_asset','current_direction','current_order_id','entry_ts','expire_ts','wins','losses','orders','profit','signals','markets','ready','last_signal','last_order','last_result','rejections','last_rejection_reason','research_summary','archive_last_saved','stop_reason')}|{'connected':True,'executor_connected':bool(v.get('executor')),'settings':{'stop_loss':v['stop_loss'],'stop_win':v['stop_win'],'max_orders':v['max_orders'],'expiration_minutes':v.get('expiration_minutes',1)}}
def app(environ,start_response):
    path=urlparse(environ.get('PATH_INFO','/')).path
    method=environ.get('REQUEST_METHOD','GET')
    cookie=SimpleCookie()
    try:cookie.load(environ.get('HTTP_COOKIE',''))
    except Exception:pass
    sid=cookie.get('xb_session')
    token=sid.value if sid else None
    with guard: current=sessions.get(token)
    if path=='/assets/xtreme_tiger_logo_animada.mp4':
        logo_video=Path(__file__).resolve().parent/'xtreme_tiger_logo_animada.mp4'
        if not logo_video.is_file():
            start_response('404 Not Found',[('Content-Type','text/plain'),('Content-Length','0')]);return [b'']
        logo_bytes=logo_video.read_bytes()
        start_response('200 OK',[('Content-Type','video/mp4'),('Content-Length',str(len(logo_bytes))),('Cache-Control','public, max-age=86400'),('Accept-Ranges','none')])
        return [logo_bytes]
    if path=='/assets/xtreme_tiger_logo.webp':
        logo_file=Path(__file__).resolve().parent/'xtreme_tiger_logo.webp'
        if not logo_file.is_file():
            start_response('404 Not Found',[('Content-Type','text/plain'),('Content-Length','0')]);return [b'']
        logo_data=logo_file.read_bytes()
        start_response('200 OK',[('Content-Type','image/webp'),('Content-Length',str(len(logo_data))),('Cache-Control','public, max-age=86400')])
        return [logo_data]
    if path=='/assets/tigre_binoculos.mp4':
        video_file=Path(__file__).resolve().parent/'tigre_binoculos.mp4'
        if not video_file.is_file():
            start_response('404 Not Found',[('Content-Type','text/plain'),('Content-Length','0')]);return [b'']
        data=video_file.read_bytes()
        start_response('200 OK',[('Content-Type','video/mp4'),('Content-Length',str(len(data))),('Cache-Control','public, max-age=300'),('Accept-Ranges','none')])
        return [data]
    if path=='/assets/gladiador_bot.mp4':
        video_file=Path(__file__).resolve().parent/'gladiador_bot.mp4'
        if not video_file.is_file():
            start_response('404 Not Found',[('Content-Type','text/plain'),('Content-Length','0')]);return [b'']
        data=video_file.read_bytes()
        start_response('200 OK',[('Content-Type','video/mp4'),('Content-Length',str(len(data))),('Cache-Control','public, max-age=3600'),('Accept-Ranges','none')])
        return [data]
    if path=='/assets/tiger_binoculars.webp':
        data=(Path(__file__).resolve().parent/'tiger_binoculars.webp').read_bytes()
        start_response('200 OK',[('Content-Type','image/webp'),('Content-Length',str(len(data))),('Cache-Control','public, max-age=3600')])
        return [data]
    if path=='/health':return respond(start_response,'200 OK',{'ok':True,'orders_enabled':False,'supabase_archive_configured':configured()})
    if path=='/api/state':
        if current:current['last_seen']=time.time()
        return respond(start_response,'200 OK',state_view(current))
    if path=='/api/history':
        if not current:return respond(start_response,'401 Unauthorized',{'error':'Conecte a corretora em PRACTICE'})
        try:return respond(start_response,'200 OK',{'enabled':configured(),**history(current.get('archive_account'))})
        except Exception:return respond(start_response,'503 Service Unavailable',{'enabled':configured(),'days':[],'error':'Falha ao consultar gravações no Supabase. Verifique as credenciais do Render e tente novamente.'})
    if path=='/':
        data=HTML.encode()
        start_response('200 OK',[('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(data))),('Cache-Control','no-store')])
        return [data]
    if method=='POST' and path in ('/api/connect','/api/disconnect','/api/prepare','/api/start','/api/stop','/api/settings'):
        origin=environ.get('HTTP_ORIGIN','')
        host=environ.get('HTTP_HOST','')
        if origin and origin not in ('https://'+host,'http://'+host):return respond(start_response,'403 Forbidden',{'error':'Origem inválida'})
        if path=='/api/settings':
            if not current:return respond(start_response,'401 Unauthorized',{'error':'Conecte à PRACTICE primeiro'})
            if current['running'] or current['pending']:return respond(start_response,'409 Conflict',{'error':'Pare o robô e conclua a ordem antes de alterar os stops'})
            try:
                size=int(environ.get('CONTENT_LENGTH') or 0)
                if size<=0 or size>1024:raise ValueError('Configuração inválida')
                values=json.loads(environ['wsgi.input'].read(size))
                sl=values.get('stop_loss');sw=values.get('stop_win');mo=values.get('max_orders');em=values.get('expiration_minutes',1)
                if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not 2<=x<=500 for x in (sl,sw)):raise ValueError('Stops entre US$ 2 e US$ 500')
                if isinstance(mo,bool) or not isinstance(mo,int) or not 10<=mo<=1000:raise ValueError('Máximo de operações entre 10 e 1000')
                if isinstance(em,bool) or not isinstance(em,int) or em not in (1,2,3,5):raise ValueError('Expiração permitida: M1, M2, M3 ou M5')
                current['stop_loss']=round(float(sl),2);current['stop_win']=round(float(sw),2);current['max_orders']=mo;current['expiration_minutes']=em;current['stop_reason']=None
                return respond(start_response,'200 OK',state_view(current))
            except (ValueError,TypeError) as exc:return respond(start_response,'400 Bad Request',{'error':str(exc) if str(exc) else 'Configuração inválida'})
        if path in ('/api/start','/api/stop'):
            if not current or not current.get('executor'):return respond(start_response,'409 Conflict',{'error':'Executor PRACTICE desconectado'})
            if path=='/api/stop':
                current['running']=False;current['stop'].set();current['phase']='stopped';current['message']='Parada solicitada. Ordem já enviada continuará em confirmação.'
                return respond(start_response,'200 OK',state_view(current))
            if current['running']:return respond(start_response,'200 OK',state_view(current))
            if current['pending'] or current.get('uncertain'):return respond(start_response,'409 Conflict',{'error':'Há ordem anterior incerta; confira a corretora selecionada'})
            if current['orders']>=current['max_orders'] or current['profit']<=-current['stop_loss'] or current['profit']>=current['stop_win']:
                return respond(start_response,'409 Conflict',{'error':'Limite ou stop da sessão atingido; conecte nova sessão PRACTICE para reiniciar o placar'})
            current['stop_reason']=None
            current['stop']=threading.Event();current['running']=True;current['message']='Preparando catálogo PRACTICE'
            def ccall(mode,command,timeout=50):
                with current['exec_lock'] if mode=='exec' else current['read_lock']:
                    return proc_call(current['executor'] if mode=='exec' else current['proc'],command,timeout)
            threading.Thread(target=run_bot,args=(current,ccall),daemon=True).start()
            return respond(start_response,'200 OK',state_view(current))
        if path=='/api/prepare':
            if not current or not current.get('executor'):return respond(start_response,'409 Conflict',{'error':'Executor DEMO desconectado'})
            try:
                with current['exec_lock']:result=proc_call(current['executor'],{'op':'demo_prepare'},timeout=25)
                return respond(start_response,'200 OK',result)
            except Exception:return respond(start_response,'503 Service Unavailable',{'error':'Pré-validação PRACTICE falhou; nenhuma ordem enviada'})
        if path=='/api/disconnect':
            if current and (current.get('running') or current.get('pending')):return respond(start_response,'409 Conflict',{'error':'Pare o robô e aguarde a liquidação da ordem antes de trocar de corretora'})
            with guard:
                old=sessions.pop(token,None)
                if old:
                    old['running']=False;old['stop'].set()
                    old['proc'].terminate()
                    if old.get('executor'):old['executor'].terminate()
            return respond(start_response,'200 OK',{'connected':False},[('Set-Cookie','xb_session=; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Path=/')])
        try:
            size=int(environ.get('CONTENT_LENGTH') or 0)
            if size>3000 or size<=0:raise ValueError('Dados inválidos')
            data=json.loads(environ['wsgi.input'].read(size))
            email=str(data.get('email','')).strip()
            pwd=str(data.get('password',''))
            chosen=str(data.get('broker','bullex')).strip().lower()
            if chosen not in ('bullex','iqoption'):raise ValueError('Selecione Bullex ou IQ Option')
            if current:raise ValueError('Desconecte a corretora atual antes de conectar outra')
            if not email or len(email)>254 or not pwd or len(pwd)>256:raise ValueError('Informe e-mail e senha válidos')
            with guard:
                # Reclaim idle, disconnected sessions; never interrupt an active order.
                stale=[k for k,v in sessions.items() if not v.get('running') and not v.get('pending') and time.time()-v.get('last_seen',0)>1800]
                for k in stale:
                    old_session=sessions.pop(k)
                    for p in (old_session.get('proc'),old_session.get('executor')):
                        if p:
                            try:p.terminate()
                            except Exception:pass
                if len(sessions)>=8:raise RuntimeError('Limite de sessões simultâneas. Desconecte abas antigas e tente novamente.')
            reader_path='iq_worker.py' if chosen=='iqoption' else 'worker.py'
            executor_path='iq_executor_worker.py' if chosen=='iqoption' else 'executor_worker.py'
            proc=subprocess.Popen([sys.executable,str(ROOT/reader_path)],cwd=str(ROOT),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
            try:
                answer=proc_call(proc,{'op':'connect','email':email,'password':pwd})
                if answer.get('mode')!='PRACTICE':raise RuntimeError('Somente PRACTICE é permitida')
                executor=None
                try:
                    executor=subprocess.Popen([sys.executable,str(ROOT/executor_path)],cwd=str(ROOT),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
                    check=proc_call(executor,{'op':'connect','email':email,'password':pwd},timeout=48)
                    if check.get('mode')!='PRACTICE':raise RuntimeError('Executor não confirmou conta DEMO')
                except Exception:
                    if executor:executor.terminate()
                    executor=None
                new=secrets.token_urlsafe(32)
                with guard:sessions[new]={'broker':chosen,'proc':proc,'executor':executor,'exec_lock':threading.Lock(),'read_lock':threading.Lock(),'order_lock':threading.Lock(),'stop':threading.Event(),'running':False,'pending':False,'uncertain':False,'message':'Conectado à PRACTICE','phase':'idle','current_asset':'','current_direction':'','current_order_id':'','entry_ts':0,'expire_ts':0,'stake':2,'max_orders':10,'expiration_minutes':1,'stop_loss':10,'stop_win':20,'profit':0.,'wins':0,'losses':0,'orders':0,'signals':0,'seen':set(),'markets':0,'ready':0,'balance':answer.get('balance'),'currency':answer.get('currency'),'archive_account':account_id(chosen+':'+email.strip().lower()),'last_seen':time.time()}
                return respond(start_response,'200 OK',state_view(sessions[new]),[('Set-Cookie','xb_session='+new+'; HttpOnly; Secure; SameSite=Strict; Path=/')])
            except Exception:
                proc.terminate()
                raise
        except (RuntimeError,ValueError,KeyError) as e:return respond(start_response,'400 Bad Request',{'error':str(e)})
        except Exception:return respond(start_response,'502 Bad Gateway',{'error':'Falha na autenticação da corretora selecionada'})
    return respond(start_response,'404 Not Found',{'error':'Não encontrado'})
if __name__=='__main__':
    from wsgiref.simple_server import make_server
    # Render clean service uses this entry point without an external build command.
    subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True,timeout=180)
    subprocess.run([sys.executable,str(ROOT/'bootstrap.py')],cwd=str(ROOT),check=True,timeout=90)
    class ThreadServer(ThreadingMixIn, type(make_server('127.0.0.1',0,app))):daemon_threads=True
    make_server('0.0.0.0',int(os.environ.get('PORT','10000')),app,server_class=ThreadServer).serve_forever()
