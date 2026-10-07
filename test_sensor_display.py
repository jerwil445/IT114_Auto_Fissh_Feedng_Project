import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from flask import Flask
from aquafeed import Feeder
from pages.dashboard import create_blueprint
class SensorTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.send=Mock(return_value='OK')
  self.feeder=Feeder(self.send,lambda:{'connected':True,'port':'TEST'},Path(self.temp.name)/'test.sqlite3')
  self.feeder.state['connected']=True
 def tearDown(self):self.temp.cleanup()
 def test_raw_reading_expires_without_new_sample(self):
  with patch('aquafeed.time.monotonic',return_value=100):self.feeder.record_sensor(12.1,True)
  with patch('aquafeed.time.monotonic',return_value=101):
   result=self.feeder.sensor_snapshot();self.assertEqual(result['distance'],12.1);self.assertEqual(result['age_seconds'],1)
  with patch('aquafeed.time.monotonic',return_value=106):
   result=self.feeder.sensor_snapshot();self.assertEqual(result['status'],'stale');self.assertIsNone(result['distance'])
 def test_no_echo_disconnect_and_waiting(self):
  self.assertEqual(self.feeder.sensor_snapshot()['status'],'waiting')
  self.feeder.record_sensor(None,True)
  self.assertEqual(self.feeder.sensor_snapshot()['status'],'no_echo')
  self.feeder.record_sensor(12,False)
  self.assertEqual(self.feeder.sensor_snapshot()['status'],'disconnected')
  self.assertIsNone(self.feeder.sensor_snapshot()['distance'])
 def test_polling_does_not_access_hardware_or_database(self):
  self.feeder.record_sensor(20,True)
  app=Flask(__name__);app.register_blueprint(create_blueprint(self.feeder))
  with patch.object(self.feeder,'db',side_effect=AssertionError('Unexpected DB read')):
   for _ in range(5):
    response=app.test_client().get('/api/sensor');self.assertEqual(response.status_code,200)
    self.assertEqual(response.json['distance'],20);self.assertEqual(response.headers['Cache-Control'],'no-store')
  self.send.assert_not_called()
if __name__=='__main__':unittest.main()
