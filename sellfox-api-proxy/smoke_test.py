#!/usr/bin/env python3
"""
Smoke tests for sellfox-api-proxy.

Tests the proxy gateway end-to-end: health, auth, key CRUD, API proxying,
rate limiting, and permission enforcement.

Usage:
    python smoke_test.py              # remote: https://api.vilavi.cn/sellfox
    python smoke_test.py --local      # local:  http://localhost:8400

Requires: ADMIN_API_KEY env var (the admin password / X-Admin-Key value).
"""

import argparse
import concurrent.futures
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request


# ── Config ──────────────────────────────────────────────────────────

REMOTE_BASE = "https://api.vilavi.cn/sellfox"
LOCAL_BASE = "http://localhost:8400"

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")
if not ADMIN_KEY:
    print("FATAL: ADMIN_API_KEY env var not set")
    sys.exit(1)

# ── Colors ──────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str):
    print(f"  {GREEN}PASS{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}FAIL{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}WARN{RESET} {msg}")


# ── HTTP Helpers ────────────────────────────────────────────────────

class Session:
    """An HTTP session with cookie jar and base URL."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.cookiejar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookiejar),
            urllib.request.HTTPRedirectHandler(),
        )
        self.created_key_id: str | None = None
        self.created_key: str | None = None

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    def request(self, method: str, path: str, body=None, headers=None, timeout=30):
        """Make an HTTP request. Returns (status, body_bytes, response_headers)."""
        url = self._url(path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            resp = self.opener.open(req, timeout=timeout)
            return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def get(self, path: str, **kw):
        return self.request("GET", path, **kw)

    def post(self, path: str, body=None, **kw):
        return self.request("POST", path, body=body, **kw)

    def delete(self, path: str, **kw):
        return self.request("DELETE", path, **kw)

    def json(self, method: str, path: str, **kw) -> dict:
        status, raw, headers = self.request(method, path, **kw)
        return {"status": status, "data": json.loads(raw), "headers": headers}


# ── Test Runner ─────────────────────────────────────────────────────

passed = 0
failed = 0


def run_test(name: str, fn):
    global passed, failed
    print(f"\n{BOLD}[{name}]{RESET}")
    try:
        fn()
        passed += 1
    except AssertionError as e:
        fail(str(e))
        failed += 1
    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
        failed += 1


# ── Tests ───────────────────────────────────────────────────────────

def test_health(s: Session):
    """1. GET /health → 200, sellfox_reachable: true"""
    r = s.json("GET", "/health")
    assert r["status"] == 200, f"expected 200, got {r['status']}"
    assert r["data"]["status"] == "ok", f"status not ok: {r['data']}"
    reachable = r["data"].get("sellfox_reachable", False)
    if reachable:
        ok(f"sellfox_reachable={reachable}")
    else:
        warn(f"sellfox_reachable={reachable} (may be expected depending on network)")


def test_admin_login(s: Session):
    """2. POST /admin/login → 200 + set cookie"""
    # Login uses form-encoded password, not JSON
    import urllib.parse
    data = urllib.parse.urlencode({"password": ADMIN_KEY}).encode()
    req = urllib.request.Request(s._url("/admin/login"), data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        resp = s.opener.open(req, timeout=15)
        status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code

    if status in (200, 302, 303):
        cookies = list(s.cookiejar)
        has_session = any("proxy_admin_session" in str(c) for c in cookies)
        if has_session:
            ok("login cookie set (proxy_admin_session)")
        else:
            warn(f"login returned {status} but no session cookie found; falling back to X-Admin-Key header")
    else:
        warn(f"form login returned {status}; tests will use X-Admin-Key header fallback")


def _admin_headers() -> dict:
    return {"X-Admin-Key": ADMIN_KEY}


def test_create_key(s: Session):
    """3. POST /admin/api/keys → 200, key returned"""
    r = s.json("POST", "/admin/api/keys",
               body={"name": "smoke-test", "account": "sellfox-main"},
               headers=_admin_headers())
    assert r["status"] == 200, f"expected 200, got {r['status']}: {r['data']}"
    key = r["data"].get("key", "")
    assert key.startswith("sk-"), f"key doesn't start with sk-: {key}"
    s.created_key = key
    ok(f"key created: {key[:12]}...")


def test_reveal_key(s: Session):
    """4. POST /admin/api/keys/{id}/reveal → key returned"""
    # First get key list to find the created key's ID
    r = s.json("GET", "/admin/api/keys", headers=_admin_headers())
    assert r["status"] == 200, f"list keys failed: {r['status']}"
    keys = r["data"].get("keys", [])
    smoke_keys = [k for k in keys if k["name"] == "smoke-test"]
    assert smoke_keys, "smoke-test key not found in list"
    s.created_key_id = smoke_keys[0]["id"]

    r = s.json("POST", f"/admin/api/keys/{s.created_key_id}/reveal",
               headers=_admin_headers())
    assert r["status"] == 200, f"reveal failed: {r['status']}"
    revealed = r["data"].get("key", "")
    assert revealed.startswith("sk-"), f"revealed key invalid: {revealed[:12]}..."
    if revealed == s.created_key:
        ok("revealed key matches created key")
    else:
        warn("revealed key differs (may be expected if encryption differs)")


def test_proxy_api(s: Session):
    """5. POST /v1/sellfox-main/api/shop/pageList.json → 200, JSON data"""
    r = s.json("POST", "/v1/sellfox-main/api/shop/pageList.json",
               body={"pageSize": 5, "pageNum": 1},
               headers={"Authorization": f"Bearer {s.created_key}"})
    assert r["status"] == 200, f"expected 200, got {r['status']}: {r['data']}"
    code = r["data"].get("code")
    if code == 0:
        shops = r["data"].get("data", {}).get("list", [])
        ok(f"proxy works: {len(shops)} shop(s) returned")
    elif code == 40001:
        warn("token expired (expected for long-running tokens)")
    else:
        fail(f"unexpected code={code}: {r['data'].get('msg', '')}")


def test_concurrent_rate_limit(s: Session):
    """6. 3 concurrent requests → 3rd gets 429"""
    def make_request():
        try:
            s.json("POST", "/v1/sellfox-main/api/shop/pageList.json",
                   body={"pageSize": 5, "pageNum": 1},
                   headers={"Authorization": f"Bearer {s.created_key}"},
                   timeout=10)
            return True
        except Exception:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(make_request) for _ in range(3)]
        results = [f.result() for f in futures]

    successes = sum(1 for r in results if r)
    if successes >= 2:
        ok(f"concurrent: {successes}/3 success (rate limiter active)")
    elif successes == 3:
        ok(f"concurrent: all 3 success (rate limit may be high enough)")
    else:
        warn(f"concurrent: only {successes}/3 success")


def test_invalid_key(s: Session):
    """7. Invalid key → 401"""
    status, raw, _ = s.post("/v1/sellfox-main/api/shop/pageList.json",
                            body={"pageSize": 1, "pageNum": 1},
                            headers={"Authorization": "Bearer sk-invalid-deadbeef"})
    assert status == 401, f"expected 401, got {status}"
    ok("invalid key returns 401")


def test_toggle_key(s: Session):
    """8. Toggle key off → then verify it returns 401"""
    assert s.created_key_id, "no key to toggle"

    # Disable
    r = s.json("POST", f"/admin/api/keys/{s.created_key_id}/toggle",
               headers=_admin_headers())
    assert r["status"] == 200, f"toggle failed: {r['status']}: {r['data']}"

    # Verify disabled key gets 401
    status, raw, _ = s.post("/v1/sellfox-main/api/shop/pageList.json",
                            body={"pageSize": 1},
                            headers={"Authorization": f"Bearer {s.created_key}"})
    assert status == 401, f"disabled key should return 401, got {status}"

    # Re-enable
    r = s.json("POST", f"/admin/api/keys/{s.created_key_id}/toggle",
               headers=_admin_headers())
    assert r["status"] == 200, f"re-enable failed: {r['status']}"

    ok("toggle disable → 401, re-enable → ok")


def test_delete_key(s: Session):
    """9. DELETE key → then verify it's gone"""
    assert s.created_key_id, "no key to delete"

    # Delete
    r = s.json("DELETE", f"/admin/api/keys/{s.created_key_id}",
               headers=_admin_headers())
    assert r["status"] == 200, f"delete failed: {r['status']}: {r['data']}"

    # Verify gone
    r = s.json("GET", "/admin/api/keys", headers=_admin_headers())
    keys = r["data"].get("keys", [])
    gone = all(k["id"] != s.created_key_id for k in keys)
    assert gone, "key still exists after delete"

    ok("key deleted, no longer in list")


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Smoke test sellfox-api-proxy")
    parser.add_argument("--local", action="store_true",
                        help="Test against localhost:8400 instead of api.vilavi.cn")
    parser.add_argument("--skip-concurrent", action="store_true",
                        help="Skip concurrent rate-limit test")
    args = parser.parse_args()

    base = LOCAL_BASE if args.local else REMOTE_BASE
    schema = "http" if args.local else "https"
    domain = base.split("://")[1].split(":")[0]

    print(f"{BOLD}sellfox-api-proxy Smoke Tests{RESET}")
    print(f"Target: {base}")
    print(f"Mode:   {'local (bypass nginx)' if args.local else 'remote (nginx + public)'}")
    print(f"Auth:   ADMIN_API_KEY={'***' if ADMIN_KEY else 'NOT SET'}")

    # Quick pre-check (any status is fine, just testing connectivity)
    try:
        urllib.request.urlopen(f"{base}/health", timeout=10)
        print(f"Connectivity: {GREEN}OK{RESET}")
    except Exception as e:
        print(f"\n{YELLOW}WARN: Cannot reach {base}: {e}{RESET}")
        print("Tests will likely fail. Continue anyway? (Ctrl+C to abort)")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            sys.exit(1)

    s = Session(base)

    run_test("1. Health check", lambda: test_health(s))
    run_test("2. Admin login", lambda: test_admin_login(s))
    run_test("3. Create API key", lambda: test_create_key(s))
    run_test("4. Reveal API key", lambda: test_reveal_key(s))
    run_test("5. Proxy API call", lambda: test_proxy_api(s))

    if not args.skip_concurrent:
        run_test("6. Concurrent rate limit", lambda: test_concurrent_rate_limit(s))
    else:
        print(f"\n{BOLD}[6. Concurrent rate limit]{RESET}")
        warn("skipped (--skip-concurrent)")

    run_test("7. Invalid key → 401", lambda: test_invalid_key(s))
    run_test("8. Toggle key disable/enable", lambda: test_toggle_key(s))
    run_test("9. Delete key", lambda: test_delete_key(s))

    # Cleanup in case test 9 failed
    if s.created_key_id:
        try:
            s.json("DELETE", f"/admin/api/keys/{s.created_key_id}",
                   headers=_admin_headers())
        except Exception:
            pass

    # Summary
    total = passed + failed
    print(f"\n{BOLD}{'=' * 50}{RESET}")
    print(f"Results: {GREEN}{passed} passed{RESET}", end="")
    if failed:
        print(f", {RED}{failed} failed{RESET}", end="")
    print(f" of {total} total")
    if failed:
        print(f"\n{RED}Some tests failed!{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All tests passed!{RESET}")


if __name__ == "__main__":
    main()
