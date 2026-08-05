---
okf: v0.1
type: Research
title: 2026-07-24-ivyeaops-structure
timestamp: 2026-07-24
---

# IvyeaOps-sellfox — Lingxing structure audit (read-only)

**Repo root:** `d:\Work\赛狐\IvyeaOps-sellfox` (clone of Hector-xue/IvyeaOps)  
**Audit date:** 2026-07-24

---

## 1. `lingxing_openapi.py` — auth / sign / request API surface

**Path:** `d:\Work\赛狐\IvyeaOps-sellfox\server\app\services\lingxing_openapi.py`

Thin transport only. Policy (master/operate switches, audit, human-confirm) lives in `lingxing_service.py`.

| Symbol | Role |
|--------|------|
| `LingXingOpenAPIError` | Transport / business error |
| `classify_route(route) -> "read"\|"write"\|"unknown"` | Path markers (`/manage/`, `/put`, `/create`, …) → write |
| `make_sign(params, app_id) -> str` | ksort → `k=v&…` → MD5 upper → AES-128-ECB(PKCS7, key=appId) → base64 |
| `is_configured() -> bool` | host + appid + secret from hub settings |
| `_ensure_token(client) -> access_token` | File cache + refresh skew 120s |
| `call(route, params=None, *, method="POST") -> dict` | Signed request (common qs + JSON body) |
| `verify() -> dict` | Token + probe GET `/erp/sc/data/seller/lists` |

**Config keys** (`hub_settings`): `lingxing_openapi_host`, `lingxing_openapi_appid`, `lingxing_openapi_secret`

**Token cache:** `{settings.data_dir}/lingxing_token.json` via `_token_path()`

**Auth flow:**
1. POST `/api/auth-server/oauth/access-token?appId&appSecret` (or refresh)
2. Sign full params + `access_token`/`timestamp`/`app_key`
3. POST/GET `{host}/{route}` with `sign` in query; body = JSON of full params (POST)

**How to hook (Sellfox mirror):**
- Add `sellfox_openapi.py` beside this file with the same public surface: `is_configured`, `make_sign` (or Sellfox-equivalent auth), `call`, `verify`, `classify_route`.
- Gateway should call it only via a policy wrapper (same pattern as `lingxing_service.call_openapi` / `call_openapi_read`).

---

## 2. `lingxing_data.py` — `READ_DATASETS`, fetch flow, cache

**Path:** `d:\Work\赛狐\IvyeaOps-sellfox\server\app\services\lingxing_data.py`

### `READ_DATASETS` keys (full)

| Key | Label | Route | Method |
|-----|-------|-------|--------|
| **`sellers`** | 店铺列表 | `/erp/sc/data/seller/lists` | GET |
| `fba_stock` | FBA 库存 | `/erp/sc/routing/fba/fbaStock/fbaList` | POST |
| `sp_campaigns` | SP 广告活动 | `/pb/openapi/newad/spCampaigns` | POST |
| `sp_adgroups` | SP 广告组 | `/pb/openapi/newad/spAdGroups` | POST |
| `sp_keywords` | SP 关键词 | `/pb/openapi/newad/spKeywords` | POST |
| `sp_targets` | SP 定向 | `/pb/openapi/newad/spTargets` | POST |
| `sp_campaign_report` | SP 活动报表 | `/pb/openapi/newad/spCampaignReports` | POST |
| `sp_product_ads` | SP 投放商品 | `/pb/openapi/newad/spProductAds` | POST |
| `sp_keyword_report` | SP 关键词报表 | `/pb/openapi/newad/spKeywordReports` | POST |
| `sp_target_report` | SP 定向报表 | `/pb/openapi/newad/spTargetReports` | POST |
| **`sp_search_term_report`** | SP 搜索词报表 | **`/pb/openapi/newad/queryWordReports`** | POST |
| `asin_profit` | ASIN 利润 | `/bd/profit/statistics/open/asin/list` | POST |

**Sellers:** no params; `row_key=sid`; columns sid/name/marketplace/country/seller_id/region. Other datasets take `sid` from here.

**Search-term / word report:** only key is `sp_search_term_report` → route `queryWordReports`. Params: `sid` (int, required), `report_date` (date, default `-1d`), `length`/`offset`. Columns include `query`, `target_text`, `match_type`, metrics, `campaign_id`. Hint explicitly: 否词 + 收割依据.

### `fetch_dataset` flow

```text
fetch_dataset(dataset, params, *, force=False, ttl=None, caller="panel")
  → READ_DATASETS[dataset]
  → _coerce(params)  # dates: -Nd → YYYY-MM-DD; sids → list[int]
  → params_hash = sha1(dataset|json)
  → if not force: _cache_get(dataset, hash, ttl)  # default TTL 1800s
  → else/miss: lingxing_service.call_openapi_read(route, resolved, method)
  → _cache_put → return {dataset, rows, count, synced_at, cached, params}
```

