import os
import hmac
from functools import wraps
from datetime import date, datetime
from flask import Blueprint, request, jsonify
from database.db import get_db_connection

api_bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')


def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        configured_key = os.environ.get('API_KEY', '').strip()
        if not configured_key:
            return jsonify({'error': 'API key not configured'}), 401

        provided_key = request.headers.get('X-API-Key', '').strip()
        if not provided_key or not hmac.compare_digest(provided_key, configured_key):
            return jsonify({'error': 'Invalid API key'}), 401

        return f(*args, **kwargs)
    return decorated_function


def parse_pagination():
    try:
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        return None, None, (jsonify({'error': 'Invalid limit or offset'}), 400)

    if limit < 1 or offset < 0:
        return None, None, (jsonify({'error': 'Limit must be >= 1 and offset >= 0'}), 400)

    return min(limit, 100), offset, None


def serialize_date(val):
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return str(val)


def serialize_ticket(row):
    return {
        'id': row['id'],
        'ticket_code': row['ticket_code'],
        'title': row['title'],
        'category': row['category'],
        'priority': row['priority'],
        'status': row['status'],
        'description': row['description'],
        'created_by': row['created_by'],
        'assigned_to': row['assigned_to'],
        'created_at': serialize_date(row['created_at']),
        'resolved_by': row['resolved_by'],
        'resolved_at': serialize_date(row['resolved_at']),
        'resolution_note': row['resolution_note']
    }


def serialize_asset(row):
    return {
        'id': row['id'],
        'asset_tag': row['asset_tag'],
        'serial_number': row['serial_number'],
        'name': row['name'],
        'category': row['category'],
        'status': row['status'],
        'location': row['location'],
        'ip_address': row['ip_address'],
        'mac_address': row['mac_address'],
        'notes': row['notes'],
        'assigned_to': row['assigned_to'],
        'purchase_date': serialize_date(row['purchase_date']),
        'warranty_expiry': serialize_date(row['warranty_expiry']),
        'no_warranty': bool(row['no_warranty']),
        'created_at': serialize_date(row['created_at']),
        'updated_at': serialize_date(row['updated_at']),
        'updated_by': row['updated_by']
    }


def serialize_monitor(row):
    return {
        'id': row['id'],
        'service_name': row['name'],
        'target_url': row['target'],
        'type': row['type'],
        'port': row['port'],
        'last_status': row['status'],
        'response_time_ms': row['latency'],
        'last_checked': serialize_date(row['last_check']),
        'enabled': bool(row['enabled']),
        'consecutive_failures': row['consecutive_failures'],
        'created_at': serialize_date(row['created_at'])
    }


@api_bp.route('/tickets', methods=['GET'])
@require_api_key
def list_tickets():
    limit, offset, err = parse_pagination()
    if err:
        return err

    where, params = ['is_deleted = FALSE'], []
    for field, col in [('status', 'status'), ('category', 'category'),
                       ('priority', 'priority'), ('assignee', 'assigned_to')]:
        val = request.args.get(field)
        if val:
            where.append(f"{col} = %s")
            params.append(val)

    where_sql = ' WHERE ' + ' AND '.join(where)
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) AS total FROM tickets{where_sql};", tuple(params))
    total = cur.fetchone()['total']

    cur.execute(f"""
        SELECT id, ticket_code, title, category, priority, status, description,
               created_by, assigned_to, created_at, resolved_by, resolved_at, resolution_note
        FROM tickets {where_sql}
        ORDER BY id DESC LIMIT %s OFFSET %s;
    """, tuple(params + [limit, offset]))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({
        'data': [serialize_ticket(r) for r in rows],
        'meta': {'total': total, 'limit': limit, 'offset': offset}
    })


@api_bp.route('/tickets/<int:ticket_id>', methods=['GET'])
@require_api_key
def get_ticket(ticket_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ticket_code, title, category, priority, status, description,
               created_by, assigned_to, created_at, resolved_by, resolved_at, resolution_note
        FROM tickets WHERE id = %s AND is_deleted = FALSE;
    """, (ticket_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({'error': 'Ticket not found'}), 404
    return jsonify({'data': serialize_ticket(row)})


@api_bp.route('/assets', methods=['GET'])
@require_api_key
def list_assets():
    limit, offset, err = parse_pagination()
    if err:
        return err

    where, params = ['is_deleted = FALSE'], []
    for field in ['status', 'category']:
        val = request.args.get(field)
        if val:
            where.append(f"{field} = %s")
            params.append(val)

    where_sql = ' WHERE ' + ' AND '.join(where)
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(f"SELECT COUNT(*) AS total FROM assets{where_sql};", tuple(params))
    total = cur.fetchone()['total']

    cur.execute(f"""
        SELECT id, asset_tag, serial_number, name, category, status, location,
               ip_address, mac_address, notes, assigned_to, purchase_date,
               warranty_expiry, no_warranty, created_at, updated_at, updated_by
        FROM assets {where_sql}
        ORDER BY id DESC LIMIT %s OFFSET %s;
    """, tuple(params + [limit, offset]))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({
        'data': [serialize_asset(r) for r in rows],
        'meta': {'total': total, 'limit': limit, 'offset': offset}
    })


@api_bp.route('/assets/<int:asset_id>', methods=['GET'])
@require_api_key
def get_asset(asset_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, asset_tag, serial_number, name, category, status, location,
               ip_address, mac_address, notes, assigned_to, purchase_date,
               warranty_expiry, no_warranty, created_at, updated_at, updated_by
        FROM assets WHERE id = %s AND is_deleted = FALSE;
    """, (asset_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({'error': 'Asset not found'}), 404
    return jsonify({'data': serialize_asset(row)})


@api_bp.route('/monitors', methods=['GET'])
@require_api_key
def list_monitors():
    limit, offset, err = parse_pagination()
    if err:
        return err

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM monitors;")
    total = cur.fetchone()['total']

    cur.execute("""
        SELECT id, name, target, type, port, status, latency,
               last_check, created_at, enabled, consecutive_failures
        FROM monitors
        ORDER BY id ASC LIMIT %s OFFSET %s;
    """, (limit, offset))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({
        'data': [serialize_monitor(r) for r in rows],
        'meta': {'total': total, 'limit': limit, 'offset': offset}
    })


@api_bp.route('/monitors/<int:monitor_id>', methods=['GET'])
@require_api_key
def get_monitor(monitor_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, target, type, port, status, latency,
               last_check, created_at, enabled, consecutive_failures
        FROM monitors WHERE id = %s;
    """, (monitor_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({'error': 'Monitor not found'}), 404
    return jsonify({'data': serialize_monitor(row)})
