import os
from cryptography.fernet import Fernet
from flask import jsonify
from tests.conftest import app, login_as, FakeConnection, FakeCursor
from tests.test_telegram_config import RecordingCursor
import database.db
import routes.settings_hub
import routes.api
import routes.tickets
import routes.uptime


def test_hub_get_admin(client, monkeypatch):
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: FakeConnection(cursor=FakeCursor(fetchone_val=None)))
    login_as(client, role='admin', username='admin')
    res = client.get('/settings')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert '/settings/branding' in html
    assert '/settings/telegram' in html
    assert '/settings/telegram-test' in html
    assert '/settings/sla' in html
    assert '/settings/webhook' in html
    assert '/settings/interval' in html
    assert '/settings/api-key' in html


def test_hub_get_non_admin_redirects(client):
    for role in ['it', 'user', 'guest']:
        login_as(client, role=role, username=f'user_{role}')
        res = client.get('/settings')
        assert res.status_code == 302
        assert '/' in res.headers.get('Location', '')


def test_csrf_protection_on_settings_posts(client):
    login_as(client, role='admin', username='admin', csrf_token='test-csrf-token')
    # POST without CSRF token in payload
    res_sla = client.post('/settings/sla', data={})
    assert res_sla.status_code == 403

    res_api = client.post('/settings/api-key', data={})
    assert res_api.status_code == 403


def test_sla_post_valid_and_invalid(client, monkeypatch):
    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)
    login_as(client, role='admin', username='admin')

    # Valid POST
    valid_data = {
        '_csrf_token': 'test-csrf-token',
        'sla_critical_response': '1', 'sla_critical_resolution': '3',
        'sla_high_response': '2', 'sla_high_resolution': '6',
        'sla_medium_response': '4', 'sla_medium_resolution': '12',
        'sla_low_response': '8', 'sla_low_resolution': '24',
    }
    res = client.post('/settings/sla', data=valid_data)
    assert res.status_code == 302
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 8

    # Invalid POSTs: 0, negative, non-integer, response > resolution
    invalid_cases = [
        {'sla_critical_response': '0', 'sla_critical_resolution': '4'},
        {'sla_high_response': '-1', 'sla_high_resolution': '8'},
        {'sla_medium_response': 'abc', 'sla_medium_resolution': '24'},
        {'sla_low_response': '10', 'sla_low_resolution': '8'},  # response > resolution
    ]
    for case in invalid_cases:
        cursor.executed.clear()
        data = dict(valid_data)
        data.update(case)
        res = client.post('/settings/sla', data=data)
        assert res.status_code == 302
        hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
        assert len(hub_writes) == 0


def test_interval_post(client, monkeypatch):
    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)
    login_as(client, role='admin', username='admin')

    # Invalid: 59, 3601, 'abc'
    for bad in ['59', '3601', 'abc']:
        cursor.executed.clear()
        res = client.post(
            '/settings/interval',
            data={'_csrf_token': 'test-csrf-token', 'uptime_interval_seconds': bad},
        )
        assert res.status_code == 302
        hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
        assert len(hub_writes) == 0

    # Valid: 300
    cursor.executed.clear()
    res = client.post(
        '/settings/interval',
        data={'_csrf_token': 'test-csrf-token', 'uptime_interval_seconds': '300'},
    )
    assert res.status_code == 302
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 1
    assert hub_writes[0][0] == 'uptime_interval_seconds'
    assert hub_writes[0][1] == '300'
    assert hub_writes[0][2] is False


def test_webhook_post(client, monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY', test_key)

    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)
    login_as(client, role='admin', username='admin')

    # Valid URL
    res = client.post(
        '/settings/webhook',
        data={'_csrf_token': 'test-csrf-token', 'webhook_url': 'https://example.com/hook'},
    )
    assert res.status_code == 302
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 1
    key, val, is_secret = hub_writes[0]
    assert key == 'webhook_url'
    assert is_secret is True
    assert val != 'https://example.com/hook'
    f = Fernet(test_key.encode())
    assert f.decrypt(val.encode()).decode() == 'https://example.com/hook'

    # Empty URL (disabled)
    cursor.executed.clear()
    res = client.post(
        '/settings/webhook',
        data={'_csrf_token': 'test-csrf-token', 'webhook_url': ''},
    )
    assert res.status_code == 302
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 1
    assert hub_writes[0] == ('webhook_url', '', False)

    # Invalid URL scheme
    cursor.executed.clear()
    res = client.post(
        '/settings/webhook',
        data={'_csrf_token': 'test-csrf-token', 'webhook_url': 'ftp://example.com/hook'},
    )
    assert res.status_code == 302
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 0


