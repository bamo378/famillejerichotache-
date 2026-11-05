// Static server root must contain the checkout directory (GitHub project URL shape).
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try{
 const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));const requests=[];page.on('request',r=>requests.push(r.url()));
 const base=process.env.TEST_BASE_URL||'http://127.0.0.1:8080/famillejerichotache-/';
 await page.goto(base);await page.locator('[data-profile=alice]').click();await page.getByRole('heading',{name:/Coucou Alice/}).waitFor();
 assert.equal(await page.locator('dialog').isVisible(),false);
 await page.locator('[data-task=lit]').click();
 await page.locator('input[type=file]').setInputFiles({name:'proof.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=','base64')});
 await page.locator('#photo-form button').click();await page.locator('[data-task=lit]').filter({hasText:'En attente'}).waitFor();
 await page.reload();await page.locator('[data-task=lit]').filter({hasText:'En attente'}).waitFor();
 await page.locator('#top-logout').click();await page.locator('[data-profile=parent-test]').click();await page.locator('#login-form input').fill('0000');await page.locator('#login-form button').click();await page.locator('#toast').filter({hasText:'Code incorrect'}).waitFor();
 await page.locator('#login-form input').fill('1234');await page.locator('#login-form button').click();await page.locator('[data-page=reviews]').click();await page.locator('.review-photo').waitFor();
 assert.equal(await page.locator('.review-photo').evaluate(img=>img.complete&&img.naturalWidth>0),true);
 await page.locator('[data-approve]').click();await page.getByRole('heading',{name:'Tout est à jour.'}).waitFor();
 await page.locator('[data-page=settings]').click();await page.locator('#money-settings [name=point_value]').fill('0.05');await page.locator('#money-settings button').click();await page.locator('#toast').filter({hasText:'Montants enregistrés.'}).waitFor();
 await page.locator('[data-page=home]').click();await page.locator('#new-task').click();await page.locator('[name=title]').fill('Arroser les fleurs');await page.locator('#task-form button').click();await page.getByText('Arroser les fleurs',{exact:true}).waitFor();
 await page.locator('[data-page=challenges]').click();await page.locator('#new-challenge').click();await page.locator('[name=title]').fill('Défi statique');await page.locator('[name=description]').fill('Ensemble, on range le jardin.');await page.locator('[name=deadline]').fill(await page.evaluate(async()=>(await localApi('session')).today));await page.locator('#challenge-form button').click();await page.getByRole('heading',{name:'Défi statique'}).waitFor();
 await page.locator('#top-logout').click();await page.locator('[data-profile=alice]').click();await page.locator('[data-task=lit]').filter({hasText:'Validée'}).waitFor();
 await page.locator('[data-page=challenges]').click();await page.locator('[data-join]').click();await page.getByRole('button',{name:'Inscrit·e !'}).waitFor();
 await page.locator('#top-logout').click();await page.locator('[data-profile=parent-test]').click();await page.locator('#login-form input').fill('1234');await page.locator('#login-form button').click();await page.locator('[data-page=challenges]').click();await page.locator('[data-win]').click();await page.getByText('✓ Réussi',{exact:true}).waitFor();
 await page.locator('[data-page=money]').click();await page.locator('.money-table').waitFor();assert.match(await page.locator('.money-table').innerText(),/20 pts/);
 for(const size of [{width:390,height:844},{width:768,height:1024},{width:1440,height:1050}]){await page.setViewportSize(size);await page.locator('[data-page=home]').click();assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth>innerWidth),false);}
 // Independent browser: no illusion of cross-device synchronization.
 const other=await browser.newContext();const otherPage=await other.newPage();await otherPage.goto(base);await otherPage.locator('[data-profile=alice]').click();await otherPage.locator('[data-task=lit]').filter({hasText:'Envoyer une photo'}).waitFor();await other.close();
 // Validate the weekly gate and one-time payment on isolated persisted fixtures.
 await page.evaluate(async()=>{
   let blocked=false;
   const current=await localApi('week');
   try{await localApi('payments',{method:'POST',body:{child_id:'alice',week:current.monday}})}catch{blocked=true}
   if(!blocked)throw Error('Incomplete week must not unlock money');
   const shift=(s,n)=>{const d=new Date(s+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)};
   const week=shift(current.monday,-7);
   await new Promise((resolve,reject)=>{
     const open=indexedDB.open('la-tribu:'+new URL('.',location.href).pathname,1);
     open.onsuccess=()=>{const db=open.result,tx=db.transaction('family','readwrite'),store=tx.objectStore('family'),get=store.get('state');get.onsuccess=()=>{const d=get.result;for(let i=0;i<7;i++)for(const task of ['lit','chambre'])d.submissions.push({id:++d.counter,child_id:'alice',task_id:task,day:shift(week,i),status:'approved',awarded:0});store.put(d,'state')};tx.oncomplete=()=>{db.close();resolve()};tx.onerror=()=>reject(tx.error)};
   });
   const completed=await localApi('week?date='+week);
   if(!completed.children[0].eligibility.eligible)throw Error('14 approvals must unlock money');
   await localApi('payments',{method:'POST',body:{child_id:'alice',week}});
   const paid=await localApi('week?date='+week);
   if(paid.children[0].paid.amount!==500)throw Error('Alice allowance must be 500 centimes');
   let duplicate=false;try{await localApi('payments',{method:'POST',body:{child_id:'alice',week}})}catch{duplicate=true}
   if(!duplicate)throw Error('Double payment must be rejected');
 });
 assert.equal(requests.some(url=>new URL(url).pathname.startsWith('/api/')),false);
 assert.deepEqual(errors,[]);console.log('Static Pages OK: nested URL, direct profiles, parent PIN, photos, persistence, approval, tasks, challenges, points, responsive layouts and device isolation.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
