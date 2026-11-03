#!/usr/bin/env python3
"""nas_mcp 离线单测 —— **不连 NAS、不需要网络**，可进 CI。

覆盖：路径护栏、会话错误识别、错误码翻译、登录熔断、Thumb API 回退、
以及 HTTP 端点（/healthz 免令牌、其它 GET 需令牌、ping/initialize/tools/list）。

用法（在仓库根执行）：
    uv run python nas_mcp/tests/test_offline.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "nas_mcp"))

os.environ["NAS_MCP_TOKEN"] = "test-token"
os.environ["NAS_ALLOWED_ROOTS"] = "/FZH共享文件夹,/产品信息"
os.environ.setdefault("NAS_ROOT_FOLDER", "/FZH共享文件夹")
os.environ.setdefault("NAS_URL", "https://example.invalid:5001")
os.environ.setdefault("NAS_USERNAME", "dummy")
os.environ.setdefault("NAS_PASSWORD", "dummy")

import server as S  # noqa: E402
from synology_api.exceptions import FileStationError  # noqa: E402

ok = fail = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print("── 1) 路径护栏")
for bad in ["/etc/passwd", "/FZH共享文件夹/../../etc", "/其他共享文件夹", "/FZH共享文件夹X/x"]:
    try:
        S.safe_path(bad)
        check(f"拒绝 {bad}", False, "← 竟然放行")
    except S.PathDenied:
        check(f"拒绝 {bad}", True)
check("放行根", S.safe_path("") == S.ROOTS[0], S.safe_path(""))
check("放行第二个根", S.safe_path("/产品信息/x") == "/产品信息/x")

print("\n── 2) 会话错误识别")
check("119 识别为会话错误", S._is_session_error(FileStationError(error_code=119)))
check("Session timeout 识别", S._is_session_error("Session timeout"))
check("权限错误不识别", not S._is_session_error("Permission denied"))

print("\n── 3) 错误码翻译（借用库码表）")
txt = S.describe_dsm_error(FileStationError(error_code=408))
check("408 翻译为文件不存在", "No such file" in txt, txt)
txt = S.describe_dsm_error(S.NasError("自定义错误"))
check("NasError 原样返回", txt == "自定义错误", txt)

print("\n── 4) Thumb API 回退")
_orig_get = S.requests.get
S.requests.get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
S._thumb_api_cache.update({"path": None, "version": None})
got = S.thumb_api(SimpleNamespace(base_url="https://x/webapi/"))
S.requests.get = _orig_get
check("发现失败回退默认值", got == (S.THUMB_PATH, S.THUMB_VER), str(got))

print("\n── 5) 登录熔断（FileStation 抛 LoginError）")


class _BoomFS:
    def __init__(self, **kw):
        raise S.LoginError(error_code=400)


_orig_fs = S.FileStation
_orig_nas = S._nas
S.FileStation = _BoomFS
S._nas = None
S._login_state.update({"last_ok": 0.0, "failures": [], "blocked_until": 0.0})
_msgs = []
for _ in range(4):
    try:
        S.nas_client()
    except S.NasError as e:
        _msgs.append(str(e))
S.FileStation = _orig_fs
S._nas = _orig_nas
S._login_state.update({"last_ok": 0.0, "failures": [], "blocked_until": 0.0})
check("前 3 次报登录失败", len(_msgs) == 4 and all("登录失败" in m for m in _msgs[:3]),
      str(_msgs[:3]))
check("第 4 次直接熔断", "熔断" in (_msgs[3] if len(_msgs) > 3 else ""), str(_msgs[3:4]))

print("\n── 6) HTTP 端点（本地随机端口，不连 NAS）")
srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{port}"


def http_get(path: str):
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def http_post(obj, with_token: bool = True):
    req = urllib.request.Request(BASE + "/mcp", data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    if with_token:
        req.add_header("Authorization", f"Bearer {os.environ['NAS_MCP_TOKEN']}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return e.code, (json.loads(body) if body else {})


code, body = http_get("/healthz")
hz = json.loads(body) if code == 200 else {}
check("/healthz 免令牌 200", code == 200, f"code={code}")
check("/healthz 返回版本与工具数",
      hz.get("version") == S.SERVER_VERSION and hz.get("tools") == len(S.TOOLS),
      f"version={hz.get('version')} tools={hz.get('tools')}")
check("/healthz 只读声明", hz.get("read_only") is True and hz.get("allowed_roots") == S.ROOTS)

code, _ = http_get("/status")
check("非 /healthz 的 GET 仍需令牌（401）", code == 401, f"code={code}")

code, _ = http_post({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    with_token=False)
check("无令牌 tools/list 401", code == 401, f"code={code}")

code, resp = http_post({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
check("ping 返回空结果", code == 200 and resp.get("result") == {}, str(resp)[:120])

code, resp = http_post({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
check("initialize 返回协议版本",
      resp.get("result", {}).get("protocolVersion") == S.PROTOCOL, str(resp)[:120])

code, resp = http_post({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
check("tools/list 返回 15 个工具", len(resp.get("result", {}).get("tools") or []) == len(S.TOOLS))

code, resp = http_post({"jsonrpc": "2.0", "id": 4, "method": "no/such", "params": {}})
check("未知方法返回 -32601", (resp.get("error") or {}).get("code") == -32601, str(resp)[:120])

srv.shutdown()

print(f"\n结果：{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
