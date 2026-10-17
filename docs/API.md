# REST API v1 (MPS-ITHub)

Read-only REST API for integrations (tickets, assets, monitors).

## Base URL & Auth
- **Base URL**: `/api/v1`
- **Header**: `X-API-Key: <key>` (configured via `API_KEY` env)
- **Tradeoff**: Single shared key gives full read access. No key management UI or per-user scoping.
- **Fail-closed**: Missing/invalid key or empty `API_KEY` returns `401 {"error": "..."}`.
- **Errors**: `400` (invalid params), `401` (auth failed), `404` (not found).
- **Format**: JSON, ISO dates (`YYYY-MM-DDTHH:MM:SS`), `null` for unset dates. Soft-deleted rows excluded. No rate limiting yet.

## Pagination & Parameters
- `limit`: default `20`, max `100` (integer >= 1).
- `offset`: default `0` (integer >= 0).
- Response shape: `{"data": [...], "meta": {"total": N, "limit": L, "offset": O}}`

## Endpoints

### 1. Tickets
- `GET /api/v1/tickets` — list active tickets (`is_deleted = FALSE`, `ORDER BY id DESC`).
  - Filters: `status`, `category`, `priority`, `assignee`.
- `GET /api/v1/tickets/<int:ticket_id>` — single ticket (404 if missing or soft-deleted).

### 2. Assets
- `GET /api/v1/assets` — list active assets (`is_deleted = FALSE`, `ORDER BY id DESC`).
  - Filters: `status`, `category`.
- `GET /api/v1/assets/<int:asset_id>` — single asset (404 if missing or soft-deleted).

### 3. Monitors
- `GET /api/v1/monitors` — list monitors from `monitors` (`ORDER BY id ASC`).
- `GET /api/v1/monitors/<int:monitor_id>` — single monitor (404 if missing).
- Real-column mapping: `name` → `service_name`, `target` → `target_url`, `status` → `last_status`, `latency` → `response_time_ms`, `last_check` → `last_checked`.
- Additional fields: `type` (e.g. `PING`/`TCP`/`HTTP`), `port`, `consecutive_failures`, `created_at`.

## Curl Examples
```bash
# List open tickets
curl -H "X-API-Key: secret" "http://localhost:5000/api/v1/tickets?status=Open&limit=5"

# Get ticket detail
curl -H "X-API-Key: secret" "http://localhost:5000/api/v1/tickets/10"

# List assets
curl -H "X-API-Key: secret" "http://localhost:5000/api/v1/assets?category=Laptop"

# List monitors
curl -H "X-API-Key: secret" "http://localhost:5000/api/v1/monitors"
```
