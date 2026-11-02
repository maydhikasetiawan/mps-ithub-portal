from tests.conftest import app, login_as, FakeConnection, FakeCursor
import database.db


def test_security_headers_on_normal_page(client, monkeypatch):
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: FakeConnection(cursor=FakeCursor(fetchone_val=None)))
    login_as(client, role='admin', username='admin')
    res = client.get('/settings')
    assert res.status_code == 200
    assert res.headers.get('X-Content-Type-Options') == 'nosniff'
    assert res.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert res.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'


def test_security_headers_on_404_error(client):
    res = client.get('/nonexistent-route-for-security-header-test-404')
    assert res.status_code == 404
    assert res.headers.get('X-Content-Type-Options') == 'nosniff'
    assert res.headers.get('X-Frame-Options') == 'SAMEORIGIN'
    assert res.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