def test_api_key_post_with_and_without_key(client, monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY', test_key)

    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)
    login_as(client, role='admin', username='admin')

    # Valid with encryption key
    res = client.post(
        '/settings/api-key',
        data={'_csrf_token': 'test-csrf-token', 'api_key': 'secret-key-123'},
    )
    assert res.status_code == 302
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 1
    key, val, is_secret = hub_writes[0]
    assert key == 'api_key'
    assert is_secret is True
    assert val != 'secret-key-123'
    f = Fernet(test_key.encode())
    assert f.decrypt(val.encode()).decode() == 'secret-key-123'

    # Empty -> DELETE hub_settings row
    cursor.executed.clear()
    res = client.post(
        '/settings/api-key',
        data={'_csrf_token': 'test-csrf-token', 'api_key': ''},
    )
    assert res.status_code == 302
    deletes = [p for q, p in cursor.executed if 'DELETE FROM hub_settings' in q]
    assert len(deletes) == 1
    assert deletes[0] == ('api_key',)

    # POST with NO encryption key -> refused
    monkeypatch.delenv('SETTINGS_ENCRYPTION_KEY', raising=False)
    cursor.executed.clear()
    res = client.post(
        '/settings/api-key',
        data={'_csrf_token': 'test-csrf-token', 'api_key': 'secret-key-123'},
    )
    assert res.status_code == 302
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 0


def test_decrypt_failure_handling(client, monkeypatch):
    # Corrupt secret row in DB
    corrupt_row = {'value': 'invalid-not-fernet-token', 'is_secret': True}
    monkeypatch.setattr(
        database.db,
        'get_db_connection',
        lambda: FakeConnection(cursor=FakeCursor(fetchone_val=corrupt_row)),
    )

    # getter returns None on decrypt failure
    assert database.db.get_hub_setting('api_key') is None
    assert database.db.hub_setting_decrypt_failed('api_key') is True

    login_as(client, role='admin', username='admin')
    res = client.get('/settings')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'Kunci enkripsi tidak cocok atau data rusak' in html


def test_fallback_to_env_when_no_db_row(monkeypatch):
    monkeypatch.setattr(
        database.db,
        'get_db_connection',
        lambda: FakeConnection(cursor=FakeCursor(fetchone_val=None)),
    )
    monkeypatch.setenv('API_KEY', 'env-api-key')
    monkeypatch.setenv('WEBHOOK_URL', 'https://env.example.com/hook')
    monkeypatch.setenv('UPTIME_CHECK_INTERVAL', '120')

    # API key fallback
    test_func = routes.api.require_api_key(lambda: jsonify({'status': 'ok'}))
    with app.test_request_context(headers={'X-API-Key': 'env-api-key'}):
        res = test_func()
        # Should succeed because env key matched
        assert res.status_code == 200

    # Interval fallback
    assert routes.uptime.get_check_interval_seconds() == 120

    # SLA fallback
    sla = routes.tickets.get_sla_targets()
    assert sla == routes.tickets.SLA_TARGETS


def test_db_overrides_env(monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY', test_key)
    monkeypatch.setenv('API_KEY', 'env-key')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'env-telegram-token')

    f = Fernet(test_key.encode())
    encrypted_api_key = f.encrypt(b'db-key').decode()
    encrypted_tg_token = f.encrypt(b'db-telegram-token').decode()

    def fake_db():
        class MockCursor(FakeCursor):
            def execute(self, query, params=None):
                self._query = query
                self._params = params or ()

            def fetchone(self):
                if 'hub_settings' in self._query and self._params:
                    if self._params[0] == 'api_key':
                        return {'value': encrypted_api_key, 'is_secret': True}
                    if self._params[0] == 'telegram_bot_token':
                        return {'value': encrypted_tg_token, 'is_secret': True}
                if 'telegram_settings' in self._query:
                    return {'chat_id': '-999'}
                return None
        return FakeConnection(cursor=MockCursor())

    monkeypatch.setattr(database.db, 'get_db_connection', fake_db)
    monkeypatch.setattr(routes.uptime, 'get_db_connection', fake_db)

    # Verify API key uses DB
    test_func = routes.api.require_api_key(lambda: jsonify({'status': 'ok'}))
    with app.test_request_context(headers={'X-API-Key': 'db-key'}):
        assert test_func().status_code == 200
    with app.test_request_context(headers={'X-API-Key': 'env-key'}):
        # Rejected because DB key overrides env key
        assert test_func()[1] == 401

    # Verify Telegram token uses DB
    token, chat_id = routes.uptime.get_telegram_config()
    assert token == 'db-telegram-token'
    assert chat_id == '-999'


