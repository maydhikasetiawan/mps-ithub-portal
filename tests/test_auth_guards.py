from urllib.parse import urlparse
import pytest
from tests.conftest import login_as, FakeConnection, FakeCursor
import routes.reports
import routes.uptime


def redirect_path(response):
    return urlparse(response.location).path


class TestAnonymousGuards:
    def test_anonymous_root_redirects_to_login(self, client):
        res = client.get('/')
        assert res.status_code == 302
        assert '/login' in res.location

    def test_anonymous_reports_redirects_to_login(self, client):
        res = client.get('/reports/')
        assert res.status_code == 302
        assert '/login' in res.location

    def test_anonymous_export_assets_redirects_to_login(self, client):
        res = client.get('/reports/export/assets')
        assert res.status_code == 302
        assert '/login' in res.location

    def test_anonymous_export_tickets_redirects_to_login(self, client):
        res = client.get('/reports/export/tickets')
        assert res.status_code == 302
        assert '/login' in res.location

    def test_anonymous_uptime_redirects_to_login(self, client):
        res = client.get('/uptime/')
        assert res.status_code == 302
        assert '/login' in res.location

    def test_anonymous_uptime_check_one_method_not_allowed(self, client):
        res = client.get('/uptime/check/1')
        assert res.status_code == 405

    def test_anonymous_uptime_check_all_method_not_allowed(self, client):
        res = client.get('/uptime/check-all')
        assert res.status_code == 405

    def test_anonymous_health_check_returns_healthy(self, client):
        res = client.get('/health')
        assert res.status_code == 200
        data = res.get_json()
        assert data.get('status') == 'healthy'


class TestGuestGuards:
    def test_guest_reports_redirects_to_dashboard(self, client):
        login_as(client, role='guest', username='guest')
        res = client.get('/reports/')
        assert res.status_code == 302
        assert redirect_path(res) in ['/', '/dashboard']

    def test_guest_export_assets_redirects_to_dashboard(self, client):
        login_as(client, role='guest', username='guest')
        res = client.get('/reports/export/assets')
        assert res.status_code == 302
        assert redirect_path(res) in ['/', '/dashboard']

    def test_guest_export_tickets_redirects_to_dashboard(self, client):
        login_as(client, role='guest', username='guest')
        res = client.get('/reports/export/tickets')
        assert res.status_code == 302
        assert redirect_path(res) in ['/', '/dashboard']

    def test_guest_uptime_check_one_post_redirects_to_dashboard(self, client):
        login_as(client, role='guest', username='guest')
        res = client.post('/uptime/check/1')
        assert res.status_code == 302
        assert redirect_path(res) in ['/', '/dashboard']

    def test_guest_uptime_check_all_post_redirects_to_dashboard(self, client):
        login_as(client, role='guest', username='guest')
        res = client.post('/uptime/check-all')
        assert res.status_code == 302
        assert redirect_path(res) in ['/', '/dashboard']


class TestUserGuards:
    def test_user_export_assets_redirects_to_dashboard(self, client):
        login_as(client, role='user', username='regular_user')
        res = client.get('/reports/export/assets')
        assert res.status_code == 302
        assert redirect_path(res) in ['/', '/dashboard']


class TestAdminGuardsWithFakes:
    def test_admin_export_assets_csv(self, client, monkeypatch):
        monkeypatch.setattr(routes.reports, 'get_db_connection', lambda: FakeConnection())
        login_as(client, role='admin', username='admin')
        res = client.get('/reports/export/assets')
        assert res.status_code == 200
        assert res.mimetype == 'text/csv'
        assert 'Laporan Aset IT' in res.get_data(as_text=True)

    def test_admin_uptime_check_all(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(routes.uptime, 'run_all_checks', lambda: calls.append(1))
        login_as(client, role='admin', username='admin')
        res = client.post('/uptime/check-all')
        assert res.status_code == 302
        assert redirect_path(res) == '/uptime/'
        assert len(calls) == 1

    def test_admin_uptime_check_one(self, client, monkeypatch):
        fake_conn = FakeConnection(cursor=FakeCursor(fetchone_val=None))
        monkeypatch.setattr(routes.uptime, 'get_db_connection', lambda: fake_conn)
        login_as(client, role='admin', username='admin')
        res = client.post('/uptime/check/1')
        assert res.status_code == 302
        assert redirect_path(res) == '/uptime/'
