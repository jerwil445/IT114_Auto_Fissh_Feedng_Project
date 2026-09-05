import copy
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from aquafeed import DEFAULTS, HARDWARE_TESTS, Feeder, setup_aquafeed


class FeederTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'test.sqlite3'
        self.send = Mock(return_value='OK')
        self.connection = Mock(return_value={'connected': True, 'port': 'COM5'})
        self.feeder = Feeder(self.send, self.connection, self.database)

    def tearDown(self):
        self.temp.cleanup()

    def test_settings_persist_and_invalid_settings_do_not_overwrite(self):
        settings = copy.deepcopy(DEFAULTS)
        settings['duration'] = 1.5
        self.feeder.save(settings)
        self.assertEqual(Feeder(self.send, self.connection, self.database).settings()['duration'], 1.5)
        for invalid in (0, 61, float('nan'), True):
            settings['duration'] = invalid
            with self.assertRaises(ValueError):
                self.feeder.save(settings)
        self.assertEqual(self.feeder.settings()['duration'], 1.5)

    def test_reject_duplicate_times_and_bad_calibration(self):
        settings = copy.deepcopy(DEFAULTS)
        settings['slots'][1]['time'] = settings['slots'][0]['time']
        with self.assertRaises(ValueError):
            self.feeder.save(settings)
        settings = copy.deepcopy(DEFAULTS)
        settings['full_distance'] = 30
        with self.assertRaises(ValueError):
            self.feeder.save(settings)

    def test_dispense_stops_and_logs_success(self):
        self.feeder.feed_lock.acquire()
        with patch('aquafeed.time.sleep'):
            self.feeder.dispense('Manual', 'Flakes', DEFAULTS)
        self.assertEqual([call.args[0] for call in self.send.call_args_list], ['SERVO_ROTATE', 'SERVO_STOP'])
        self.assertEqual(self.feeder.history()['events'][0]['status'], 'Successful')
        self.assertFalse(self.feeder.feed_lock.locked())

    def test_missing_acknowledgement_still_stops_and_logs_failure(self):
        self.send.side_effect = ['', 'OK']
        self.feeder.feed_lock.acquire()
        self.feeder.dispense('Manual', 'Flakes', DEFAULTS)
        self.assertEqual(self.send.call_args.args[0], 'SERVO_STOP')
        self.assertEqual(self.feeder.history()['events'][0]['status'], 'Failed')

    def test_stop_failure_leaves_valve_unknown(self):
        self.send.side_effect = ['OK', None]
        self.feeder.feed_lock.acquire()
        with patch('aquafeed.time.sleep'):
            self.feeder.dispense('Manual', 'Flakes', DEFAULTS)
        self.assertEqual(self.feeder.state['valve'], 'Unknown')
        self.assertEqual(self.feeder.state['operation'], 'Failed')

    def test_busy_feeder_rejects_second_request(self):
        self.feeder.feed_lock.acquire()
        self.assertFalse(self.feeder.begin_feed())
        self.feeder.feed_lock.release()

    def test_schedule_executes_once_per_minute_even_after_restart(self):
        settings = copy.deepcopy(DEFAULTS)
        settings['automation'] = True
        self.feeder.save(settings)
        moment = datetime(2026, 9, 6, 8, 0, 10, tzinfo=self.feeder.zone)
        with patch.object(self.feeder, 'now', return_value=moment), patch.object(self.feeder, 'begin_feed', return_value=True) as begin:
            self.feeder.tick()
            self.feeder.tick()
            begin.assert_called_once()
        restarted = Feeder(self.send, self.connection, self.database)
        with patch.object(restarted, 'now', return_value=moment), patch.object(restarted, 'begin_feed') as begin:
            restarted.tick()
            begin.assert_not_called()

    def test_level_requires_calibration_and_warns_once(self):
        self.send.return_value = 'DISTANCE:24'
        self.feeder.tick()
        self.assertIsNone(self.feeder.state['level'])
        settings = copy.deepcopy(DEFAULTS)
        settings['calibrated'] = True
        self.feeder.save(settings)
        self.feeder.tick()
        self.feeder.tick()
        self.assertEqual(self.feeder.state['level'], 5)
        warnings = [event for event in self.feeder.history()['events'] if 'Low feed' in event['message']]
        self.assertEqual(len(warnings), 1)
        self.connection.return_value = {'connected': False, 'port': None}
        self.feeder.tick()
        self.assertIsNone(self.feeder.state['distance'])
        self.assertIsNone(self.feeder.state['level'])

    def test_nonfinite_sensor_readings_are_unavailable(self):
        for response in ('DISTANCE:nan', 'DISTANCE:inf', 'DISTANCE:-1', 'ERROR', ''):
            self.send.return_value = response
            self.feeder.tick()
            self.assertIsNone(self.feeder.state['distance'])

    def test_history_pagination(self):
        for index in range(20):
            self.feeder.log('system', 'Info', str(index))
        first = self.feeder.history()
        second = self.feeder.history(before=first['events'][-1]['id'])
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual(len(first['events']) + len(second['events']), 20)
        self.assertTrue(set(e['id'] for e in first['events']).isdisjoint(e['id'] for e in second['events']))

    def run_diagnostics(self, selected):
        self.feeder.feed_lock.acquire()
        self.feeder.diagnostics['running'] = True
        with patch.object(self.feeder.test_cancel, 'wait'):
            self.feeder.run_tests(selected)

    def test_all_hardware_and_cleanup(self):
        self.send.side_effect = lambda command: 'DISTANCE:15' if command == 'DISTANCE' else 'OK'
        self.run_diagnostics(list(HARDWARE_TESTS))
        self.assertEqual(len(self.feeder.diagnostics['results']), 10)
        self.assertTrue(all(result['status'] == 'Acknowledged' for result in self.feeder.diagnostics['results'].values()))
        commands = [call.args[0] for call in self.send.call_args_list]
        for stop in ('MORNING_OFF', 'AFTERNOON_OFF', 'NIGHT_OFF', 'RED_OFF', 'BUZZER_OFF', 'SERVO_STOP', 'ALL_LED_OFF'):
            self.assertIn(stop, commands)
        self.assertFalse(self.feeder.feed_lock.locked())

    def test_failed_hardware_still_stops_and_skips_remaining(self):
        self.send.side_effect = ['', 'OK']
        self.run_diagnostics(['servo', 'lcd'])
        self.assertEqual([call.args[0] for call in self.send.call_args_list], ['SERVO_ROTATE', 'SERVO_STOP'])
        self.assertEqual(self.feeder.diagnostics['results']['servo']['status'], 'Failed')
        self.assertEqual(self.feeder.diagnostics['results']['lcd']['status'], 'Skipped')

    def test_cancellation_sends_off_command(self):
        def reply(command):
            self.feeder.test_cancel.set()
            return 'OK'
        self.send.side_effect = reply
        self.run_diagnostics(['buzzer', 'servo'])
        self.assertEqual([call.args[0] for call in self.send.call_args_list], ['BUZZER_ON', 'BUZZER_OFF'])
        self.assertEqual(self.feeder.diagnostics['results']['buzzer']['status'], 'Cancelled')
        self.assertEqual(self.feeder.diagnostics['results']['servo']['status'], 'Skipped')

    def test_invalid_sensor_diagnostic_fails(self):
        self.send.return_value = 'DISTANCE:nan'
        self.run_diagnostics(['sensor'])
        self.assertEqual(self.feeder.diagnostics['results']['sensor']['status'], 'Failed')

    def test_diagnostics_reject_busy_and_unknown_components(self):
        with self.assertRaises(ValueError):
            self.feeder.begin_test('unknown')
        self.feeder.feed_lock.acquire()
        self.assertFalse(self.feeder.begin_test('servo'))
        self.feeder.feed_lock.release()

    def test_pages_and_api_validation(self):
        app = Flask(__name__)
        with patch.dict('os.environ', {'AQUAFEED_DB':str(self.database)}):
            feeder = setup_aquafeed(app, self.send, self.connection)
        client = app.test_client()
        for path in ('/control', '/history', '/api/settings', '/api/history'):
            self.assertEqual(client.get(path).status_code, 200, path)
        with patch.object(feeder, 'start'):
            self.assertEqual(client.get('/api/monitor').status_code, 200)
        self.assertEqual(client.post('/api/settings', json={}).status_code, 400)
        self.assertEqual(client.get('/api/history?before=oops').status_code, 400)
        self.assertEqual(client.post('/api/settings', json=DEFAULTS).status_code, 200)
        self.assertEqual(client.post('/api/hardware-test/invalid').status_code, 400)
        feeder.feed_lock.acquire()
        self.assertEqual(client.post('/api/hardware-test/all').status_code, 409)
        feeder.feed_lock.release()
        with patch('aquafeed.threading.Thread'):
            self.assertEqual(client.post('/api/hardware-test/all').status_code, 202)
        self.assertEqual(client.post('/api/feed').status_code, 409)
        self.assertEqual(client.post('/api/hardware-test-cancel').status_code, 200)
        self.assertTrue(feeder.test_cancel.is_set())
        feeder.feed_lock.release()


if __name__ == '__main__':
    unittest.main()
