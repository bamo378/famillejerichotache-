import io
import json
import os
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, request, session, render_template, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from accounts import hash_pin, verify_pin
from rewards import weekly_eligibility

Image.MAX_IMAGE_PIXELS = 20_000_000
ROOT = Path(__file__).resolve().parent
CHILDREN = {'alice': 'Alice', 'anaelle': 'Anaëlle', 'tiziano': 'Tiziano'}

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(DATA_DIR=os.environ.get('DATA_DIR',str(ROOT/'data')), MAX_CONTENT_LENGTH=12*1024*1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
    if test_config:
        app.config.update(test_config)
    folder = Path(app.config['DATA_DIR']); folder.mkdir(parents=True, exist_ok=True); folder.chmod(0o700)
    secret_file = folder/'session.key'
    if not secret_file.exists():
        fd = os.open(secret_file, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,'w') as stream: stream.write(secrets.token_hex(32))
    app.secret_key = secret_file.read_text()
    dbpath = folder/'family.sqlite3'
    def db():
        conn = sqlite3.connect(dbpath, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn
    with closing(db()) as conn, conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT,role TEXT,pin_hash TEXT);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT,points INTEGER,category TEXT,frequency TEXT,assignee TEXT,scheduled_date TEXT,active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS submissions(id INTEGER PRIMARY KEY,child_id TEXT,task_id TEXT,day TEXT,status TEXT,photo BLOB,note TEXT DEFAULT '',feedback TEXT DEFAULT '',awarded INTEGER DEFAULT 0,UNIQUE(child_id,task_id,day));
        CREATE TABLE IF NOT EXISTS notices(id INTEGER PRIMARY KEY,recipient TEXT,message TEXT,read INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value INTEGER);
        CREATE TABLE IF NOT EXISTS challenges(id INTEGER PRIMARY KEY,title TEXT,description TEXT,points INTEGER,deadline TEXT);
        CREATE TABLE IF NOT EXISTS challenge_entries(challenge_id INTEGER,child_id TEXT,status TEXT DEFAULT 'joined',PRIMARY KEY(challenge_id,child_id));
        CREATE TABLE IF NOT EXISTS payments(child_id TEXT,week TEXT,amount INTEGER,paid_at TEXT,PRIMARY KEY(child_id,week));
        CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,until REAL);
        ''')
        for uid,name in CHILDREN.items(): conn.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?)',(uid,name,'child',None))
        # The temporary parent is only provisioned in development.
        if os.environ.get('APP_ENV','development') != 'production':
            for profile in json.loads((ROOT/'config/test_profiles.json').read_text())['profiles']:
                conn.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?)',(profile['id'],profile['display_name'],'parent',profile['pin_hash']))
        elif os.environ.get('PARENT_PIN'):
            conn.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?)',('parent','Parents','parent',hash_pin(os.environ['PARENT_PIN'])))
        catalog = json.loads((ROOT/'config/tasks.json').read_text())
        for task in catalog['tasks']:
            conn.execute('INSERT OR IGNORE INTO tasks(id,title,points,category,frequency) VALUES(?,?,?,?,?)',(task['id'],task['title'],task['points'],task['category'],task['frequency']))
        for uid,amount in catalog['allowance']['base_amount_minor_by_child'].items():
            conn.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('base_'+uid,amount))
        conn.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('point_value',0))

    dbpath.chmod(0o600)

    def permitted(user):
        return user and not (os.environ.get('APP_ENV')=='production' and user['id']=='parent-test')

    def today(): return datetime.now(ZoneInfo('Europe/Zurich')).date()
    def notice(conn, recipient, message): conn.execute('INSERT INTO notices(recipient,message) VALUES(?,?)',(recipient,message))
    def parents_notice(conn,message):
        for row in conn.execute("SELECT id FROM users WHERE role='parent'"): notice(conn,row['id'],message)
    def auth(parent=False):
        def decorator(func):
            @wraps(func)
            def wrapped(*args,**kwargs):
                with closing(db()) as conn: user=conn.execute('SELECT * FROM users WHERE id=?',(session.get('uid'),)).fetchone()
                if not permitted(user): abort(401)
                if parent and user['role']!='parent': abort(403)
                if request.method!='GET' and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','!')): abort(403)
                return func(user,*args,**kwargs)
            return wrapped
        return decorator
    def payload(): return request.get_json(silent=True) or {}
    def integer(value, low=0, high=100000):
        if isinstance(value,bool): abort(400, 'Nombre invalide')
        try: result=int(value)
        except (TypeError,ValueError): abort(400,'Nombre invalide')
        if result<low or result>high: abort(400,'Nombre hors limites')
        return result
    def text(value, length=150):
        if not isinstance(value,str) or not value.strip() or len(value)>length: abort(400,'Texte invalide')
        return value.strip()
    def day_value(value):
        try: return date.fromisoformat(value)
        except (ValueError,TypeError): abort(400,'Date invalide')
    def available(task,uid,day):
        if not task['active'] or task['assignee'] not in (None,'',uid): return False
        if task['frequency']=='once': return task['scheduled_date']==day.isoformat()
        # Weekly and as-needed bonus tasks remain optional daily opportunities.
        if task['frequency']=='presence_days': return day.weekday()>=5
        return True

    @app.get('/')
    def index(): return render_template('index.html')

    @app.get('/api/session')
    def current():
        if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(32)
        with closing(db()) as conn:
            profiles=[dict(row) for row in conn.execute('SELECT id,name,role FROM users') if permitted(row)]
            user=next((p for p in profiles if p['id']==session.get('uid')),None)
        return jsonify(user=user,profiles=profiles,csrf=session['csrf'],today=today().isoformat(),development=os.environ.get('APP_ENV','development')!='production')

    @app.post('/api/login')
    def login():
        if not session.get('csrf') or request.headers.get('X-CSRF-Token')!=session.get('csrf'): abort(403)
        data=payload(); uid=data.get('id')
        with closing(db()) as conn, conn:
            user=conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if not permitted(user): abort(401)
            key='login:'+str(request.remote_addr)
            attempt=conn.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
            if attempt and attempt['until']>time.time() and attempt['count']>=5: abort(429,'Trop de tentatives. Réessayez dans 5 minutes.')
            if user['pin_hash'] and not verify_pin(data.get('pin'),user['pin_hash']):
                count=attempt['count']+1 if attempt and attempt['until']>time.time() else 1
                conn.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,time.time()+300))
                conn.commit(); abort(401,'Code incorrect')
            if user['role']=='child' and os.environ.get('APP_ENV')=='production' and not user['pin_hash']:
                abort(403,'Le parent doit définir un code enfant avant la mise en ligne.')
            conn.execute('DELETE FROM attempts WHERE key=?',(key,))
        session.clear(); session.update(uid=uid,csrf=secrets.token_urlsafe(32)); session.permanent=True
        return jsonify(ok=True)

    @app.post('/api/logout')
    @auth()
    def logout(user): session.clear(); return jsonify(ok=True)

    @app.get('/api/week')
    @auth()
    def week(user):
        day=day_value(request.args.get('date',today().isoformat())); monday=day-timedelta(days=day.weekday())
        with closing(db()) as conn:
            tasks=[dict(r) for r in conn.execute('SELECT * FROM tasks WHERE active=1')]
            settings={r['key']:r['value'] for r in conn.execute('SELECT * FROM settings')}
            children=[]
            for uid,name in CHILDREN.items():
                if user['role']!='parent' and uid!=user['id']: continue
                rows=[dict(r) for r in conn.execute('SELECT id,child_id,task_id,day,status,note,feedback,awarded FROM submissions WHERE child_id=? AND day BETWEEN ? AND ?',(uid,monday.isoformat(),(monday+timedelta(days=6)).isoformat()))]
                eligibility=weekly_eligibility(uid,monday.isoformat(),[dict(child_id=r['child_id'],task_id=r['task_id'],date=r['day'],status=r['status']) for r in rows])
                bonus=sum(r['awarded'] for r in rows if r['status']=='approved')
                contest_points=conn.execute("SELECT COALESCE(SUM(c.points),0) FROM challenge_entries e JOIN challenges c ON c.id=e.challenge_id WHERE e.child_id=? AND e.status='approved' AND c.deadline BETWEEN ? AND ?",(uid,monday.isoformat(),(monday+timedelta(days=6)).isoformat())).fetchone()[0]
                bonus+=contest_points
                payment=conn.execute('SELECT * FROM payments WHERE child_id=? AND week=?',(uid,monday.isoformat())).fetchone()
                children.append(dict(id=uid,name=name,submissions=rows,eligibility=eligibility,base=settings['base_'+uid],bonus_points=bonus,bonus_amount=bonus*settings['point_value'],paid=dict(payment) if payment else None))
            claims=[dict(r) for r in conn.execute("SELECT s.task_id,s.day,s.child_id FROM submissions s JOIN tasks t ON t.id=s.task_id WHERE t.category='bonus' AND s.status IN ('submitted','approved') AND s.day BETWEEN ? AND ?",(monday.isoformat(),(monday+timedelta(days=6)).isoformat()))]
            return jsonify(monday=monday.isoformat(),today=today().isoformat(),children=children,tasks=tasks,claims=claims,point_value=settings['point_value'])

    @app.post('/api/submit')
    @auth()
    def submit(user):
        if user['role']!='child': abort(403)
        day=day_value(request.form.get('day'))
        if day>today(): abort(400,'Une tâche future ne peut pas être terminée.')
        if day<today()-timedelta(days=7): abort(400,'Cette date est trop ancienne.')
        photo=request.files.get('photo')
        if not photo: abort(400,'Ajoute une photo de ta tâche.')
        try:
            image=Image.open(photo.stream)
            if image.format not in ('JPEG','PNG','WEBP'): abort(400,'Choisis une photo JPEG, PNG ou WebP.')
            if image.width*image.height>20_000_000: abort(400,'Photo trop grande : maximum 20 mégapixels.')
            image.load(); image=ImageOps.exif_transpose(image); image.thumbnail((1600,1600)); output=io.BytesIO(); image.convert('RGB').save(output,'JPEG',quality=85)
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError): abort(400,'Photo illisible. Choisis une photo JPEG ou PNG.')
        with closing(db()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            week_start=(day-timedelta(days=day.weekday())).isoformat()
            if conn.execute('SELECT 1 FROM payments WHERE child_id=? AND week=?',(user['id'],week_start)).fetchone(): abort(409,'Cette semaine a déjà été versée.')
            task=conn.execute('SELECT * FROM tasks WHERE id=?',(request.form.get('task_id'),)).fetchone()
            if not task or not available(task,user['id'],day): abort(400,'Tâche indisponible')
            old=conn.execute('SELECT status FROM submissions WHERE child_id=? AND task_id=? AND day=?',(user['id'],task['id'],day.isoformat())).fetchone()
            if old and old['status']!='rejected': abort(409,'Cette tâche est déjà envoyée.')
            # Shared bonus task can only be claimed once per day across the family.
            if task['category']=='bonus' and conn.execute("SELECT 1 FROM submissions WHERE task_id=? AND day=? AND child_id!=? AND status IN ('submitted','approved')",(task['id'],day.isoformat(),user['id'])).fetchone(): abort(409,'Cette mission est déjà prise par un autre enfant.')
            conn.execute("INSERT INTO submissions(child_id,task_id,day,status,photo,note) VALUES(?,?,?,'submitted',?,?) ON CONFLICT(child_id,task_id,day) DO UPDATE SET status='submitted',photo=excluded.photo,note=excluded.note,feedback='',awarded=0",(user['id'],task['id'],day.isoformat(),output.getvalue(),request.form.get('note','')[:500]))
            parents_notice(conn,user['name']+' a terminé : '+task['title']+'. Photo à valider !')
        return jsonify(ok=True)

    @app.get('/api/reviews')
    @auth(parent=True)
    def reviews(user):
        with closing(db()) as conn:
            return jsonify([dict(r) for r in conn.execute("SELECT s.id,s.child_id,s.day,s.note,t.title,t.points,u.name FROM submissions s JOIN tasks t ON t.id=s.task_id JOIN users u ON u.id=s.child_id WHERE s.status='submitted' ORDER BY s.id")])

    @app.get('/api/photos/<int:identifier>')
    @auth()
    def photo(user,identifier):
        with closing(db()) as conn: row=conn.execute('SELECT child_id,photo FROM submissions WHERE id=?',(identifier,)).fetchone()
        if not row: abort(404)
        if user['role']!='parent' and row['child_id']!=user['id']: abort(403)
        response=send_file(io.BytesIO(row['photo']),mimetype='image/jpeg')
        response.headers['Cache-Control']='private, no-store'
        return response

    @app.post('/api/reviews/<int:identifier>')
    @auth(parent=True)
    def review(user,identifier):
        data=payload(); status=data.get('status')
        if status not in ('approved','rejected'): abort(400)
        with closing(db()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT s.*,t.points,t.title FROM submissions s JOIN tasks t ON t.id=s.task_id WHERE s.id=?',(identifier,)).fetchone()
            if not row: abort(404)
            if row['status']!='submitted': abort(409,'Cette tâche a déjà été traitée.')
            conn.execute('UPDATE submissions SET status=?,feedback=?,awarded=? WHERE id=?',(status,str(data.get('feedback',''))[:500],row['points'] if status=='approved' else 0,identifier))
            notice(conn,row['child_id'],('Bravo ! Mission validée : ' if status=='approved' else 'À reprendre : ')+row['title']+('. '+str(data.get('feedback',''))[:500] if data.get('feedback') else ''))
        return jsonify(ok=True)

    @app.get('/api/notices')
    @auth()
    def notices(user):
        with closing(db()) as conn: return jsonify([dict(r) for r in conn.execute('SELECT * FROM notices WHERE recipient=? ORDER BY id DESC LIMIT 60',(user['id'],))])

    @app.post('/api/notices/read')
    @auth()
    def read(user):
        with closing(db()) as conn, conn: conn.execute('UPDATE notices SET read=1 WHERE recipient=?',(user['id'],))
        return jsonify(ok=True)

    @app.post('/api/tasks')
    @auth(parent=True)
    def add_task(user):
        data=payload(); title=text(data.get('title')); points=integer(data.get('points'),0,1000)
        frequency=data.get('frequency','daily'); assignee=data.get('assignee') or None
        if frequency not in ('daily','once','presence_days','as_needed') or assignee not in (None,*CHILDREN): abort(400)
        scheduled=day_value(data.get('date')).isoformat() if frequency=='once' else None
        with closing(db()) as conn, conn:
            conn.execute('INSERT INTO tasks(id,title,points,category,frequency,assignee,scheduled_date) VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(8),title,points,'bonus',frequency,assignee,scheduled))
            for uid in CHILDREN:
                if assignee in (None,uid): notice(conn,uid,'Nouvelle mission bonus : '+title)
        return jsonify(ok=True)

    @app.post('/api/tasks/<identifier>/archive')
    @auth(parent=True)
    def archive(user,identifier):
        with closing(db()) as conn, conn:
            row=conn.execute('SELECT category FROM tasks WHERE id=?',(identifier,)).fetchone()
            if not row: abort(404)
            if row['category']=='required': abort(400,'Les deux missions obligatoires doivent rester actives.')
            conn.execute('UPDATE tasks SET active=0 WHERE id=?',(identifier,))
        return jsonify(ok=True)

    @app.post('/api/settings')
    @auth(parent=True)
    def settings(user):
        data=payload()
        with closing(db()) as conn, conn:
            for uid in CHILDREN:
                if uid in data: conn.execute('UPDATE settings SET value=? WHERE key=?',(integer(data[uid]),'base_'+uid))
            if 'point_value' in data: conn.execute('UPDATE settings SET value=? WHERE key=?',(integer(data['point_value'],0,1000),'point_value'))
            if data.get('child_id') in CHILDREN and data.get('pin'):
                try: encoded=hash_pin(data['pin'])
                except ValueError: abort(400,'Le code doit contenir 4 chiffres.')
                conn.execute('UPDATE users SET pin_hash=? WHERE id=?',(encoded,data['child_id']))
        return jsonify(ok=True)

    @app.post('/api/payments')
    @auth(parent=True)
    def pay(user):
        data=payload(); uid=data.get('child_id'); monday=day_value(data.get('week'))
        if uid not in CHILDREN or monday.weekday()!=0: abort(400)
        with closing(db()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=[dict(child_id=r['child_id'],task_id=r['task_id'],date=r['day'],status=r['status']) for r in conn.execute('SELECT * FROM submissions WHERE child_id=? AND day BETWEEN ? AND ?',(uid,monday.isoformat(),(monday+timedelta(days=6)).isoformat()))]
            if not weekly_eligibility(uid,monday.isoformat(),rows)['eligible']: abort(400,'Les 14 missions obligatoires ne sont pas encore validées.')
            if conn.execute("SELECT 1 FROM submissions WHERE child_id=? AND day BETWEEN ? AND ? AND status='submitted'",(uid,monday.isoformat(),(monday+timedelta(days=6)).isoformat())).fetchone(): abort(409,'Validez les missions en attente avant le versement.')
            if conn.execute("SELECT 1 FROM challenge_entries e JOIN challenges c ON c.id=e.challenge_id WHERE e.child_id=? AND e.status='joined' AND c.deadline BETWEEN ? AND ?",(uid,monday.isoformat(),(monday+timedelta(days=6)).isoformat())).fetchone(): abort(409,'Traitez les participations aux défis avant le versement.')
            settings={r['key']:r['value'] for r in conn.execute('SELECT * FROM settings')}
            points=conn.execute("SELECT COALESCE(SUM(awarded),0) FROM submissions WHERE child_id=? AND day BETWEEN ? AND ? AND status='approved'",(uid,monday.isoformat(),(monday+timedelta(days=6)).isoformat())).fetchone()[0]
            points+=conn.execute("SELECT COALESCE(SUM(c.points),0) FROM challenges c JOIN challenge_entries e ON e.challenge_id=c.id WHERE e.child_id=? AND e.status='approved' AND c.deadline BETWEEN ? AND ?",(uid,monday.isoformat(),(monday+timedelta(days=6)).isoformat())).fetchone()[0]
            try: conn.execute('INSERT INTO payments VALUES(?,?,?,?)',(uid,monday.isoformat(),settings['base_'+uid]+points*settings['point_value'],datetime.now(ZoneInfo('Europe/Zurich')).isoformat()))
            except sqlite3.IntegrityError: abort(409,'Versement déjà enregistré.')
            notice(conn,uid,'Ton argent de poche a été marqué comme versé par les parents !')
        return jsonify(ok=True)

    @app.get('/api/challenges')
    @auth()
    def challenges(user):
        with closing(db()) as conn:
            items=[dict(r) for r in conn.execute('SELECT * FROM challenges ORDER BY deadline DESC')]
            for item in items:
                item['entries']=[dict(r) for r in conn.execute('SELECT child_id,status FROM challenge_entries WHERE challenge_id=?',(item['id'],)) if user['role']=='parent' or r['child_id']==user['id']]
            return jsonify(items)

    @app.post('/api/challenges')
    @auth(parent=True)
    def add_challenge(user):
        data=payload(); title=text(data.get('title')); description=text(data.get('description'),1000); deadline=day_value(data.get('deadline'))
        if deadline<today(): abort(400,'Choisis une date à venir.')
        points=integer(data.get('points'),1,1000)
        with closing(db()) as conn, conn:
            conn.execute('INSERT INTO challenges(title,description,points,deadline) VALUES(?,?,?,?)',(title,description,points,deadline.isoformat()))
            for uid in CHILDREN: notice(conn,uid,'Nouveau défi : '+title+' · '+str(points)+' points à gagner !')
        return jsonify(ok=True)

    @app.post('/api/challenges/<int:identifier>/entry')
    @auth()
    def challenge_entry(user,identifier):
        data=payload()
        with closing(db()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            challenge=conn.execute('SELECT * FROM challenges WHERE id=?',(identifier,)).fetchone()
            if not challenge: abort(404)
            if user['role']=='child':
                if challenge['deadline']<today().isoformat(): abort(400,'Ce défi est terminé.')
                cursor=conn.execute("INSERT OR IGNORE INTO challenge_entries VALUES(?,?,'joined')",(identifier,user['id']))
                if cursor.rowcount: parents_notice(conn,user['name']+' participe au défi : '+challenge['title'])
            else:
                uid=data.get('child_id'); status=data.get('status')
                if uid not in CHILDREN or status not in ('approved','rejected'): abort(400)
                challenge_day=day_value(challenge['deadline']); challenge_week=(challenge_day-timedelta(days=challenge_day.weekday())).isoformat()
                if conn.execute('SELECT 1 FROM payments WHERE child_id=? AND week=?',(uid,challenge_week)).fetchone(): abort(409,'Cette semaine a déjà été versée.')
                cursor=conn.execute("UPDATE challenge_entries SET status=? WHERE challenge_id=? AND child_id=? AND status='joined'",(status,identifier,uid))
                if not cursor.rowcount: abort(409,'Participation déjà traitée ou inexistante.')
                notice(conn,uid,('Défi réussi ! +' + str(challenge['points'])+' points : ' if status=='approved' else 'Défi non validé : ')+challenge['title'])
        return jsonify(ok=True)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def error(e): return jsonify(error=e.description),e.code
    return app

if __name__=='__main__':
    create_app().run(host=os.environ.get('HOST','127.0.0.1'),port=int(os.environ.get('PORT','5000')))
