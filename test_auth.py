import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from flask import Flask
from werkzeug.security import check_password_hash
from aquafeed import setup_aquafeed
from pages.landing import setup_auth


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='isolated-test-secret')
        self.send = Mock()
        with patch.dict(os.environ, AQUAFEED_DB=str(Path(self.temp.name)/'test.sqlite3')):
            self.feeder = setup_aquafeed(self.app, self.send, lambda: {'connected':False, 'port':None})
        self.feeder.start = Mock()
        self.app.add_url_rule('/command/<command>', 'legacy_command', lambda command: self.send(command) or 'OK')
        setup_auth(self.app, self.feeder.store)
        self.client = self.app.test_client()

    def tearDown(self):
        self.send.assert_not_called()
        self.temp.cleanup()

    def post(self, path, data=None):
        token = self.client.get('/api/auth/session').json['csrf_token']
        return self.client.post(path, json=data or {}, headers={'X-CSRF-Token':token})

    def register(self, **changes):
        data=dict(name='Test Keeper',email='Keeper@example.com',password='Test-password-123',confirm_password='Test-password-123')
        data.update(changes)
        return self.post('/api/auth/register',data)

    def test_public_landing_assets_and_protected_pages(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        for text in (b'hero-background-video',b'login-form',b'register-form'):
            self.assertIn(text,response.data)
        with self.client.get('/static/css/landing.css') as asset:
            self.assertEqual(asset.status_code,200)
        for path in ('/dashboard','/control','/history','/hardware-test'):
            self.assertEqual(self.client.get(path).status_code,302)
        for path in ('/api/monitor','/command/SERVO_ROTATE'):
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.client.post('/api/feed').status_code,401)

    def test_registration_hash_session_and_dashboard(self):
        self.assertEqual(self.register().status_code,201)
        with self.feeder.store.connect() as db:
            user=db.execute('SELECT * FROM users').fetchone()
        self.assertEqual(user['email'],'keeper@example.com')
        self.assertNotEqual(user['password_hash'],'Test-password-123')
        self.assertTrue(check_password_hash(user['password_hash'],'Test-password-123'))
        for path in ('/dashboard','/control','/history','/hardware-test'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn(b'logout-button',response.data)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn(b'Open dashboard',self.client.get('/').data)

    def test_login_logout_and_duplicate_email(self):
        self.register()
        self.assertEqual(self.post('/api/auth/logout').status_code,200)
        self.assertEqual(self.client.get('/api/monitor').status_code,401)
        self.assertEqual(self.register(email='KEEPER@example.com').status_code,409)
        self.assertEqual(self.post('/api/auth/login',dict(email='keeper@example.com',password='wrong')).status_code,401)
        self.assertEqual(self.post('/api/auth/login',dict(email='KEEPER@example.com',password='Test-password-123')).status_code,200)
        self.assertEqual(self.client.get('/dashboard').status_code,200)

    def test_csrf_blocks_mutations_and_legacy_commands(self):
        self.assertEqual(self.client.post('/api/auth/register',json={}).status_code,403)
        self.register()
        self.assertEqual(self.client.post('/api/auth/logout').status_code,403)
        self.assertEqual(self.client.post('/api/settings',json={}).status_code,403)
        self.assertEqual(self.client.get('/command/SERVO_ROTATE').status_code,403)
        self.assertEqual(self.client.get('/dashboard').status_code,200)

    def test_validation_and_escaped_name(self):
        for changes in (dict(password='short'),dict(confirm_password='different'),dict(email='invalid'),dict(name='x')):
            self.assertEqual(self.register(**changes).status_code,400)
        self.assertEqual(self.register(name='<script>alert(1)</script>').status_code,201)
        dashboard=self.client.get('/dashboard').data
        self.assertNotIn(b'<script>alert(1)</script>',dashboard)
        self.assertIn(b'&lt;script&gt;',dashboard)

    def test_rate_limit(self):
        for _ in range(20):
            self.assertEqual(self.post('/api/auth/login',dict(email='nobody@example.com',password='wrong')).status_code,401)
        self.assertEqual(self.post('/api/auth/login',dict(email='nobody@example.com',password='wrong')).status_code,429)

    def test_app_registers_public_routes(self):
        app_rules = {str(rule) for rule in self.app.url_map.iter_rules()}
        self.assertIn('/static/<path:filename>', app_rules)
        self.assertIn('/', app_rules)
        self.assertIn('/api/auth/session', app_rules)
        self.assertIn('/api/auth/register', app_rules)
        self.assertIn('/api/auth/login', app_rules)

if __name__=='__main__':
    unittest.main()
