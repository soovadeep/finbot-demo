const {chromium}=require('playwright');const fs=require('fs');
const HEAD=process.env.HEAD==='1';const URL='http://127.0.0.1:8766/';
const D=JSON.parse(process.env.DURS||'{}'); // scene -> seconds
const marks=[];const mark=n=>{marks.push([n,Date.now()/1000]);};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
const b=await chromium.launch(HEAD?{headless:false,args:['--window-position=0,0','--window-size=1280,807','--force-device-scale-factor=1.5','--kiosk','--disable-infobars','--hide-scrollbars']}:{});
const ctx=await b.newContext(HEAD?{viewport:null,bypassCSP:true}:{viewport:{width:1280,height:720},bypassCSP:true});const p=await ctx.newPage();
const prep=async()=>{await p.addStyleTag({content:`::-webkit-scrollbar{display:none} #fc{position:fixed;z-index:99999;width:22px;height:22px;border-radius:50%;background:rgba(31,107,79,.35);border:2px solid #1f6b4f;pointer-events:none;transition:left .55s ease,top .55s ease,transform .12s;left:640px;top:400px;transform:translate(-50%,-50%)} #fc.down{transform:translate(-50%,-50%) scale(.7)} .hl{outline:3px solid #e0a526!important;outline-offset:4px;border-radius:6px;transition:outline-color .3s}`});
 await p.evaluate(()=>{const c=document.createElement('div');c.id='fc';document.body.append(c);});};
