import os

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_NAME', 'test_db')
os.environ.setdefault('DB_USER', 'test_user')
os.environ.setdefault('DB_PASS', 'test_pass')

import pytest  # noqa: E402
import app as app_module  # noqa: E402

# Neutralize scheduler on the app module namespace
app_module.start_uptime_scheduler = lambda: None
app_module.get_branding = lambda: {}
app_module.get_nav_counts = lambda: {}

app = app_module.app
app.config['SESSION_COOKIE_SECURE'] = False
app.config['TESTING'] = True


class FakeCursor:
    def __init__(self, fetchone_val=None, fetchall_val=None):
        self._fetchone_val = fetchone_val
        self._fetchall_val = fetchall_val if fetchall_val is not None else []

    def execute(self, *args, **kwargs):
        pass

    def fetchone(self):
        return self._fetchone_val

    def fetchall(self):
        return self._fetchall_val

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor=None):
        self._cursor = cursor or FakeCursor()

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def login_as(client, role='user', username='testuser', csrf_token='test-csrf-token'):
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = username
        sess['role'] = role
        if csrf_token is not None:
            sess['_csrf_token'] = csrf_token


@pytest.fixture
def client():
    yield app.test_client()


@pytest.fixture
def login_as_user():
    return login_as
