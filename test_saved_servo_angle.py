import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from aquafeed import Feeder,DEFAULTS
from serial_protocol import is_command_reply
class SavedAngleTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.send=Mock(side_effect=self.reply)
  self.feeder=Feeder(self.send,lambda:{'connected':True,'port':'TEST'},Path(self.temp.name)/'test.sqlite3')
 def tearDown(self):self.temp.cleanup()
 def reply(self,command):
  return 'SERVO_ANGLE_OK' if command.startswith('SERVO_ANGLE:') else 'SERVO_ROTATING' if command=='SERVO_ROTATE' else 'SERVO_STOPPED' if command=='SERVO_STOP' else 'OK'
 def test_saved_angle_applies_to_feeding_and_hardware_test(self):
  for angle in (60,65,75):
   settings=copy.deepcopy(DEFAULTS);settings['angle']=angle;self.feeder.save(settings)
   self.send.reset_mock();self.feeder.feed_lock.acquire()
   with patch('aquafeed.time.sleep'):self.feeder.dispense('Manual','Flakes',self.feeder.settings())
   self.assertEqual([c.args[0] for c in self.send.call_args_list],[f'SERVO_ANGLE:{angle}','SERVO_ROTATE','SERVO_STOP'])
   self.send.reset_mock();self.feeder.feed_lock.acquire()
   with patch.object(self.feeder.test_cancel,'wait',return_value=False):self.feeder.run_tests(['servo'])
   self.assertEqual([c.args[0] for c in self.send.call_args_list],[f'SERVO_ANGLE:{angle}','SERVO_ROTATE','SERVO_STOP'])
 def test_invalid_settings_and_missing_angle_ack(self):
  for angle in (59,76,60.5,True):
   settings=copy.deepcopy(DEFAULTS);settings['angle']=angle
   with self.assertRaises(ValueError):self.feeder.save(settings)
  for reply in (None,'OK','UNKNOWN_COMMAND:SERVO_ANGLE'):
   self.send.side_effect=None;self.send.return_value=reply;self.send.reset_mock();self.feeder.feed_lock.acquire()
   self.feeder.dispense('Manual','Flakes',DEFAULTS)
   self.assertEqual([c.args[0] for c in self.send.call_args_list],['SERVO_ANGLE:75'])
   self.assertEqual(self.feeder.state['operation'],'Failed')
  self.assertTrue(is_command_reply('SERVO_ANGLE:60','SERVO_ANGLE_OK'))
  self.assertFalse(is_command_reply('SERVO_ANGLE:60','SERVO_STOPPED'))
if __name__=='__main__':unittest.main()
