from datetime import datetime
from tests.conftest import app, login_as, FakeConnection
from tests.test_telegram_config import RecordingCursor
import database.db
import routes.tickets


def test_post_comment_internal_by_admin(client, monkeypatch):
    ticket_data = {
        'id': 1,
        'status': 'Open',
        'created_by': 'admin',
        'title': 'Test Ticket',
        'created_at': datetime.now(),
        'priority': 'Medium',
        'category': 'General',
    }
    cursor = RecordingCursor(fetchone_val=ticket_data)
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(routes.tickets, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)

    login_as(client, role='admin', username='admin')
    res = client.post(
        '/tickets/1',
        data={
            '_csrf_token': 'test-csrf-token',
            'action': 'comment',
            'comment': 'Staff internal note',
            'comment_visibility': 'internal',
        },
    )
    assert res.status_code == 302
    inserts = [p for q, p in cursor.executed if 'INSERT INTO ticket_activities' in q]
    assert len(inserts) == 1
    # params: (ticket_id, username, comment_text, is_internal)
    assert inserts[0][3] is True


def test_post_comment_internal_by_user_forced_public(client, monkeypatch):
    ticket_data = {
        'id': 2,
        'status': 'Open',
        'created_by': 'user1',
        'title': 'Test Ticket User',
        'created_at': datetime.now(),
        'priority': 'Medium',
        'category': 'General',
    }
    cursor = RecordingCursor(fetchone_val=ticket_data)
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(routes.tickets, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)

    login_as(client, role='user', username='user1')
    res = client.post(
        '/tickets/2',
        data={
            '_csrf_token': 'test-csrf-token',
            'action': 'comment',
            'comment': 'User trying internal note',
            'comment_visibility': 'internal',
        },
    )
    assert res.status_code == 302
    inserts = [p for q, p in cursor.executed if 'INSERT INTO ticket_activities' in q]
    assert len(inserts) == 1
    # forced to False (public)
    assert inserts[0][3] is False


def test_detail_query_hides_internal_for_user_guest(client, monkeypatch):
    ticket_data = {
        'id': 3,
        'status': 'Open',
        'created_by': 'user1',
        'title': 'Test Detail Visibility',
        'created_at': datetime.now(),
        'priority': 'Medium',
        'category': 'General',
    }

    class DetailCursor(RecordingCursor):
        def fetchone(self):
            for q, _ in reversed(self.executed):
                if 'FROM tickets WHERE id' in q:
                    return ticket_data
                elif 'FROM ticket_ratings' in q:
                    return None
            return ticket_data

        def fetchall(self):
            for q, _ in reversed(self.executed):
                if 'FROM ticket_activities' in q:
                    return [
                        {
                            'id': 101,
                            'ticket_id': 3,
                            'actor': 'admin',
                            'type': 'comment',
                            'content': 'Public message',
                            'is_internal': False,
                            'created_at': datetime.now(),
                            'actor_role': 'admin',
                        }
                    ]
                elif 'FROM ticket_attachments' in q:
                    return []
                elif 'FROM kb_articles' in q:
                    return []
                elif 'FROM users WHERE role' in q:
                    return []
            return []

    cursor = DetailCursor()
    fake_conn = FakeConnection(cursor=cursor)
    monkeypatch.setattr(routes.tickets, 'get_db_connection', lambda: fake_conn)
    monkeypatch.setattr(database.db, 'get_db_connection', lambda: fake_conn)

    # User viewer: activities query MUST filter out internal comments
    login_as(client, role='user', username='user1')
    res = client.get('/tickets/3')
    assert res.status_code == 200
    user_activity_queries = [
        q for q, _ in cursor.executed if 'FROM ticket_activities' in q
    ]
    assert len(user_activity_queries) == 1
    assert "AND (ta.type != 'comment' OR ta.is_internal = FALSE)" in user_activity_queries[0]

    # Admin viewer: activities query has NO filter
    cursor.executed.clear()
    login_as(client, role='admin', username='admin')
    res = client.get('/tickets/3')
    assert res.status_code == 200
    admin_activity_queries = [
        q for q, _ in cursor.executed if 'FROM ticket_activities' in q
    ]
    assert len(admin_activity_queries) == 1
    assert "is_internal = FALSE" not in admin_activity_queries[0]
