"""Public landing page, account registration, and session authentication."""
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


def setup_auth(app, store):
    if not app.config.get('SECRET_KEY'):
        key = os.getenv('SECRET_KEY')
        if not key:
            path = Path(app.instance_path) / 'session-secret'
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open('x', encoding='utf-8') as file:
                    file.write(secrets.token_hex(32))
            except FileExistsError:
                pass
            key = path.read_text(encoding='utf-8').strip()
        app.config['SECRET_KEY'] = key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    blueprint = Blueprint('landing', __name__)
    attempts = defaultdict(deque)
    attempts_lock = threading.Lock()

    def csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return session['csrf_token']

    def start_session(user_id):
        session.clear()
        session['user_id'] = user_id
        session.permanent = True
        csrf_token()

    def rate_limited():
        now = time.monotonic()
        with attempts_lock:
            for key in list(attempts):
                while attempts[key] and attempts[key][0] < now - 600:
                    attempts[key].popleft()
                if not attempts[key]:
                    del attempts[key]
            key = request.remote_addr or 'unknown'
            if len(attempts[key]) >= 20:
                return True
            attempts[key].append(now)
        return False

    @app.context_processor
    def auth_context():
        return {'csrf_token': csrf_token, 'current_user': getattr(g, 'user', None)}

    @app.before_request
    def authenticate_request():
        if request.endpoint == 'static':
            return None
        g.user = None
        user_id = session.get('user_id')
        if isinstance(user_id, int):
            with store.connect() as db:
                row = db.execute('SELECT id, name, email FROM users WHERE id=?', (user_id,)).fetchone()
            if row:
                g.user = dict(row)
            else:
                session.clear()
        public = request.endpoint in ('landing.home', 'landing.session_info', 'landing.login', 'landing.register')
        if request.endpoint and not public and not g.user:
            if request.path.startswith(('/api/', '/command/')) or request.path in ('/status', '/distance'):
                return jsonify(message='Please log in to continue.'), 401
            return redirect(url_for('landing.home', auth='login'))
        changes_state = request.method not in ('GET', 'HEAD', 'OPTIONS') or request.path.startswith('/command/')
        if changes_state:
            expected = session.get('csrf_token', '')
            supplied = request.headers.get('X-CSRF-Token', '')
            if not expected or not secrets.compare_digest(expected, supplied):
                return jsonify(message='Your session has expired. Refresh the page and try again.'), 403

    @blueprint.get('/')
    def home():
        return render_template('landing.html')

    @blueprint.get('/api/auth/session')
    def session_info():
        response = jsonify(user=g.user, csrf_token=csrf_token())
        response.headers['Cache-Control'] = 'no-store'
        return response

    @blueprint.post('/api/auth/register')
    def register():
        if rate_limited():
            return jsonify(message='Too many attempts. Please try again in 10 minutes.'), 429
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(message='Please complete the registration form.'), 400
        name, email, password, confirmation = (data.get(key) for key in ('name', 'email', 'password', 'confirm_password'))
        if not all(isinstance(value, str) for value in (name, email, password, confirmation)):
            return jsonify(message='Please complete all fields.'), 400
        name, email = name.strip(), email.strip().lower()
        if not 2 <= len(name) <= 80:
            return jsonify(message='Name must contain 2 to 80 characters.'), 400
        if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            return jsonify(message='Enter a valid email address.'), 400
        if not 8 <= len(password) <= 128:
            return jsonify(message='Use a password between 8 and 128 characters.'), 400
        if password != confirmation:
            return jsonify(message='Passwords do not match.'), 400
        password_hash = generate_password_hash(password)
        with store.connect() as db:
            row = db.execute(
                'INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?) ON CONFLICT (email) DO NOTHING RETURNING id',
                (name, email, password_hash, datetime.now(timezone.utc).isoformat()),
            ).fetchone()
        if not row:
            return jsonify(message='An account with this email already exists. Please log in.'), 409
        start_session(row['id'])
        return jsonify(message='Account created.', redirect=url_for('dashboard.home')), 201

    @blueprint.post('/api/auth/login')
    def login():
        if rate_limited():
            return jsonify(message='Too many attempts. Please try again in 10 minutes.'), 429
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(message='Enter your email and password.'), 400
        email, password = data.get('email'), data.get('password')
        if not isinstance(email, str) or not isinstance(password, str) or len(email) > 254 or not 1 <= len(password) <= 128:
            return jsonify(message='Incorrect email or password.'), 401
        with store.connect() as db:
            row = db.execute('SELECT id,password_hash FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        if not row or not check_password_hash(row['password_hash'], password):
            return jsonify(message='Incorrect email or password.'), 401
        start_session(row['id'])
        return jsonify(message='Welcome back.', redirect=url_for('dashboard.home'))

    @blueprint.post('/api/auth/logout')
    def logout():
        session.clear()
        return jsonify(message='You have been logged out.', redirect=url_for('landing.home'))

    @app.after_request
    def protect_private_responses(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        return response

    app.register_blueprint(blueprint)
