import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from aquafeed import Feeder
class ValveTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.send=Mock();self.feeder=Feeder(self.send,lambda:{'connected':True,'port':'TEST'},Path(self.temp.name)/'test.sqlite3');self.feeder.state['connected']=True
 def tearDown(self):self.temp.cleanup()
 def test_exact_acknowledgements_and_unconfirmed_reply(self):
  self.send.return_value='SERVO_ROTATING';self.feeder.send('SERVO_ROTATE');self.assertEqual(self.feeder.valve_snapshot()['status'],'running')
  self.send.return_value='SERVO_STOPPED';self.feeder.send('SERVO_STOP');self.assertEqual(self.feeder.valve_snapshot()['status'],'stopped')
  for response in (None,'OK','SERVO_ROTATING'):
   self.send.return_value=response;self.feeder.send('SERVO_STOP');self.assertEqual(self.feeder.valve_snapshot()['status'],'unknown')
 def test_pending_status_and_disconnect(self):
  self.feeder.record_valve_command('SERVO_ROTATE',pending=True);self.assertEqual(self.feeder.valve_snapshot()['status'],'starting')
  self.feeder.record_valve_command('SERVO_STOP',pending=True);self.assertEqual(self.feeder.valve_snapshot()['status'],'stopping')
  self.feeder.state['connected']=False;self.assertEqual(self.feeder.valve_snapshot()['status'],'unknown')
 def test_exception_and_cache_poll(self):
  self.send.side_effect=OSError('Serial lost')
  with self.assertRaises(OSError):self.feeder.send('SERVO_STOP')
  self.assertEqual(self.feeder.valve_snapshot()['status'],'unknown')
  self.send.reset_mock()
  for _ in range(5):self.feeder.valve_snapshot()
  self.send.assert_not_called()
if __name__=='__main__':unittest.main()
