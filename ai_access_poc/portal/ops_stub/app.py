"""Portal /ops stub — board PoC status under path prefix /ops (no AGPL vendoring)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

BOARD_OUT = Path(os.environ.get("BOARD_OUT_DIR", "/data/board_out"))
IVYEAOPS_UPSTREAM = os.environ.get("IVYEAOPS_UPSTREAM", "").rstrip("/")
PORTAL_PUBLIC_URL = os.environ.get("PORTAL_PUBLIC_URL", "http://127.0.0.1:8088")
DINGTALK_ENABLED = os.environ.get("DINGTALK_ENABLED", "0").strip() in ("1", "true", "True")
DINGTALK_CLIENT_ID_SET = bool(os.environ.get("DINGTALK_CLIENT_ID", "").strip())

app = FastAPI(title="FZH AI Portal — Ops Stub", version="0.1.0")


def _load_json(name: str) -> Any | None:
    path = BOARD_OUT / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _candidates_summary() -> dict[str, Any]:
    data = _load_json("candidates.json")
    if not isinstance(data, dict):
        return {"available": False, "reason": f"missing or invalid {BOARD_OUT / 'candidates.json'}"}
    summary = data.get("summary") or {}
    return {
        "available": True,
        "summary": summary,
        "candidate_count": len(data.get("candidates") or []),
        "write_path": summary.get("write_path", "DISABLED"),
        "source": str(BOARD_OUT / "candidates.json"),
    }


def _sellers_summary() -> dict[str, Any]:
    data = _load_json("sellers_probe.json")
    if data is None:
        return {"available": False, "reason": f"missing {BOARD_OUT / 'sellers_probe.json'}"}
    if isinstance(data, list):
        return {"available": True, "shop_count": len(data), "sample": data[:3]}
    if isinstance(data, dict):
        rows = data.get("shops") or data.get("itemList") or data.get("data") or data
        if isinstance(rows, list):
            return {"available": True, "shop_count": len(rows), "keys": list(data.keys())[:12]}
        return {"available": True, "keys": list(data.keys())[:12], "raw_type": "object"}
    return {"available": True, "raw_type": type(data).__name__}


@app.get("/ops/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "portal-ops-stub",
        "board_out": str(BOARD_OUT),
        "candidates": _candidates_summary(),
        "sellers": _sellers_summary(),
        "ivyeaops_upstream": IVYEAOPS_UPSTREAM or None,
        "dingtalk": {
            "enabled": DINGTALK_ENABLED,
            "client_id_configured": DINGTALK_CLIENT_ID_SET,
            "mode": "live" if (DINGTALK_ENABLED and DINGTALK_CLIENT_ID_SET) else "dry-run",
            "oidc_path": "/oidc/",
            "enable_hint": "Set DINGTALK_CLIENT_ID/SECRET + compose --profile dingtalk",
        },
        "ops_review": "DEFERRED — skip ops sign-off for Portal PoC; see board/docs/specs/ops-review-brief.md",
    }


@app.get("/ops/api/candidates")
async def candidates() -> JSONResponse:
    data = _load_json("candidates.json")
    if data is None:
        return JSONResponse({"error": "candidates.json not found", "dir": str(BOARD_OUT)}, status_code=404)
    return JSONResponse(data)


@app.get("/ops/api/sellers")
async def sellers() -> JSONResponse:
    data = _load_json("sellers_probe.json")
    if data is None:
        return JSONResponse({"error": "sellers_probe.json not found", "dir": str(BOARD_OUT)}, status_code=404)
    return JSONResponse(data)


@app.get("/ops/api/auth/status")
async def auth_status() -> dict[str, Any]:
    """DingTalk OIDC dry-run / live status (no secrets returned)."""
    return {
        "dingtalk_enabled": DINGTALK_ENABLED,
        "client_id_configured": DINGTALK_CLIENT_ID_SET,
        "mode": "live" if (DINGTALK_ENABLED and DINGTALK_CLIENT_ID_SET) else "dry-run",
        "discovery_url": f"{PORTAL_PUBLIC_URL.rstrip('/')}/oidc/.well-known/openid-configuration"
        if DINGTALK_ENABLED
        else None,
        "note": "PoC ships config + dry-run; live SSO needs 钉钉 AppKey/Secret and profile dingtalk",
    }


@app.get("/ops/api/ivyeaops/health")
async def ivyeaops_health() -> JSONResponse:
    if not IVYEAOPS_UPSTREAM:
        return JSONResponse(
            {
                "available": False,
                "reason": "IVYEAOPS_UPSTREAM unset — using board stub only",
                "howto": "Start IvyeaOps on :8001 then set IVYEAOPS_UPSTREAM=http://host.docker.internal:8001",
            }
        )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{IVYEAOPS_UPSTREAM}/api/health")
            return JSONResponse(
                {
                    "available": r.status_code < 500,
                    "upstream": IVYEAOPS_UPSTREAM,
                    "status_code": r.status_code,
                    "body_preview": r.text[:500],
                }
            )
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"available": False, "upstream": IVYEAOPS_UPSTREAM, "error": str(exc)},
            status_code=502,
        )


@app.api_route("/ops/ivyea/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def ivyeaops_proxy(path: str, request: Request) -> JSONResponse:
    """Optional reverse proxy to full IvyeaOps UI/API when upstream is set."""
    if not IVYEAOPS_UPSTREAM:
        return JSONResponse(
            {"error": "IVYEAOPS_UPSTREAM not configured", "stub": True},
            status_code=501,
        )
    url = f"{IVYEAOPS_UPSTREAM}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            r = await client.request(request.method, url, content=body, headers=headers)
        return JSONResponse(
            content=r.json() if "application/json" in r.headers.get("content-type", "") else {"raw": r.text[:2000]},
            status_code=r.status_code,
        )
    except Exception as exc:  # noqa: BLE001 — surface upstream errors to PoC UI
        return JSONResponse({"error": str(exc), "upstream": url}, status_code=502)


@app.get("/ops", response_class=HTMLResponse)
@app.get("/ops/", response_class=HTMLResponse)
async def ops_home() -> HTMLResponse:
    cand = _candidates_summary()
    sellers = _sellers_summary()
    auth = await auth_status()
    summary = cand.get("summary") if cand.get("available") else {}
    shop = summary.get("shop_name", "—") if isinstance(summary, dict) else "—"
    n_cand = cand.get("candidate_count", 0) if cand.get("available") else 0
    by_lever = summary.get("by_lever", {}) if isinstance(summary, dict) else {}
    shop_count = sellers.get("shop_count", "—") if sellers.get("available") else "—"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FZH Ops — Board PoC</title>
  <style>
    :root {{
      --bg: #0f1419;
      --panel: #1a222c;
      --text: #e7eef6;
      --muted: #8b9bb0;
      --accent: #3d9cf0;
      --ok: #3ecf8e;
      --warn: #e6b84d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI", "PingFang SC", sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1b2a3a, var(--bg));
      color: var(--text); min-height: 100vh;
    }}
    header {{
      padding: 1.25rem 1.75rem; border-bottom: 1px solid #2a3544;
      display: flex; gap: 1rem; align-items: baseline; flex-wrap: wrap;
    }}
    header a {{ color: var(--accent); text-decoration: none; }}
    h1 {{ margin: 0; font-size: 1.35rem; font-weight: 650; letter-spacing: 0.02em; }}
    main {{ padding: 1.5rem 1.75rem; max-width: 960px; }}
    .grid {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }}
    .card {{
      background: var(--panel); border: 1px solid #2a3544; border-radius: 10px;
      padding: 1rem 1.1rem;
    }}
    .label {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; }}
    .value {{ font-size: 1.6rem; font-weight: 650; margin-top: 0.35rem; }}
    .muted {{ color: var(--muted); font-size: 0.92rem; line-height: 1.5; }}
    .badge {{
      display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px;
      font-size: 0.75rem; background: #243041; color: var(--warn);
    }}
    .badge.ok {{ color: var(--ok); }}
    pre {{
      background: #121820; border: 1px solid #2a3544; border-radius: 8px;
      padding: 0.85rem 1rem; overflow: auto; font-size: 0.82rem;
    }}
    ul {{ padding-left: 1.2rem; }}
    code {{ font-family: ui-monospace, Consolas, monospace; }}
  </style>
</head>
<body>
  <header>
    <h1>FZH Ops · Board PoC</h1>
    <a href="/">← Portal</a>
    <a href="/chat/">Chat 壳</a>
    <a href="/ops/api/health">/ops/api/health</a>
  </header>
  <main>
    <p class="muted">
      路径 <code>/ops</code> 由 Portal nginx 反代到本 stub。
      数据来自板 PoC 落盘（非 vendoring IvyeaOps）。
      运营审：<span class="badge">DEFERRED</span>
    </p>
    <div class="grid">
      <div class="card">
        <div class="label">店铺</div>
        <div class="value" style="font-size:1.1rem">{shop}</div>
      </div>
      <div class="card">
        <div class="label">候选数</div>
        <div class="value">{n_cand}</div>
      </div>
      <div class="card">
        <div class="label">sellers probe</div>
        <div class="value">{shop_count}</div>
      </div>
      <div class="card">
        <div class="label">钉钉 SSO</div>
        <div class="value" style="font-size:1.1rem">{auth.get("mode")}</div>
      </div>
    </div>
    <p class="muted" style="margin-top:1.25rem">杠杆分布：{json.dumps(by_lever, ensure_ascii=False)}</p>
    <p class="muted">写路径：{summary.get("write_path", "DISABLED") if isinstance(summary, dict) else "DISABLED"}</p>
    <h2 style="margin-top:1.75rem;font-size:1.05rem">API</h2>
    <ul class="muted">
      <li><a href="/ops/api/health"><code>/ops/api/health</code></a></li>
      <li><a href="/ops/api/candidates"><code>/ops/api/candidates</code></a></li>
      <li><a href="/ops/api/sellers"><code>/ops/api/sellers</code></a></li>
      <li><a href="/ops/api/auth/status"><code>/ops/api/auth/status</code></a></li>
      <li><a href="/ops/api/ivyeaops/health"><code>/ops/api/ivyeaops/health</code></a>（可选上游）</li>
    </ul>
    <h2 style="margin-top:1.5rem;font-size:1.05rem">完整 IvyeaOps UI</h2>
    <p class="muted">
      AGPL fork 在仓外 <code>IvyeaOps-sellfox</code>。本 PoC 默认 stub。
      若本机已起 <code>:8001</code>，设 <code>IVYEAOPS_UPSTREAM</code> 后可用
      <code>/ops/ivyea/...</code> 探活（完整 SPA 更推荐直连上游端口，因未改 Vite base）。
    </p>
    <pre id="health">loading /ops/api/health …</pre>
  </main>
  <script>
    fetch("/ops/api/health").then(r => r.json()).then(j => {{
      document.getElementById("health").textContent = JSON.stringify(j, null, 2);
    }}).catch(e => {{
      document.getElementById("health").textContent = String(e);
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(html)
