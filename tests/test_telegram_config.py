import os
from cryptography.fernet import Fernet
from tests.conftest import login_as, FakeConnection, FakeCursor
import routes.uptime
import database.db


class RecordingCursor(FakeCursor):
    def __init__(self, fetchone_val=None, fetchall_val=None):
        super().__init__(fetchone_val=fetchone_val, fetchall_val=fetchall_val)
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))


def test_telegram_config_env_set(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test-token-present')
    fake_conn = FakeConnection(cursor=FakeCursor(fetchone_val={'chat_id': '-100123456'}))
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: FakeConnection(cursor=FakeCursor(fetchone_val=None)))

    token, chat_id = routes.uptime.get_telegram_config()
    assert bool(token)
    assert chat_id == '-100123456'


def test_telegram_config_env_unset(monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    fake_conn = FakeConnection(cursor=FakeCursor(fetchone_val={'chat_id': '-100123456'}))
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: FakeConnection(cursor=FakeCursor(fetchone_val=None)))

    token, chat_id = routes.uptime.get_telegram_config()
    assert token == ''
    assert chat_id == '-100123456'


def test_telegram_settings_post_admin_with_bot_token(client, monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY', test_key)

    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)

    login_as(client, role='admin', username='admin')
    res = client.post(
        '/uptime/telegram-settings',
        data={
            '_csrf_token': 'test-csrf-token',
            'chat_id': '-100987654',
            'bot_token': 'my-new-bot-token',
        },
    )
    assert res.status_code == 302

    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 1
    key, val, is_secret = hub_writes[0]
    assert key == 'telegram_bot_token'
    assert is_secret is True
    assert val != 'my-new-bot-token'
    f = Fernet(test_key.encode())
    assert f.decrypt(val.encode()).decode() == 'my-new-bot-token'

    chat_writes = [p for q, p in cursor.executed if 'UPDATE telegram_settings' in q]
    assert len(chat_writes) == 1
    assert chat_writes[0] == ('-100987654',)


def test_telegram_settings_post_admin_without_bot_token(client, monkeypatch):
    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)

    login_as(client, role='admin', username='admin')
    res = client.post(
        '/uptime/telegram-settings',
        data={
            '_csrf_token': 'test-csrf-token',
            'chat_id': '-100987654',
            'bot_token': '',
        },
    )
    assert res.status_code == 302
    for query, params in cursor.executed:
        assert 'hub_settings' not in query
        if 'UPDATE telegram_settings' in query:
            assert params == ('-100987654',)


def test_telegram_settings_get_renders_bot_token_input(client, monkeypatch):
    fake_conn = FakeConnection(cursor=FakeCursor(fetchone_val={'chat_id': '-100123456'}))
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: FakeConnection(cursor=FakeCursor(fetchone_val=None)))

    login_as(client, role='admin', username='admin')
    res = client.get('/uptime/telegram-settings')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'name="bot_token"' in html
    assert 'type="password"' in html
    assert 'value="my-new-bot-token"' not in html
