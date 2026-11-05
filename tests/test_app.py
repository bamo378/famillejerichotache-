import io
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
from PIL import Image
from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'APP_ENV':'development'}); self.env.start(); self.addCleanup(self.env.stop)
        self.app=create_app({'TESTING':True,'DATA_DIR':self.temp.name})
        self.client=self.app.test_client()
        self.today=datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()

    def login(self,uid='alice',pin=''):
        csrf=self.client.get('/api/session').json['csrf']
        response=self.client.post('/api/login',json={'id':uid,'pin':pin},headers={'X-CSRF-Token':csrf})
        self.assertEqual(response.status_code,200,response.json)
        self.csrf=self.client.get('/api/session').json['csrf']

    def post(self,path,data=None):
        return self.client.post('/api/'+path,json=data or {},headers={'X-CSRF-Token':self.csrf})

    def submit(self,task='lit',day=None,raw=None):
        output=io.BytesIO(); Image.new('RGB',(30,30),'green').save(output,'JPEG'); output.seek(0)
        return self.client.post('/api/submit',data={'task_id':task,'day':day or self.today,'photo':(io.BytesIO(raw) if raw else output,'proof.jpg')},headers={'X-CSRF-Token':self.csrf})

    def test_photo_approval_and_private_access(self):
        self.login(); self.assertEqual(self.submit().status_code,200)
        self.assertEqual(self.submit().status_code,409)
        self.assertEqual(self.client.get('/api/reviews').status_code,403)
        self.login('anaelle'); self.assertEqual(self.client.get('/api/photos/1').status_code,403)
        self.login('parent-test','1234')
        self.assertEqual(len(self.client.get('/api/reviews').json),1)
        self.assertEqual(self.client.get('/api/photos/1').mimetype,'image/jpeg')
        self.assertEqual(self.post('reviews/1',{'status':'approved'}).status_code,200)
        self.assertEqual(self.post('reviews/1',{'status':'approved'}).status_code,409)
        self.login(); c=self.client.get('/api/week').json['children'][0]
        self.assertEqual(c['eligibility']['approved_count'],1)
        self.assertTrue(self.client.get('/api/notices').json)

    def test_bonus_shared_and_awarded_once(self):
        self.login(); self.assertEqual(self.submit('vider-lave-vaisselle').status_code,200)
        self.login('tiziano'); self.assertEqual(self.submit('vider-lave-vaisselle').status_code,409)
        self.login('parent-test','1234'); self.post('reviews/1',{'status':'approved'})
        self.login(); self.assertEqual(self.client.get('/api/week').json['children'][0]['bonus_points'],10)

    def test_rejection_and_resubmission(self):
        self.login(); self.submit()
        self.login('parent-test','1234'); self.post('reviews/1',{'status':'rejected','feedback':'À reprendre'})
        self.login(); self.assertEqual(self.submit().status_code,200)
        c=self.client.get('/api/week').json['children'][0]
        self.assertEqual(c['submissions'][0]['status'],'submitted')
        self.assertEqual(c['eligibility']['approved_count'],0)

    def test_invalid_photo_future_day_and_csrf(self):
        self.assertEqual(self.client.get('/api/week').status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'id':'alice'}).status_code,403)
        self.login()
        self.assertEqual(self.submit(raw=b'fake image').status_code,400)
        future=(datetime.now(ZoneInfo('Europe/Zurich')).date()+timedelta(days=1)).isoformat()
        self.assertEqual(self.submit(day=future).status_code,400)
        self.assertEqual(self.client.post('/api/logout').status_code,403)
        self.assertEqual(self.post('settings',{'alice':999}).status_code,403)

    def test_parent_rate_limit(self):
        csrf=self.client.get('/api/session').json['csrf']
        for _ in range(5):
            self.assertEqual(self.client.post('/api/login',json={'id':'parent-test','pin':'0000'},headers={'X-CSRF-Token':csrf}).status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'id':'parent-test','pin':'1234'},headers={'X-CSRF-Token':csrf}).status_code,429)

    def test_tasks_challenge_settings_and_children_pins(self):
        self.login('parent-test','1234')
        self.assertEqual(self.post('tasks',{'title':'Arroser','points':15,'frequency':'daily','assignee':'alice'}).status_code,200)
        self.assertEqual(self.post('challenges',{'title':'Jardin','description':'Ensemble','points':20,'deadline':self.today}).status_code,200)
        self.assertEqual(self.post('settings',{'point_value':5,'child_id':'alice','pin':'5678'}).status_code,200)
        self.login('alice','5678')
        self.assertEqual(self.post('challenges/1/entry').status_code,200)
        self.login('parent-test','1234')
        self.assertEqual(self.post('challenges/1/entry',{'child_id':'alice','status':'approved'}).status_code,200)
        self.assertEqual(self.post('challenges/1/entry',{'child_id':'alice','status':'approved'}).status_code,409)
        child=self.client.get('/api/week').json['children'][0]
        self.assertEqual(child['bonus_amount'],100)

    def test_allowance_gate_and_idempotent_payment(self):
        self.login('parent-test','1234')
        monday=self.client.get('/api/week').json['monday']
        self.assertEqual(self.post('payments',{'child_id':'alice','week':monday}).status_code,400)
        # Persist a complete previous week, as if reviewed by the parents.
        from datetime import date
        previous=(date.fromisoformat(monday)-timedelta(days=7)).isoformat()
        conn=sqlite3.connect(self.temp.name+'/family.sqlite3')
        for offset in range(7):
            day=(date.fromisoformat(previous)+timedelta(days=offset)).isoformat()
            for task in ('lit','chambre'):
                conn.execute("INSERT INTO submissions(child_id,task_id,day,status,photo) VALUES(?,?,?,'approved',?)",('alice',task,day,b'photo'))
        conn.commit();conn.close()
        self.assertEqual(self.post('payments',{'child_id':'alice','week':previous}).status_code,200)
        self.assertEqual(self.post('payments',{'child_id':'alice','week':previous}).status_code,409)
        week=self.client.get('/api/week?date='+previous).json
        self.assertEqual(week['children'][0]['paid']['amount'],500)

    def test_production_excludes_temporary_parent_and_requires_child_pin(self):
        # Even an existing development database cannot authenticate the test parent.
        self.env.stop()
        with patch.dict(os.environ, {'APP_ENV':'production','PARENT_PIN':'9876'}):
            production=create_app({'TESTING':True,'DATA_DIR':self.temp.name})
            client=production.test_client()
            current=client.get('/api/session').json
            self.assertNotIn('parent-test',[p['id'] for p in current['profiles']])
            token={'X-CSRF-Token':current['csrf']}
            self.assertEqual(client.post('/api/login',json={'id':'parent-test','pin':'1234'},headers=token).status_code,401)
            self.assertEqual(client.post('/api/login',json={'id':'alice'},headers=token).status_code,403)
            self.assertEqual(client.post('/api/login',json={'id':'parent','pin':'9876'},headers=token).status_code,200)

    def test_pages_and_static_assets(self):
        self.assertEqual(self.client.get('/').status_code,200)
        for asset in ('app.js','style.css','manifest.json','icon.svg'):
            with self.client.get('/static/'+asset) as response:
                self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/config/test_profiles.json').status_code,404)


if __name__=='__main__': unittest.main()