**Helpers:** `catalog()`, `_extract_rows()`, `_cache_get` / `_cache_put`

### Cache location

- **SQLite table:** `lingxing_cache` (`dataset`, `params_hash`, `params_json`, `payload_json`, `synced_at`)
- **DB file:** `{settings.data_dir}/lingxing.sqlite3` (`lingxing_service._db_path()` / `connect()`)
- Schema created in `lingxing_service` init migrations.

**How to hook:** register new keys in `READ_DATASETS`; UI/API already driven by `catalog()` + `POST /api/lingxing/read/{dataset}`.

---

## 3. `lingxing_optimizer.py` — datasets for negative/harvest; entrypoints; createTask?

**Path:** `d:\Work\赛狐\IvyeaOps-sellfox\server\app\services\lingxing_optimizer.py`

### Dataset keys used

| Use | Dataset key(s) |
|-----|----------------|
| **否词 (negative)** | `sp_search_term_report` via `_agg` |
| **收割 (harvest)** | same `sp_search_term_report` |
| 降bid / 加bid | `sp_keyword_report` + live `sp_keywords` |
| 加预算 | `sp_campaign_report` + `sp_campaigns` |
| Target ACOS | `asin_profit`, `sp_product_ads` |

Negative rule: clicks ≥ `lingxing_neg_min_clicks` (default 15) & orders==0 → `op_type=negate_keyword`, `match_type=negativeExact`.  
Harvest: orders ≥ `lingxing_harvest_min_orders` (default 3) & ACOS ≤ breakeven → advisory `add_keyword` / EXACT (often `advisory: True`).

### Entrypoints

| Function | Role |
|----------|------|
| `run_store(sid, progress=None)` | Sync rule engine; returns candidates |
| `start_background_run(sid)` | Persist run → `asyncio.create_task(run_store)` |
| `list_opt_runs` / `get_opt_run` | Poll progress from `lingxing_optimizer_runs` |

**HTTP:** `POST /api/lingxing/optimizer/run?sid=` → `start_background_run`; poll `GET /api/lingxing/optimizer/runs/{id}`  
**UI:** `client/src/pages/workbench/LingXingOptimizer.tsx` → tickets via `/lingxing/operate/manual` or `batch-tickets`.

### Does it call `createTask` daily?

**No.** There is no Lingxing `createTask` (or async report-create) in this stack. Reports are **synchronous** day-by-day GETs of `*Reports` / `queryWordReports` with `report_date`, cached with TTL `_REPORT_TTL_S = 7 days`. Optimizer is **on-demand** (manual POST), not a daily createTask cron.

(Related: `lingxing_automation.scheduler_loop` is weekly **advisory** LLM automation — also not createTask.)

---

## 4. `lingxing_operate.py` — write entrypoints (disable / pause)

**Path:** `d:\Work\赛狐\IvyeaOps-sellfox\server\app\services\lingxing_operate.py`

### `OP_TYPES` (write surface)

| op_type | Route | Disable/pause how |
|---------|-------|-------------------|
| `campaign_budget` | `/basicOpen/adReport/manage/putSpCampaign` | `new_state` / change `state`: `enabled`\|`paused` |
| `keyword_bid` | `.../putSpKeyword` | same |
| `target_bid` | `.../putSpTarget` | same |
| `adgroup_bid` | `.../putSpAdGroup` | same |
| `add_keyword` | `.../spTarget/addKeywords` | create |
| `negate_keyword` | `.../spTarget/addNegativeKeywords` | negate; reverse via `archiveNegatives` |

### Execution entrypoints (to gate / disable writes)

| Function | Purpose |
|----------|---------|
| `enable_operate()` / `disable_operate()` | TTL write switch in hub settings |
| `create_ticket` / `create_manual_ticket` / `create_tickets_batch` | Ticket → review |
| `create_tickets_from_run(run_id)` | From automation proposals |
| `confirm_ticket(tid, *, dry_run=False)` | Real write (`allow_write=True`) or dry-run |
| `batch_tickets_action("confirm"\|"reject", ids, dry_run=)` | Batch |
| `reject_ticket` / `rollback_ticket` | Reject / reverse |
| `check_guardrails` / `review_intent` / `build_body` | Pre-exec |

**Circuit breaker:** failed `confirm_ticket` → `disable_operate()`.

**Router:** `d:\Work\赛狐\IvyeaOps-sellfox\server\app\routers\lingxing.py`  
`POST /operate/enable|disable`, `/operate/manual`, `/operate/tickets/{tid}/confirm`, etc.

**To hard-disable writes without code delete:** keep `lingxing_operate_enabled=false` (and/or `lingxing_enabled=false`); leave `lingxing_scope_stores` empty (fail-closed whitelist).

