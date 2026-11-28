// Scene 5 (payment vs refund role check) on the hosted inspector. Recording-only overlays; no demo code changes.
const {chromium}=require('playwright');const fs=require('fs');
const URL='https://finbot-demo-20852907589.us-central1.run.app/inspector';
const D=JSON.parse(process.env.DURS||'{}');
const marks=[];const mark=n=>marks.push([n,Date.now()/1000]);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
const b=await chromium.launch({headless:false,args:['--window-position=0,0','--window-size=1280,720','--force-device-scale-factor=1.5','--kiosk','--disable-infobars','--hide-scrollbars']});
const ctx=await b.newContext({viewport:null,bypassCSP:true});const p=await ctx.newPage();
await p.goto(URL);await p.waitForSelector('#run');await sleep(1500);
await p.addStyleTag({content:`::-webkit-scrollbar{display:none} #fc{position:fixed;z-index:99999;width:22px;height:22px;border-radius:50%;background:rgba(31,107,79,.35);border:2px solid #1f6b4f;pointer-events:none;transition:left .55s ease,top .55s ease,transform .12s;left:640px;top:400px;transform:translate(-50%,-50%)} #fc.down{transform:translate(-50%,-50%) scale(.7)} .hl{outline:3px solid #e0a526!important;outline-offset:4px;border-radius:6px;transition:outline-color .3s} mark.rk{background:rgba(224,165,38,.28);color:inherit;border-radius:3px;padding:0 2px;transition:background .3s} mark.rk.bad{background:rgba(180,66,58,.18);box-shadow:0 0 0 2px #b4423a} mark.rk.good{background:rgba(31,107,79,.15);box-shadow:0 0 0 2px #1f6b4f}`});
await p.evaluate(()=>{const c=document.createElement('div');c.id='fc';document.body.append(c);});
const moveTo=async sel=>{const bb=await (await p.$(sel)).boundingBox();await p.evaluate(([x,y])=>{const c=document.getElementById('fc');c.style.left=x+'px';c.style.top=y+'px';},[bb.x+bb.width/2,bb.y+bb.height/2]);await sleep(650);};
const click=async sel=>{await moveTo(sel);await p.evaluate(()=>document.getElementById('fc').classList.add('down'));await sleep(120);await p.click(sel);await p.evaluate(()=>document.getElementById('fc').classList.remove('down'));await sleep(250);};
const scrollY=async y=>{await p.evaluate(y=>window.scrollTo({top:y,behavior:'smooth'}),y);await sleep(900);};
const until=async(t0,sec)=>{const left=t0+sec*1000-Date.now();if(left>0)await sleep(left);};
// wrap "Refund amount: X." inside an element in a <mark>
const markText=(sel,cls)=>p.evaluate(([sel,cls])=>{const root=document.querySelector(sel);const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const i=n.data.indexOf('Refund amount:');if(i>=0){const j=n.data.indexOf('.',n.data.indexOf('.',i)+1)+1||n.data.length;const r=document.createRange();r.setStart(n,i);r.setEnd(n,j);const m=document.createElement('mark');m.className='rk '+cls;r.surroundContents(m);return true;}}return false;},[sel,cls]);
const OV=`<div style="font:700 13px Inter,sans-serif;color:#5c727b;letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px">Code checks the role, not just the number</div>
<div style="font:17px/1.5 Inter,sans-serif;color:#16303a">
<div style="color:#5c727b;font-size:14px">Draft</div><div style="font-weight:600">Refund amount: 200.00</div>
<div style="color:#1f6b4f;font-weight:700;margin-top:4px">✓ 200.00 is on the record…</div>
<div style="color:#b4423a;font-weight:700">✗ …as the payment. refund.amount is 50.00</div>
<div style="border-top:1px solid #dfe7e2;margin-top:10px;padding-top:8px;color:#5c727b;font-size:14px">Repair</div><div style="font-weight:600">Refund amount: 50.00 <span style="color:#1f6b4f;font-weight:700">✓ refund.amount</span></div></div>`;
const showOv=on=>p.evaluate(([on,html])=>{let d=document.getElementById('ov');if(on){if(!d){d=document.createElement('div');d.id='ov';d.style.cssText='position:fixed;right:20px;top:120px;width:400px;background:#fff;border:2px solid #e0a526;border-radius:10px;padding:22px 26px;box-shadow:0 10px 30px rgba(0,0,0,.12);z-index:9999;opacity:0;transition:opacity .4s';d.innerHTML=html;document.body.append(d);requestAnimationFrame(()=>d.style.opacity=1);}}else if(d){d.style.opacity=0;setTimeout(()=>d.remove(),450);}},[on,OV]);
// start position: the run form in view
await p.evaluate(()=>window.scrollTo(0,330));await sleep(800);
await p.evaluate(()=>{const d=document.createElement('div');d.id='sync';d.style.cssText='position:fixed;inset:0;background:#ff00ff;z-index:999999';document.body.append(d);});await sleep(100);mark('sync');await sleep(500);await p.evaluate(()=>document.getElementById('sync').remove());await sleep(800);
let t=Date.now();mark('s5');
await sleep(300);await moveTo('#scenario');await p.selectOption('#scenario','refund_role');await p.locator('#scenario').evaluate(e=>e.classList.add('hl'));await sleep(900);
await p.locator('#scenario').evaluate(e=>e.classList.remove('hl'));
await click('#run');await p.waitForSelector('#answer .repaired, #answer',{timeout:15000});await sleep(700);
await scrollY(790);
// draft text
const draftSel='#draft';
await until(t,D.draftAt||4.2);await markText(draftSel,'bad');await moveTo('#draft mark.rk');
await until(t,D.ovIn||6.0);await showOv(true);
await until(t,D.reasonAt||9.0);await showOv(false);
await p.evaluate(()=>{const e=[...document.querySelectorAll('#draft *')].find(x=>x.children.length===0&&/payment amount is not a refund amount/.test(x.textContent));if(e)e.closest('li')?.classList.add('hl')||e.classList.add('hl');});
await until(t,D.answerAt||11.0);await markText('#answer','good');await moveTo('#answer mark.rk');
await until(t,D.s5||16);
mark('end');fs.writeFileSync('marks.json',JSON.stringify(marks));await b.close();})();
