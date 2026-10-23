import pytest
from tests.conftest import login_as
import routes.uptime


def test_anonymous_get_login_renders_csrf_token(client):
    res = client.get('/login')
    assert res.status_code == 200
    assert 'name="_csrf_token"' in res.get_data(as_text=True)


def test_post_login_no_token_returns_403(client):
    res = client.post('/login', data={'username': 'admin', 'password': 'wrong'})
    assert res.status_code == 403


def test_post_login_wrong_token_returns_403(client):
    res = client.post('/login', data={'username': 'admin', 'password': 'wrong', '_csrf_token': 'wrong-token'})
    assert res.status_code == 403


def test_post_uptime_check_all_as_admin_without_token_returns_403(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes.uptime, 'run_all_checks', lambda: calls.append(1))
    login_as(client, role='admin', username='admin', csrf_token=None)
    res = client.post('/uptime/check-all')
    assert res.status_code == 403
    assert len(calls) == 0


def test_post_uptime_check_all_as_admin_with_real_token_succeeds(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes.uptime, 'run_all_checks', lambda: calls.append(1))
    # Obtain token after a GET that renders a form
    client.get('/login')
    with client.session_transaction() as sess:
        real_token = sess.get('_csrf_token')
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = 'admin'
    assert real_token is not None

    res = client.post('/uptime/check-all', data={'_csrf_token': real_token})
    assert res.status_code == 302
    assert res.location == '/uptime/'
    assert len(calls) == 1


def test_api_v1_post_exempt_from_csrf(client):
    res = client.post('/api/v1/tickets')
    assert res.status_code == 405
