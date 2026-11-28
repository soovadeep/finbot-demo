const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1.5});
for(const n of ['title','results','closing']){await p.goto('file://'+__dirname+'/'+n+'.html');await p.waitForTimeout(300);await p.screenshot({path:n+'.png'});}
await b.close();})();
