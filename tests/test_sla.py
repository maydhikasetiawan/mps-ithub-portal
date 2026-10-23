from datetime import datetime, timedelta
import pytest
from routes.tickets import compute_sla

BASE_TIME = datetime(2026, 1, 1, 8, 0, 0)


def test_compute_sla_empty_or_invalid():
    assert compute_sla(None) is None
    assert compute_sla({}) is None
    assert compute_sla({'id': 1}) is None
    assert compute_sla({'id': 1, 'priority': 'Medium'}) is None


def test_resolved_medium_met():
    ticket = {
        'id': 1,
        'priority': 'Medium',
        'status': 'Resolved',
        'created_at': BASE_TIME,
        'resolved_at': BASE_TIME + timedelta(hours=10),
    }
    res = compute_sla(ticket)
    assert res is not None
    assert res['state'] == 'met'
    assert res['badge_text'] == 'SLA Terpenuhi'
    assert res['target_type'] == 'resolution'
    assert res['target_hours'] == 24


def test_resolved_critical_breached():
    ticket = {
        'id': 2,
        'priority': 'Critical',
        'status': 'Resolved',
        'created_at': BASE_TIME,
        'resolved_at': BASE_TIME + timedelta(hours=5),
    }
    res = compute_sla(ticket)
    assert res is not None
    assert res['state'] == 'breached'
    assert res['badge_text'] == 'SLA Terlewati'
    assert res['target_hours'] == 4


def test_closed_low_exact_boundary_met():
    ticket = {
        'id': 3,
        'priority': 'Low',
        'status': 'Closed',
        'created_at': BASE_TIME,
        'resolved_at': BASE_TIME + timedelta(hours=72),
    }
    res = compute_sla(ticket)
    assert res is not None
    assert res['state'] == 'met'


def test_open_high_no_response_ok():
    ticket = {
        'id': 4,
        'priority': 'High',
        'status': 'Open',
        'created_at': BASE_TIME,
    }
    res = compute_sla(ticket, has_response=False, now=BASE_TIME + timedelta(hours=1))
    assert res is not None
    assert res['state'] == 'ok'
    assert res['badge_text'] is None
    assert res['target_type'] == 'response'
    assert res['target_hours'] == 2


def test_open_high_no_response_approaching():
    ticket = {
        'id': 5,
        'priority': 'High',
        'status': 'Open',
        'created_at': BASE_TIME,
    }
    res = compute_sla(ticket, has_response=False, now=BASE_TIME + timedelta(hours=1.7))
    assert res is not None
    assert res['state'] == 'approaching'
    assert res['badge_text'] == 'Mendekati SLA'


def test_open_high_no_response_breached():
    ticket = {
        'id': 6,
        'priority': 'High',
        'status': 'Open',
        'created_at': BASE_TIME,
    }
    res = compute_sla(ticket, has_response=False, now=BASE_TIME + timedelta(hours=2.5))
    assert res is not None
    assert res['state'] == 'breached'


def test_open_low_responded_ok():
    ticket = {
        'id': 7,
        'priority': 'Low',
        'status': 'Open',
        'created_at': BASE_TIME,
    }
    res = compute_sla(ticket, has_response=True, now=BASE_TIME + timedelta(hours=10))
    assert res is not None
    assert res['state'] == 'ok'
    assert res['target_type'] == 'resolution'
    assert res['target_hours'] == 72


def test_open_medium_activities_responded_breached():
    ticket = {
        'id': 8,
        'priority': 'Medium',
        'status': 'Open',
        'created_at': BASE_TIME,
    }
    activities = [{'type': 'comment', 'actor_role': 'it'}]
    res = compute_sla(ticket, activities=activities, now=BASE_TIME + timedelta(hours=30))
    assert res is not None
    assert res['state'] == 'breached'
    assert res['target_type'] == 'resolution'


def test_resolved_unknown_priority_fallback():
    ticket = {
        'id': 9,
        'priority': 'Urgent',
        'status': 'Resolved',
        'created_at': BASE_TIME,
        'resolved_at': BASE_TIME + timedelta(hours=10),
    }
    res = compute_sla(ticket)
    assert res is not None
    assert res['state'] == 'met'
    assert res['target_hours'] == 24
