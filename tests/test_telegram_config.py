from tests.conftest import login_as, FakeConnection, FakeCursor
import routes.uptime


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

    token, chat_id = routes.uptime.get_telegram_config()
    assert bool(token)
    assert chat_id == '-100123456'


def test_telegram_config_env_unset(monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    fake_conn = FakeConnection(cursor=FakeCursor(fetchone_val={'chat_id': '-100123456'}))
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)

    token, chat_id = routes.uptime.get_telegram_config()
    assert token == ''
    assert chat_id == '-100123456'


def test_telegram_settings_post_admin_updates_chat_id_only(client, monkeypatch):
    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)

    login_as(client, role='admin', username='admin')
    res = client.post(
        '/uptime/telegram-settings',
        data={
            '_csrf_token': 'test-csrf-token',
            'chat_id': '-100987654',
            'bot_token': 'stale-token-must-be-ignored',
        },
    )
    assert res.status_code == 302
    assert len(cursor.executed) > 0
    for query, params in cursor.executed:
        assert 'bot_token' not in query
        if 'UPDATE telegram_settings' in query:
            assert 'chat_id = %s' in query
            assert params == ('-100987654',)


def test_telegram_settings_get_renders_no_bot_token_input(client, monkeypatch):
    fake_conn = FakeConnection(cursor=FakeCursor(fetchone_val={'chat_id': '-100123456'}))
    monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)

    login_as(client, role='admin', username='admin')
    res = client.get('/uptime/telegram-settings')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'name="bot_token"' not in html
    assert 'bot_token' not in html
