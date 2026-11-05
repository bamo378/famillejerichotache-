/* GitHub Pages edition: all family data stays in this browser's IndexedDB. */
'use strict';
window.LOCAL_MODE = true;
(() => {
  const profiles = [
    {id:'alice',name:'Alice',role:'child'},
    {id:'anaelle',name:'Anaëlle',role:'child'},
    {id:'tiziano',name:'Tiziano',role:'child'},
    {id:'parent-test',name:'Parent test',role:'parent'}
  ];
  const scope = new URL('../', document.currentScript.src).pathname;
  const sessionKey = 'tribu-profile:'+scope;
  const now = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich'}).format(new Date());
  const shift = (s,n) => { const d=new Date(s+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10); };
  const monday = s => shift(s,-((new Date(s+'T12:00:00Z').getUTCDay()+6)%7));
  const fail = message => {throw Error(message)};
  const validDay = s => typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!isNaN(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s;
  const number = (v,max=100000) => {const n=Number(v);if(!Number.isInteger(n)||n<0||n>max)fail('Nombre invalide.');return n};
  const text = (v,max=150) => {if(typeof v!=='string'||!v.trim()||v.length>max)fail('Texte invalide.');return v.trim()};
  const database = new Promise((resolve,reject)=>{
    const open=indexedDB.open('la-tribu:'+scope,1);
    open.onupgradeneeded=()=>open.result.createObjectStore('family');
    open.onsuccess=()=>resolve(open.result);
    open.onerror=()=>reject(Error('Le navigateur ne permet pas la sauvegarde locale. Ouvre le site hors navigation privée.'));
  });
  let seedPromise;
  async function seed(){
    if(!seedPromise)seedPromise=fetch(new URL('config/tasks.json',location.href)).then(r=>{if(!r.ok)fail('Catalogue des tâches introuvable.');return r.json()}).then(c=>({
      version:1,tasks:c.tasks.map(t=>({...t,active:1,assignee:null,scheduled_date:null})),
      submissions:[],notices:[],challenges:[],payments:[],settings:{...c.allowance.base_amount_minor_by_child,point_value:0},counter:0
    }));
    return seedPromise;
  }
  async function transaction(write,fn){
    const db=await database,initial=await seed();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('family',write?'readwrite':'readonly'),store=tx.objectStore('family');
      let result,failure;
      const get=store.get('state');
      get.onsuccess=()=>{try{const data=get.result||structuredClone(initial);result=fn(data);if(write)store.put(data,'state')}catch(e){failure=e;tx.abort()}};
      tx.oncomplete=()=>resolve(result);
      tx.onabort=()=>reject(failure||Error('Sauvegarde impossible. Le stockage de cet appareil est peut-être plein.'));
      tx.onerror=()=>{failure=Error('Sauvegarde impossible. Vérifie l’espace disponible sur cet appareil.')};
    });
  }
  function user(){const id=sessionStorage.getItem(sessionKey);return profiles.find(p=>p.id===id)}
  function requireUser(parent=false){const u=user();if(!u)fail('Choisis ton profil.');if(parent&&u.role!=='parent')fail('Cette action est réservée aux parents.');return u}
  function notice(d,id,message){d.notices.push({id:++d.counter,recipient:id,message,read:0})}
  function settled(d,id,day){return d.payments.find(p=>p.child_id===id&&p.week===monday(day))}
  function available(t,id,day){return t&&t.active&&(!t.assignee||t.assignee===id)&&(t.frequency!=='once'||t.scheduled_date===day)&&(t.frequency!=='presence_days'||[0,6].includes(new Date(day+'T12:00:00Z').getUTCDay()))}
  function childWeek(d,id,start){
    const end=shift(start,6),rows=d.submissions.filter(s=>s.child_id===id&&s.day>=start&&s.day<=end);
    const missing=[];
    for(let i=0;i<7;i++)for(const task of ['chambre','lit'])if(!rows.some(s=>s.task_id===task&&s.day===shift(start,i)&&s.status==='approved'))missing.push({date:shift(start,i),task_id:task});
    let points=rows.filter(s=>s.status==='approved').reduce((sum,s)=>sum+s.awarded,0);
    points+=d.challenges.filter(c=>c.deadline>=start&&c.deadline<=end&&c.entries.some(e=>e.child_id===id&&e.status==='approved')).reduce((sum,c)=>sum+c.points,0);
    return {id,name:profiles.find(p=>p.id===id).name,submissions:rows.map(({photo,...s})=>s),eligibility:{eligible:!missing.length,approved_count:14-missing.length,required_count:14,missing},base:d.settings[id],bonus_points:points,bonus_amount:points*d.settings.point_value,paid:d.payments.find(p=>p.child_id===id&&p.week===start)||null};
  }
  async function photoData(file){
    if(!(file instanceof Blob)||!file.size)fail('Ajoute une photo.');
    if(file.size>12*1024*1024)fail('La photo doit faire moins de 12 Mo.');
    if(!['image/jpeg','image/png','image/webp'].includes(file.type))fail('Choisis une photo JPEG, PNG ou WebP.');
    const url=URL.createObjectURL(file);
    try{
      const image=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(Error('Photo illisible.'));img.src=url});
      if(image.width*image.height>20000000)fail('Photo trop grande : maximum 20 mégapixels.');
      const ratio=Math.min(1,1200/Math.max(image.width,image.height)),canvas=document.createElement('canvas');
      canvas.width=Math.max(1,Math.round(image.width*ratio));canvas.height=Math.max(1,Math.round(image.height*ratio));canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
      return canvas.toDataURL('image/jpeg',0.8);
    }finally{URL.revokeObjectURL(url)}
  }
  window.localApi=async function(path,options={}){
    const url=new URL(path,'https://local.invalid/'),route=url.pathname.replace(/^\//,''),method=options.method||'GET',body=options.body||{};
    if(route==='session')return {user:user()||null,profiles,csrf:'local',today:now(),development:true};
    if(route==='login'){
      const p=profiles.find(p=>p.id===body.id);if(!p)fail('Profil introuvable.');
      if(p.role==='parent'){
        const lockKey='tribu-lock:'+scope,lock=JSON.parse(sessionStorage.getItem(lockKey)||'{}');
        if(lock.until>Date.now()&&lock.count>=5)fail('Réessaie dans 5 minutes.');
        if(body.pin!=='1234'){const count=lock.until>Date.now()?(lock.count||0)+1:1;sessionStorage.setItem(lockKey,JSON.stringify({count,until:Date.now()+300000}));fail('Code incorrect.')}
        sessionStorage.removeItem(lockKey);
      }
      sessionStorage.setItem(sessionKey,p.id);return {ok:true};
    }
    if(route==='logout'){sessionStorage.removeItem(sessionKey);return {ok:true}}
    const u=requireUser();
    let photo;
    if(route==='submit')photo=await photoData(body.get('photo'));
    return transaction(method!=='GET',d=>{
      if(route==='week'){
        const day=url.searchParams.get('date')||now();if(!validDay(day))fail('Date invalide.');const start=monday(day),end=shift(start,6);
        return {monday:start,today:now(),tasks:d.tasks.filter(t=>t.active),children:profiles.filter(p=>p.role==='child'&&(u.role==='parent'||u.id===p.id)).map(p=>childWeek(d,p.id,start)),claims:d.submissions.filter(s=>s.day>=start&&s.day<=end&&s.status!=='rejected'&&d.tasks.find(t=>t.id===s.task_id)?.category==='bonus').map(s=>({task_id:s.task_id,day:s.day,child_id:s.child_id})),point_value:d.settings.point_value};
      }
      if(route==='notices')return d.notices.filter(n=>n.recipient===u.id).slice(-60).reverse();
      if(route==='notices/read'){d.notices.filter(n=>n.recipient===u.id).forEach(n=>n.read=1);return {ok:true}}
      if(route==='submit'){
        if(u.role!=='child')fail('Choisis un profil enfant.');const day=body.get('day'),task=d.tasks.find(t=>t.id===body.get('task_id'));
        if(!validDay(day)||day>now()||day<shift(now(),-7))fail('Choisis une date passée de moins de 7 jours ou aujourd’hui.');
        if(!available(task,u.id,day))fail('Mission indisponible.');if(settled(d,u.id,day))fail('Cette semaine a déjà été versée.');
        const previous=d.submissions.find(s=>s.child_id===u.id&&s.task_id===task.id&&s.day===day);
        if(previous&&previous.status!=='rejected')fail('Photo déjà enregistrée.');
        if(task.category==='bonus'&&d.submissions.some(s=>s.task_id===task.id&&s.day===day&&s.child_id!==u.id&&s.status!=='rejected'))fail('Cette mission est déjà prise.');
        const record={id:previous?.id||++d.counter,child_id:u.id,task_id:task.id,day,status:'submitted',photo,note:String(body.get('note')||'').slice(0,500),feedback:'',awarded:0};
        if(previous)Object.assign(previous,record);else d.submissions.push(record);
        notice(d,'parent-test',u.name+' a terminé : '+task.title+'. Photo à valider sur cet appareil.');return {ok:true};
      }
      if(route==='reviews'){
        requireUser(true);return d.submissions.filter(s=>s.status==='submitted').map(s=>({...s,title:d.tasks.find(t=>t.id===s.task_id).title,points:d.tasks.find(t=>t.id===s.task_id).points,name:profiles.find(p=>p.id===s.child_id).name}));
      }
      if(route.startsWith('reviews/')){
        requireUser(true);const s=d.submissions.find(s=>s.id===Number(route.split('/')[1]));
        if(!s||s.status!=='submitted')fail('Cette mission a déjà été traitée.');if(!['approved','rejected'].includes(body.status))fail('Choix invalide.');
        const task=d.tasks.find(t=>t.id===s.task_id);s.status=body.status;s.awarded=s.status==='approved'?task.points:0;s.feedback=String(body.feedback||'').slice(0,500);
        notice(d,s.child_id,(s.status==='approved'?'Bravo ! Mission validée : ':'À reprendre : ')+task.title+(s.feedback?'. '+s.feedback:''));return {ok:true};
      }
      if(route==='tasks'){
        requireUser(true);const title=text(body.title),points=number(body.points,1000),frequency=body.frequency,assignee=body.assignee||null;
        if(!['daily','once','presence_days','as_needed'].includes(frequency)||assignee&&!profiles.some(p=>p.role==='child'&&p.id===assignee))fail('Mission invalide.');
        if(frequency==='once'&&!validDay(body.date))fail('Choisis une date.');
        d.tasks.push({id:'bonus-'+(++d.counter),title,points,category:'bonus',frequency,assignee,scheduled_date:frequency==='once'?body.date:null,active:1});
        profiles.filter(p=>p.role==='child'&&(!assignee||p.id===assignee)).forEach(p=>notice(d,p.id,'Nouvelle mission : '+title));return {ok:true};
      }
      if(/^tasks\/[^/]+\/archive$/.test(route)){
        requireUser(true);const task=d.tasks.find(t=>t.id===route.split('/')[1]);if(!task||task.category==='required')fail('Cette mission doit rester active.');task.active=0;return {ok:true};
      }
      if(route==='settings'){
        requireUser(true);for(const key of ['alice','anaelle','tiziano','point_value'])if(key in body)d.settings[key]=number(body[key],key==='point_value'?1000:100000);return {ok:true};
      }
      if(route==='payments'){
        requireUser(true);if(!profiles.some(p=>p.role==='child'&&p.id===body.child_id)||!validDay(body.week)||monday(body.week)!==body.week)fail('Semaine invalide.');
        const c=childWeek(d,body.child_id,body.week);if(c.paid)fail('Versement déjà enregistré.');if(!c.eligibility.eligible)fail('Les 14 missions obligatoires doivent être validées.');
        if(c.submissions.some(s=>s.status==='submitted')||d.challenges.some(ch=>monday(ch.deadline)===body.week&&ch.entries.some(e=>e.child_id===c.id&&e.status==='joined')))fail('Traite les missions et défis en attente avant le versement.');
        d.payments.push({child_id:c.id,week:body.week,amount:c.base+c.bonus_amount,paid_at:new Date().toISOString()});notice(d,c.id,'Les parents ont marqué ton argent de poche comme versé !');return {ok:true};
      }
      if(route==='challenges'&&method==='GET')return d.challenges.map(ch=>({...ch,entries:ch.entries.filter(e=>u.role==='parent'||e.child_id===u.id)})).reverse();
      if(route==='challenges'){
        requireUser(true);const title=text(body.title),description=text(body.description,1000),points=number(body.points,1000);if(!points||!validDay(body.deadline)||body.deadline<now())fail('Choisis des points et une date à venir.');
        d.challenges.push({id:++d.counter,title,description,points,deadline:body.deadline,entries:[]});profiles.filter(p=>p.role==='child').forEach(p=>notice(d,p.id,'Nouveau défi : '+title+' · '+points+' points !'));return {ok:true};
      }
      if(/^challenges\/\d+\/entry$/.test(route)){
        const ch=d.challenges.find(c=>c.id===Number(route.split('/')[1]));if(!ch)fail('Défi introuvable.');
        if(u.role==='child'){
          if(ch.deadline<now())fail('Ce défi est terminé.');if(settled(d,u.id,ch.deadline))fail('Cette semaine a déjà été versée.');
          if(!ch.entries.some(e=>e.child_id===u.id)){ch.entries.push({child_id:u.id,status:'joined'});notice(d,'parent-test',u.name+' participe au défi : '+ch.title)}
        }else{
          const entry=ch.entries.find(e=>e.child_id===body.child_id);if(!entry||entry.status!=='joined')fail('Participation déjà traitée.');
          if(!['approved','rejected'].includes(body.status))fail('Choix invalide.');if(settled(d,body.child_id,ch.deadline))fail('Cette semaine a déjà été versée.');
          entry.status=body.status;notice(d,entry.child_id,body.status==='approved'?'Défi réussi ! +'+ch.points+' points : '+ch.title:'Défi non validé : '+ch.title);
        }return {ok:true};
      }
      fail('Action indisponible.');
    });
  };
})();