def test_api_key_delete_failure(client, monkeypatch):
    def fail_conn():
        raise RuntimeError("DB connection error")
    monkeypatch.setattr(database.db, 'get_db_connection', fail_conn)
    assert database.db.delete_hub_setting('api_key') is False

    login_as(client, role='admin', username='admin')
    res = client.post(
        '/settings/api-key',
        data={'_csrf_token': 'test-csrf-token', 'api_key': ''},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert 'Gagal menghapus API key dari database.' in res.get_data(as_text=True)


def test_branding_post_saves_and_flashes(client, monkeypatch):
    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)
    login_as(client, role='admin', username='admin')
    res = client.post(
        '/settings/branding',
        data={
            '_csrf_token': 'test-csrf-token',
            'app_name': 'My Portal',
            'tagline': 'Best Tagline',
            'logo_url': 'https://example.com/logo.png',
            'login_headline': 'Welcome',
            'login_text': 'Please login',
            'footer_text': 'Footer info',
        },
    )
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/settings')
    with client.session_transaction() as sess:
        assert any('Pengaturan branding disimpan.' in msg for _, msg in sess.get('_flashes', []))
    branding_updates = [p for q, p in cursor.executed if 'UPDATE branding_settings' in q]
    assert len(branding_updates) == 1
    assert branding_updates[0] == ('My Portal', 'Best Tagline', 'https://example.com/logo.png', 'Welcome', 'Please login', 'Footer info')


def test_telegram_post_saves_and_flashes(client, monkeypatch):
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY', test_key)
    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)
    login_as(client, role='admin', username='admin')
    res = client.post(
        '/settings/telegram',
        data={
            '_csrf_token': 'test-csrf-token',
            'chat_id': '-100555666',
            'bot_token': 'secret-tg-token',
        },
    )
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/settings')
    with client.session_transaction() as sess:
        assert any('Pengaturan Telegram berhasil disimpan.' in msg for _, msg in sess.get('_flashes', []))
    hub_writes = [p for q, p in cursor.executed if 'INSERT INTO hub_settings' in q]
    assert len(hub_writes) == 1
    assert hub_writes[0][0] == 'telegram_bot_token'
    assert hub_writes[0][2] is True
    chat_writes = [p for q, p in cursor.executed if 'UPDATE telegram_settings' in q]
    assert len(chat_writes) == 1
    assert chat_writes[0] == ('-100555666',)


def test_telegram_post_missing_key_skips_chat_id(client, monkeypatch):
    monkeypatch.delenv('SETTINGS_ENCRYPTION_KEY', raising=False)
    cursor = RecordingCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)
    login_as(client, role='admin', username='admin')
    res = client.post(
        '/settings/telegram',
        data={
            '_csrf_token': 'test-csrf-token',
            'chat_id': '-100555666',
            'bot_token': 'secret-tg-token',
        },
    )
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/settings')
    with client.session_transaction() as sess:
        assert any('Kunci enkripsi SETTINGS_ENCRYPTION_KEY belum dikonfigurasi; chat_id tidak disimpan.' in msg for _, msg in sess.get('_flashes', []))
    chat_writes = [p for q, p in cursor.executed if 'UPDATE telegram_settings' in q]
    assert len(chat_writes) == 0


def test_telegram_test_button_sends_and_flashes(client, monkeypatch):
    monkeypatch.setattr(routes.settings_hub, 'get_telegram_config', lambda: ('fake-token', '-100123'))
    monkeypatch.setattr(routes.settings_hub, 'send_telegram_message', lambda t, c, m: (True, ''))
    login_as(client, role='admin', username='admin')
    res = client.post(
        '/settings/telegram-test',
        data={'_csrf_token': 'test-csrf-token'},
    )
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/settings')
    with client.session_transaction() as sess:
        assert any('Koneksi Telegram aktif' in msg for _, msg in sess.get('_flashes', []))


def test_old_urls_redirect_to_hub(client):
    login_as(client, role='admin', username='admin')
    res_b = client.get('/settings/branding')
    assert res_b.status_code == 302
    assert res_b.headers['Location'].endswith('/settings')

    res_t = client.get('/uptime/telegram-settings')
    assert res_t.status_code == 302
    assert res_t.headers['Location'].endswith('/settings')

    res_test_get = client.get('/uptime/telegram-test')
    assert res_test_get.status_code == 302
    assert res_test_get.headers['Location'].endswith('/settings')

    res_test_post = client.post('/uptime/telegram-test', data={'_csrf_token': 'test-csrf-token'})
    assert res_test_post.status_code == 302
    assert res_test_post.headers['Location'].endswith('/settings')


def test_duplicate_buttons_removed_from_templates():
    with open('templates/users/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
        assert 'branding.branding_settings' not in content
        assert 'Pengaturan Branding' not in content
    with open('templates/uptime/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
        assert 'uptime.telegram_settings' not in content
        assert 'Pengaturan Telegram' not in content

