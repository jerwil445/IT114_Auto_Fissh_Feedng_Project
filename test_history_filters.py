import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from flask import Flask
from aquafeed import Feeder
from pages.history import create_blueprint
class HistoryFilterTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.feeder=Feeder(Mock(),lambda:{'connected':False,'port':None},Path(self.temp.name)/'test.sqlite3')
  rows=[('2026-10-15T23:59:00+08:00','feeding','Automatic','Flakes','Successful','Morning done'),('2026-10-16T00:00:00+08:00','feeding','Manual','Pellets','Failed','Servo failed'),('2026-10-16T12:00:00+08:00','system',None,None,'Warning','Low feed 10%'),('2026-10-17T00:00:00+08:00','system',None,None,'Info','Connected')]
  with self.feeder.db() as db:
   for row in rows:db.execute('INSERT INTO events(timestamp,kind,trigger,portion,status,message) VALUES(?,?,?,?,?,?)',row)
  self.app=Flask(__name__);self.app.register_blueprint(create_blueprint(self.feeder));self.client=self.app.test_client()
 def tearDown(self):self.temp.cleanup()
 def test_per_tab_filters_before_pagination(self):
  r=self.client.get('/api/history?page=1&limit=1&kind=feeding&status=Failed&trigger=Manual').json
  self.assertEqual(r['total'],1);self.assertEqual(r['events'][0]['portion'],'Pellets');self.assertFalse(r['has_next'])
  r=self.client.get('/api/history?page=1&kind=system&status=Warning').json
  self.assertEqual(r['total'],1);self.assertEqual(r['events'][0]['status'],'Warning')
 def test_inclusive_dates_and_literal_search(self):
  r=self.client.get('/api/history?page=1&start=2026-10-16&end=2026-10-16').json;self.assertEqual(r['total'],2)
  r=self.client.get('/api/history?page=1&search=PELLETS').json;self.assertEqual(r['total'],1)
  r=self.client.get('/api/history?page=1&search=10%25').json;self.assertEqual(r['total'],1)
  r=self.client.get('/api/history?page=1&search=%27%20OR%201%3D1').json;self.assertEqual(r['total'],0)
 def test_invalid_filters(self):
  for query in ('kind=other','kind=system&status=Successful','trigger=Manual','kind=feeding&trigger=other','start=bad','start=2026-10-17&end=2026-10-16','search='+('x'*101)):
   self.assertEqual(self.client.get('/api/history?page=1&'+query).status_code,400,query)
if __name__=='__main__':unittest.main()
