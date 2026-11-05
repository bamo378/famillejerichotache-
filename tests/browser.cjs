// Run against an isolated development instance, never the family's live database.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base=process.env.TEST_BASE_URL||'http://127.0.0.1:5001';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1050}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  async function login(name,pin=''){
   await page.goto(base);await page.locator('[data-profile="'+name+'"]').click();
   if(pin)await page.locator('#login-form input').fill(pin);
   await page.locator('#login-form button').click();
   await page.locator('.hero').waitFor();
  }
  async function logout(){await page.locator('#top-logout').click();await page.locator('.profiles').waitFor()}
  await login('alice');
  for(const size of [{width:1440,height:1050},{width:390,height:844},{width:768,height:1024}]){
   await page.setViewportSize(size);
   assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth>innerWidth),false,'horizontal overflow at '+size.width);
   if(process.env.SCREENSHOT_DIR)await page.screenshot({path:process.env.SCREENSHOT_DIR+'/week-'+size.width+'.png',fullPage:true});
  }
  await page.setViewportSize({width:1440,height:1050});
  await page.locator('[data-task="lit"]').click();
  // A real small PNG, decoded and converted by the server.
  await page.locator('input[type=file]').setInputFiles({name:'proof.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=','base64')});
  await page.locator('#photo-form button').click();
  await page.locator('[data-task="lit"]').filter({hasText:'En attente'}).waitFor();
  await logout();await login('parent-test','1234');
  await page.locator('[data-page="reviews"]').click();
  await page.locator('[data-approve]').first().click();
  await page.getByRole('heading',{name:'Tout est à jour.'}).waitFor();
  await page.locator('[data-page="challenges"]').click();await page.locator('#new-challenge').click();
  await page.locator('[name=title]').fill('Défi navigateur');
  await page.locator('[name=description]').fill('Un coup de main collectif.');
  await page.locator('#challenge-form button').click();
  await page.getByRole('heading',{name:'Défi navigateur'}).waitFor();
  await page.locator('[data-page="settings"]').click();
  await page.locator('#money-settings [name=point_value]').fill('0.05');
  await page.locator('#money-settings button').click();
  await page.locator('#toast').filter({hasText:'Montants enregistrés.'}).waitFor();
  if(process.env.SCREENSHOT_DIR)await page.screenshot({path:process.env.SCREENSHOT_DIR+'/parents.png',fullPage:true});
  await logout();await login('alice');
  await page.locator('[data-page="challenges"]').click();await page.locator('[data-join]').first().click();
  await page.getByRole('button',{name:'Inscrit·e !'}).waitFor();
  await page.locator('[data-page="home"]').click();
  assert.match(await page.locator('[data-task="lit"]').innerText(),/Validée/);
  await page.locator('[data-page="money"]').click();await page.getByRole('heading',{name:/Mon coffre aux récompenses/}).waitFor();
  await page.locator('[data-page="notices"]').click();await page.locator('#read-all').click();
  assert.deepEqual(errors,[]);
  console.log('Browser OK: desktop, mobile, tablet, photo, parent review, challenge, settings, rewards, notifications.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