const moveTo=async sel=>{const bb=await (await p.$(sel)).boundingBox();await p.evaluate(([x,y])=>{const c=document.getElementById('fc');c.style.left=x+'px';c.style.top=y+'px';},[bb.x+bb.width/2,bb.y+bb.height/2]);await sleep(650);};
const click=async sel=>{await moveTo(sel);await p.evaluate(()=>document.getElementById('fc').classList.add('down'));await sleep(120);await p.click(sel);await p.evaluate(()=>document.getElementById('fc').classList.remove('down'));await sleep(250);};
const scrollTo=async(sel,off=90)=>{await p.evaluate(([s,o])=>{const e=document.querySelector(s);window.scrollTo({top:e.getBoundingClientRect().top+window.scrollY-o,behavior:'smooth'});},[sel,off]);await sleep(900);};
const scrollY=async y=>{await p.evaluate(y=>window.scrollTo({top:y,behavior:'smooth'}),y);await sleep(900);};
const type=async(sel,t)=>{await click(sel);await p.fill(sel,'');await p.type(sel,t,{delay:55});await sleep(300);};
const hl=async(sel,on=true)=>p.evaluate(([s,o])=>document.querySelector(s).classList.toggle('hl',o),[sel,on]);
const until=async(t0,sec)=>{const left=t0+sec*1000-Date.now();if(left>0)await sleep(left);};
const dump=async l=>{if(!HEAD)console.log('--',l,'|',(await p.$eval('#chat-messages',e=>e.innerText)).replace(/\s+/g,' ').slice(-260));};
await p.goto(URL);await p.waitForSelector('#message-send:not([disabled])');await prep();await p.evaluate(()=>document.getElementById('customer-message').removeAttribute('required'));await sleep(1500);
await p.evaluate(()=>{const d=document.createElement('div');d.id='sync';d.style.cssText='position:fixed;inset:0;background:#ff00ff;z-index:999999';document.body.append(d);});await sleep(100);mark('sync');await sleep(500);await p.evaluate(()=>document.getElementById('sync').remove());await sleep(800);
// Scene 1 (demo part): empty page, slow scroll to chat
let t=Date.now();mark('s1');
await sleep(1200);await scrollTo('.chat-panel',20);await until(t,D.s1||3);
// Scene 2
t=Date.now();mark('s2');
await scrollY(0);await moveTo('#conversation-fault');await p.selectOption('#conversation-fault','amount_always');await sleep(400);
await scrollTo('.chat-panel',20);await click('#customer-message');await p.fill('#customer-message','');await sleep(D.typeAt?Math.max(0,D.typeAt*1000-(Date.now()-t)):0);await p.type('#customer-message',"My $200 payment hasn't arrived. When will it get there?",{delay:60});await until(t,D.sendAt||0);await click('#message-send');await sleep(900);await dump('s2');
await sleep(1500);
await scrollTo('#belief-inspector',20);await click('#belief-inspector summary');await sleep(800);
await scrollTo('#belief-inspector',20);await sleep(2500);
await scrollTo('#conversation-scores',40);await hl('#conversation-scores');
await until(t,(D.s2||3)-1.6);await hl('#conversation-scores',false);await scrollTo('#conversation-options',260);await moveTo('#conversation-options button:nth-child(2)');await until(t,D.s2||3);
// Scene 3
t=Date.now();mark('s3');
await click('#conversation-options button:has-text("ank transfer")');await sleep(1100);await dump('s3a');
await scrollTo('#message-form',330);await type('#customer-message','Willow Repairs');await click('#message-send');await sleep(1000);await dump('s3b');
await scrollTo('#confirmation',200);await hl('#matching-records');await sleep(1500);await hl('#matching-records',false);
await moveTo('#matching-records button');await until(t,(D.s3||3)-0.8);await click('#matching-records button');await until(t,D.s3||3);
// Scene 4
t=Date.now();mark('s4');
const OV=`<div style="font:700 15px Inter,sans-serif;color:#5c727b;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px">Code checks the draft against the record</div>
<table style="width:100%;border-collapse:collapse;font:19px Inter,sans-serif;color:#16303a">
<tr style="color:#5c727b;font-size:15px"><td style="padding:4px 0">Claim in draft</td><td>In the fetched record?</td></tr>
<tr><td style="padding:7px 0;border-top:1px solid #dfe7e2">200.00 USD</td><td style="border-top:1px solid #dfe7e2;color:#1f6b4f;font-weight:700">✓ amount 200.00 USD</td></tr>
<tr><td style="padding:7px 0;border-top:1px solid #dfe7e2">pending</td><td style="border-top:1px solid #dfe7e2;color:#1f6b4f;font-weight:700">✓ status pending</td></tr>
<tr><td style="padding:7px 0;border-top:1px solid #dfe7e2">expected 2026-11-18</td><td style="border-top:1px solid #dfe7e2;color:#1f6b4f;font-weight:700">✓ expected date, which was asked</td></tr>
<tr><td style="padding:7px 0;border-top:1px solid #dfe7e2">fee of 12.34</td><td style="border-top:1px solid #dfe7e2;color:#b4423a;font-weight:700">✗ no such amount → rejected</td></tr></table>`;
const showOv=on=>p.evaluate(([on,html])=>{let d=document.getElementById('ov');if(on){if(!d){d=document.createElement('div');d.id='ov';d.style.cssText='position:fixed;left:24px;top:110px;width:640px;background:#fff;border:2px solid #e0a526;border-radius:10px;padding:22px 26px;box-shadow:0 10px 30px rgba(0,0,0,.12);z-index:9999;opacity:0;transition:opacity .4s';d.innerHTML=html;document.body.append(d);requestAnimationFrame(()=>d.style.opacity=1);}}else if(d){d.style.opacity=0;setTimeout(()=>d.remove(),450);}},[on,OV]);
if(D.ovIn){setTimeout(()=>showOv(true),D.ovIn*1000-(Date.now()-t));setTimeout(()=>showOv(false),D.ovOut*1000-(Date.now()-t));}
await sleep(300);await scrollTo('#answer-check',20);
const k=(D.a4||22.37)/22.37;const sched=D.sched||[[1,0.9,5.0*k],[2,5.0*k,13.0*k],[3,13.0*k,19.0*k]];
for(const [i,a,z] of sched){await until(t,a);await hl(`#answer-steps li:nth-child(${i})`);await until(t,z);await hl(`#answer-steps li:nth-child(${i})`,false);}
await hl('#answer-steps li:nth-child(4)');await hl('#answer-result');await until(t,D.s4||3);await hl('#answer-steps li:nth-child(4)',false);await hl('#answer-result',false);
// Scene 5: correction
t=Date.now();mark('s5');
await p.selectOption('#conversation-scenario','correction');await p.selectOption('#conversation-fault','none');await sleep(300);
await scrollTo('.chat-panel',20);await click('#message-send');await sleep(500);await click('#matching-records button');await sleep(600);
await scrollTo('#message-form',330);await click('#customer-message');await p.type('#customer-message','Actually, it was a card payment on November 16.',{delay:22});await click('#message-send');await sleep(700);
await scrollTo('#confirmation',260);await until(t,D.s5||3);
mark('end');fs.writeFileSync(process.env.MARKS||(__dirname+'/marks.json'),JSON.stringify(marks));await b.close();})();
