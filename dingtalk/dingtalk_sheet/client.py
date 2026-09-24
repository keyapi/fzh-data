# -*- coding: utf-8 -*-
"""钉钉表格（workbook）只读客户端 —— 列 sheet / 读区域。

与 `dingtalk_robot`（自定义机器人 webhook）和 `dingtalk_oa_approval`（审批实例+附件）
是**不同的钉钉能力**：这里读的是「钉钉表格 / AI表格」文档内容。

## 能力边界

只读。本模块不写入、不改任何钉钉文档。

## 认证与两个必填身份

1. **accessToken** —— `POST https://api.dingtalk.com/v1.0/oauth2/accessToken`
   传企业内部应用的 `appKey`(=Client ID) / `appSecret`(=Client Secret)。
   之后所有请求带 header `x-acs-dingtalk-access-token`。

2. **operatorId** —— 文档接口**必填**，值是**操作人的 unionId**（不是 appKey、不是 AgentId、
   不是 userId）。而且**该人必须对该文档有访问权限**：同一批表里，
   有些人能读 A 表但读不了 B 表，会返回
   `403 forbidden.accessDenied / The operator has no permission.`。
   实测两个文档要用两个不同同事的 unionId 才都能读。
   → unionId 属个人信息，**只放本机 .env，不进仓库**。

## baseId 怎么来

钉钉文档链接形如 `https://alidocs.dingtalk.com/i/nodes/<baseId>?...`
——URL 里的 `nodes/` 后面那段就是 baseId，**不需要**另找。

## 端点（实测 2026-09-15）

| 用途 | 方法 | 路径 |
|------|------|------|
| 列 sheet | GET | `/v1.0/doc/workbooks/{baseId}/sheets?operatorId=&maxResults=` |
| 读区域 | GET | `/v1.0/doc/workbooks/{baseId}/sheets/{sheetId}/ranges/{A1:Z100}?operatorId=` |

返回值里单元格文本在 `displayValues`（二维数组，`A1:B2` 这种范围直接给行列表）。

## 容易踩的坑（都实测过）

- **不要用 notable API**：`/v1.0/notable/bases/{id}/sheets` 对普通钉钉表格返回
  `400 invalidRequest.inputArgs.invalid / The given baseId is incorrect. Please check the
  document type.` —— notable 只适用 AI 表格（.able 多维表），普通表格走 `doc/workbooks`。
- `{A1:B2}` 里的冒号必须 URL 编码成 `%3A`，否则被当成 query 分隔。
- `GET /v1.0/doc/workbooks/{baseId}`（不带 /sheets）**不是**有效端点 → 404。
- 没有 `.../values` 或 `.../ranges?range=` 端点 → 404。只有路径式的 `.../ranges/{A1:Z9}`。
- 少 operatorId 报 `400 MissingoperatorId`；给了但没权限报 `403 forbidden.accessDenied`；
  给了格式不对的 operatorId 报 `400 paramError-operatorId`。三种要分清。

## unionId 从哪来（需要通讯录权限）

老版 topapi 三步（本应用已实测可用）：

```
GET  https://oapi.dingtalk.com/gettoken?appkey=&appsecret=      → access_token
POST https://oapi.dingtalk.com/topapi/user/listid               → dept 下 userid 列表
POST https://oapi.dingtalk.com/topapi/v2/user/get               → userid → unionid
```

unionId 跨企业/跨应用唯一，**同一个人的 unionId 在别的应用里也一样**，
所以拿到一次可以复用到其它应用配置里。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent

API = "https://api.dingtalk.com"
OAUTH_TOKEN = f"{API}/v1.0/oauth2/accessToken"

# 单次 range 的硬上限：超过会报
# 400 invalidRequest.inputArgs.invalid
#     "This operation can only be performed on a range with at most 30000 cells"
CELL_LIMIT = 30000

# 本仓库的 .env 常有多个候选位置（worktree 里没有，在主仓库）
ENV_NAME = "DINGTALK_SHEET_ENV"


def col_letter(n: int) -> str:
    """1→A, 26→Z, 27→AA"""
    if n < 1:
        raise ValueError("列号从 1 开始")
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def chunk_rows_for(n_cols: int, rows_per_chunk: int | None = None) -> int:
    """按「单次 ≤ 30000 单元格」算每块行数。"""
    if n_cols < 1:
        raise ValueError("列数至少为 1")
    if rows_per_chunk:
        return max(1, min(rows_per_chunk, CELL_LIMIT // n_cols))
    return max(1, CELL_LIMIT // n_cols)


def is_blank_row(row) -> bool:
    return not any(str(c).strip() for c in (row or []))


def load_env(path: Path | None = None) -> dict[str, str]:
    """加载 .env。优先级：显式 path → 环境变量指向 → 模块 .env → 仓库根 .env。"""
    vals: dict[str, str] = {}
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    extra = os.environ.get(ENV_NAME, "").strip()
    if extra:
        candidates.append(Path(extra))
    candidates.append(MODULE_DIR / ".env")
    # 仓库根：本模块在 <repo>/dingtalk/dingtalk_sheet/ 下
    candidates.append(MODULE_DIR.parents[1] / ".env")
    for p in candidates:
        if not p.is_file():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return vals


def is_retryable(status: int, payload) -> bool:
    """这个失败该不该重试？

    实测同一请求会**随机**返回下列瞬时错误（换着花样来）：
      * 503 `ServiceUnavailable / temporary failure of the server`
      * 404 `invalidRequest.resource.notFound / uuid not exist`  ← 看着像"不存在"，其实是抖动

    而 403 无权限、400 参数错、404 InvalidAction.NotFound（路径本身不对）
    都是确定性的，重试多少次都一样。
    """
    if 500 <= status < 600:
        return True
    if status == 404 and isinstance(payload, dict):
        if str(payload.get("code", "")) == "invalidRequest.resource.notFound":
            return True
    return False


def _raw_request(method: str, url: str, headers: dict, data, timeout: int):
    """单次 HTTP 请求 → (status, text)。HTTP 错误也返回响应体；网络异常向上抛。"""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def http_json(method: str, url: str, token: str | None = None,
              body: dict | None = None, timeout: int = 60,
              retries: int = 5, retry_sleep: float = 2.0):
    """返回 (status, payload)。

    **5xx 与网络异常会退避重试**（实测整表扫描中途**频繁**遇到
    `503 ServiceUnavailable / temporary failure of the server` —— 3 次都不够，
    故默认 5 次、退避 2/4/6/8s）；
    **4xx 是确定性的，不重试**（权限、参数错重试多少次都一样）。
    """
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["x-acs-dingtalk-access-token"] = token

    last = (-1, "")
    attempts = max(1, retries)
    for i in range(attempts):
        try:
            status, text = _raw_request(method, url, headers, data, timeout)
        except Exception as e:                      # 网络层：超时/重置/DNS
            last = (-1, f"{type(e).__name__}: {e}")
            if i + 1 < attempts:
                time.sleep(retry_sleep * (i + 1))
                continue
            return last
        if is_retryable(status, _try_json(text)) and i + 1 < attempts:
            last = (status, text)
            time.sleep(retry_sleep * (i + 1))
            continue
        try:
            return status, json.loads(text)
        except json.JSONDecodeError:
            return status, text
    return last


def _try_json(text):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}



def get_access_token(env: dict | None = None) -> str:
    env = env or load_env()
    key = env.get("DINGTALK_CLIENT_ID") or env.get("DINGTALK_APP_KEY")
    secret = env.get("DINGTALK_CLIENT_SECRET") or env.get("DINGTALK_APP_SECRET")
    if not key or not secret:
        raise RuntimeError(
            "缺少 DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET（可写仓库根 .env）")
    code, payload = http_json("POST", OAUTH_TOKEN,
                              body={"appKey": key, "appSecret": secret})
    token = payload.get("accessToken") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError(f"accessToken 失败 http={code} body={payload}")
    return token


def parse_base_id(url_or_id: str) -> str:
    """从 alidocs 链接或裸 baseId 取出 baseId。

    链接形如 https://alidocs.dingtalk.com/i/nodes/<baseId>?utm_scene=...
    """
    s = (url_or_id or "").strip()
    if not s:
        raise ValueError("空的文档链接/baseId")
    if "://" not in s:
        return s.split("?")[0]
    path = urllib.parse.urlparse(s).path
    parts = [p for p in path.split("/") if p]
    if "nodes" in parts:
        i = parts.index("nodes")
        if i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1] if parts else s


def list_sheets(base_id: str, operator_id: str, token: str,
                max_results: int = 200) -> list[dict]:
    """列出文档里的所有 sheet（name / id）。"""
    code, payload = http_json(
        "GET",
        f"{API}/v1.0/doc/workbooks/{base_id}/sheets"
        f"?operatorId={urllib.parse.quote(operator_id)}&maxResults={max_results}",
        token=token,
    )
    if code != 200:
        raise RuntimeError(_explain(code, payload, "列 sheet"))
    return payload.get("value") or []


def read_range(base_id: str, sheet_id: str, operator_id: str, token: str,
               a1_range: str = "A1:Z1000") -> list[list[str]]:
    """读一个 A1 区域，返回二维字符串数组（单元格文本）。

    `a1_range` 里的冒号会被 URL 编码（不编码会被当 query 分隔符）。
    """
    rng = urllib.parse.quote(a1_range, safe="")
    code, payload = http_json(
        "GET",
        f"{API}/v1.0/doc/workbooks/{base_id}/sheets/{sheet_id}"
        f"/ranges/{rng}?operatorId={urllib.parse.quote(operator_id)}",
        token=token,
    )
    if code != 200:
        raise RuntimeError(_explain(code, payload, "读区域"))
    dv = payload.get("displayValues")
    if dv is None:
        dv = payload.get("values") or []
    return dv


def read_sheet_all(base_id: str, sheet_id: str, operator_id: str, token: str,
                   n_cols: int = 20, max_rows: int = 20000,
                   chunk_rows: int | None = None,
                   sleep_s: float = 0.3) -> list[list[str]]:
    """整表读取（分块翻页），返回**只到真实数据末尾**的二维数组。

    ## 为什么要这个函数，而不是自己循环 read_range

    实测两个坑（2026-09-15 踩过）：

    1. **单次 range ≤ 30000 单元格**。`A1:P2000`（16 列 × 2000 行 = 32000）直接报
       `400 ... at most 30000 cells`。
    2. **接口会用空行把请求区域补满**。读 `A701:E1200` 会稳定返回 500 行**全空**，
       而不是空列表。所以「返回行数 < 请求行数 就结束」这种翻页条件**永远不触发** ——
       会把补齐的空行当数据一路读下去。曾因此误报某张表有 40000 行，实际只有 380 行。

    本函数按「遇到整块全空才停」翻页，并只去掉**末尾**的补齐空行；
    中间的空行（留白/分段）会保留。

    `sleep_s`：块与块之间的间隔。**连续快速整表读会招来 503**（像是限流，
    不是随机故障 —— 5 次退避重试都救不回来），所以默认留 0.3s 节流。
    """
    rows_per = chunk_rows_for(n_cols, chunk_rows)
    col = col_letter(n_cols)
    out: list[list[str]] = []
    r = 1
    while r <= max_rows:
        if r > 1 and sleep_s:
            time.sleep(sleep_s)
        code, payload = http_json(
            "GET",
            f"{API}/v1.0/doc/workbooks/{base_id}/sheets/{sheet_id}"
            f"/ranges/A{r}%3A{col}{r + rows_per - 1}"
            f"?operatorId={urllib.parse.quote(operator_id)}",
            token=token,
        )
        if code != 200:
            raise RuntimeError(_explain(code, payload, "整表读取"))
        dv = payload.get("displayValues")
        if dv is None:
            dv = payload.get("values") or []
        if not dv:
            break
        if all(is_blank_row(x) for x in dv):
            break                      # 整块空 = 数据到头了
        out.extend(dv)
        r += rows_per
    # 只裁掉末尾补齐的空行；中间空行是真实数据
    while out and is_blank_row(out[-1]):
        out.pop()
    return out


def sheet_id_by_name(sheets: list[dict], name: str) -> str:
    """按名字找 sheetId（允许前后空格差异）。"""
    want = (name or "").strip()
    for s in sheets:
        if (s.get("name") or "").strip() == want:
            return s["id"]
    raise KeyError(f"没有名为 {name!r} 的 sheet；可用: {[s.get('name') for s in sheets]}")


def _explain(code: int, payload, action: str) -> str:
    """把三种 operatorId 相关错误讲清楚，避免下次再试半天。"""
    msg = ""
    if isinstance(payload, dict):
        msg = f"{payload.get('code', '')} / {payload.get('message', '')}"
    else:
        msg = str(payload)[:200]
    hint = ""
    if "MissingoperatorId" in msg:
        hint = "  → 缺 operatorId（必须是真实 unionId）"
    elif "forbidden.accessDenied" in msg or "no permission" in msg:
        hint = "  → 该 unionId 对本文档无访问权限，换一个有权限的同事"
    elif "paramError-operatorId" in msg:
        hint = "  → operatorId 格式不对，unionId 才能通过（appKey/AgentId 都不行）"
    return f"{action}失败 http={code} body={msg}{hint}"