---

## 5. Frontend / API flags — execute / write / confirm

### Hub settings (defaults in `hub_settings.py`)

| Key | Default | Meaning |
|-----|---------|---------|
| `lingxing_enabled` | `False` | Master: all OpenAPI/MCP calls denied if off |
| `lingxing_operate_enabled` | `False` | Write switch |
| `lingxing_operate_expires_at` | `""` | Auto-off after TTL |
| `lingxing_operate_ttl_minutes` | `120` | Enable duration |
| `lingxing_operate_require_human` | `True` | Human confirm required (locked by design) |
| `lingxing_circuit_reason` | `""` | Set on exec failure |
| `lingxing_scope_stores` | `""` | Empty = **no writes** |
| `lingxing_max_change_pct` | `20` | Magnitude guardrail |

### Gateway enforcement (`lingxing_service.py`)

- `is_master_enabled()` ← `lingxing_enabled`
- `is_operate_active()` ← master **and** operate **and** not expired
- `call_openapi(..., allow_write=False)` — writes need `allow_write=True` **and** `is_operate_active()`
- Only `confirm_ticket` / rollback pass `allow_write=True`

### Status API

`GET /api/lingxing/status` → `master_enabled`, `operate_enabled`, `operate_active`, `require_human`, scopes, ticket counts.

### Frontend

| File | Switches |
|------|----------|
| `client/src/pages/workbench/LingXingConfig.tsx` | Patch `lingxing_enabled` via `/settings` (“启用数据（只读）”) |
| `client/src/pages/workbench/LingXing.tsx` | Status chips; enable master; `POST /lingxing/read/sellers` |
| `client/src/pages/workbench/LingXingOperate.tsx` | `POST /operate/enable|disable`; confirm with `{ dry_run: true\|false }`; batch confirm |

**Dry-run:** `ConfirmRequest.dry_run` on confirm endpoints — builds body, does **not** call write API.

---

## 6. Start backend on port 8001

| Method | Command / note |
|--------|----------------|
| **Default port** | `IVYEA_OPS_PORT` default **8001** (`server/app/core/config.py`, `server/.env.example`) |
| **Prod-like** | `bash scripts/start.sh` → `cd server && .venv/bin/python -m app.main` |
| **Dev (hot reload)** | `scripts/dev.sh` → `uvicorn app.main:app --reload --host 127.0.0.1 --port 8001` |
| **Direct** | From `server/`: `python -m app.main` or `uvicorn app.main:app --host 127.0.0.1 --port 8001` |
| **Windows** | Docs: `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001` (`docs/TROUBLESHOOTING.md`) |
| **Docker entry** | `deploy/docker/entrypoint.sh`: uvicorn on **8001** inside container |
| **docker-compose.yml** | Maps host `${PORT:-8080}:80` (nginx front); **not** host:8001. Internal app still 8001. |

URL: `http://127.0.0.1:8001`

---

## 7. Python package layout — add `sellfox_openapi.py`

```text
IvyeaOps-sellfox/
  server/
    app/                    # package root (PYTHONPATH / -m app.main)
      main.py               # FastAPI + uvicorn.run(..., port=settings.port)
      core/
        config.py           # IVYEA_OPS_PORT, data_dir
        hub_settings.py     # lingxing_* (+ future sellfox_*) knobs
      routers/
        lingxing.py         # /api/lingxing/*
      services/
        lingxing_openapi.py   # ← mirror as sellfox_openapi.py here
        lingxing_service.py   # gateway: switches + call_openapi*
        lingxing_data.py
        lingxing_optimizer.py
        lingxing_operate.py
        …
```

**Recommended Sellfox parallel (minimal):**

1. `server/app/services/sellfox_openapi.py` — auth/sign/`call`/`verify`/`is_configured` (same role as lingxing transport).
2. Optionally `sellfox_service.py` — master/operate gating + audit (copy `call_openapi` pattern).
3. Wire settings keys in `hub_settings.py` (e.g. `sellfox_openapi_*`, `sellfox_enabled`).
4. New router or extend existing; import as `from app.services import sellfox_openapi as _sf`.

No separate package name beyond `app.services.*`; keep flat service modules like existing lingxing_* files.

---

## Hook cheat-sheet

```text
Read path:  UI/API → lingxing_data.fetch_dataset → lingxing_service.call_openapi_read
            → lingxing_openapi.call (sign+token)

Write path: UI confirm → lingxing_operate.confirm_ticket → call_openapi(..., allow_write=True)
            → lingxing_openapi.call  [blocked unless master+operate active]

Opt path:   POST /optimizer/run → start_background_run → run_store
            → fetch_dataset(sp_search_term_report | sp_keyword_report | …)
            → candidates → operate tickets (human confirm)
```
