# -*- coding: utf-8 -*-
"""批量翻译 EN 物料组中文名 → item_group_translation（腾讯云 TMT）。

范围（生产「产品」子树）:
  - is_group=0 的叶子节点（约 410）
  - is_leaf_group=1 的叶子组 LGKS（约 14，与上集不重叠）

用法:
  uv run python translate_item_group_names.py --dry-run          # 默认：拉取 + TMT 翻译，写 Excel，不写 EN
  uv run python translate_item_group_names.py --dry-run --fetch-only   # 仅拉中文，缺密钥也可
  uv run python translate_item_group_names.py --apply            # 写回 EN（需用户确认后再跑）

环境变量（EN_API/.env 或根 .env）:
  ERP_API_KEY / ERP_API_SECRET          生产 EN（或 PROD_ERP_API_*）
  TENCENT_SECRET_ID / TENCENT_SECRET_KEY   或 TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY
  TENCENT_TMT_REGION  可选，默认 ap-guangzhou
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)
_OUT = _DIR / "out"
_OUT.mkdir(parents=True, exist_ok=True)

_ENV_URLS = {"test": "https://ensh.vilavi.cn", "prod": "https://erpnext.vilavi.cn"}
_ENV_KEYS = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}

COL_SEQ = "序号"
COL_NAME = "name"
COL_IG_NAME = "物料组名"
COL_MODEL = "custom_model_id"
COL_PARENT = "父级"
COL_NODE_TYPE = "节点类型"
COL_ZH = "中文"
COL_EN = "英文"
COL_EXISTING = "现有翻译"
COL_RESULT = "处理结果"
COL_STATUS = "状态"
COL_NOTE = "备注"

TMT_MAX_CHARS = 1800  # 单次请求总字符上限（文档 2000，留余量）
TMT_QPS_SLEEP = 0.25  # 5 次/秒


def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


_load_dotenv([
    _DIR / ".env",
    _DIR.parent / ".env",
    _DIR.parent.parent / ".env",
])


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.headers["Accept"] = "application/json"
        self.session.mount("https://", _NoExpectAdapter())

    def fetch_all_item_groups(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/resource/Item Group"
        fields = [
            "name",
            "item_group_name",
            "parent_item_group",
            "is_group",
            "is_leaf_group",
            "custom_model_id",
            "item_group_translation",
            "custom_disabled",
        ]
        resp = self._get(url, params={
            "fields": json.dumps(fields),
            "limit_page_length": "0",
        })
        return resp.json().get("data", [])

    def update_translation(self, name: str, en: str) -> None:
        url = f"{self.base_url}/api/resource/Item Group/{requests.utils.quote(name, safe='')}"
        self._get(url, method="PUT", json={"item_group_translation": en})

    def _get(self, url: str, method: str = "GET", **kwargs: Any) -> requests.Response:
        last: Exception | None = None
        for attempt in range(3):
            try:
                r = self.session.request(method, url, timeout=(60, 120), **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last = e
                if attempt < 2:
                    time.sleep(3)
        raise last  # type: ignore[misc]


def _to_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def _under_product(name: str, idx: dict[str, dict]) -> bool:
    seen: set[str] = set()
    cur = name
    while cur and cur in idx and cur not in seen:
        if cur == "产品":
            return True
        seen.add(cur)
        cur = _to_str(idx[cur].get("parent_item_group"))
    return False


def select_targets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    idx = {d["name"]: d for d in rows if d.get("name")}
    targets: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for d in rows:
        name = _to_str(d.get("name"))
        if not name or name == "产品" or not _under_product(name, idx):
            continue
        is_leaf = int(d.get("is_group") or 0) == 0
        is_leaf_group = int(d.get("is_leaf_group") or 0) == 1
        if not is_leaf and not is_leaf_group:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        zh = _to_str(d.get("item_group_name")) or name
        if is_leaf_group and int(d.get("is_group") or 0) == 1:
            node_type = "叶子组(LGKS)"
        elif is_leaf:
            mid = _to_str(d.get("custom_model_id"))
            node_type = "KS叶子" if mid.startswith("KS") else "叶子(非KS)"
        else:
            node_type = "其他"
        targets.append({
            "name": name,
            "item_group_name": zh,
            "custom_model_id": _to_str(d.get("custom_model_id")),
            "parent_item_group": _to_str(d.get("parent_item_group")),
            "is_leaf_group": is_leaf_group,
            "node_type": node_type,
            "zh": zh,
            "existing_en": _to_str(d.get("item_group_translation")),
        })
    targets.sort(key=lambda x: (x["node_type"], x["custom_model_id"] or "zzz", x["name"]))
    return targets


def load_tencent_credentials() -> tuple[str, str, str]:
    sid = (
        os.getenv("TENCENT_SECRET_ID")
        or os.getenv("TENCENTCLOUD_SECRET_ID")
        or ""
    )
    sk = (
        os.getenv("TENCENT_SECRET_KEY")
        or os.getenv("TENCENTCLOUD_SECRET_KEY")
        or ""
    )
    region = os.getenv("TENCENT_TMT_REGION", "ap-guangzhou")
    return sid, sk, region


def chunk_by_char_limit(texts: list[str], max_chars: int) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for t in texts:
        tlen = len(t)
        if current and current_len + tlen > max_chars:
            batches.append(current)
            current = []
            current_len = 0
        current.append(t)
        current_len += tlen
    if current:
        batches.append(current)
    return batches


def translate_batch_tmt(
    texts: list[str],
    secret_id: str,
    secret_key: str,
    region: str,
) -> list[str]:
    from tencentcloud.common import credential
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.tmt.v20180321 import tmt_client

    cred = credential.Credential(secret_id, secret_key)
    http_profile = HttpProfile()
    http_profile.endpoint = "tmt.tencentcloudapi.com"
    http_profile.reqTimeout = 60
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    client = tmt_client.TmtClient(cred, region, client_profile)

    def _one(zh: str) -> str:
        body = client.call(
            "TextTranslate",
            {
                "SourceText": zh,
                "Source": "zh",
                "Target": "en",
                "ProjectId": 0,
            },
        )
        resp = json.loads(body)
        if "Error" in resp.get("Response", {}):
            err = resp["Response"]["Error"]
            raise RuntimeError(f"{err.get('Code')}: {err.get('Message')}")
        return str(resp["Response"].get("TargetText") or "").strip()

    # SDK 精简包无 TextTranslateBatch 模型，逐条调用（本批 424 条约 2 分钟）
    out: list[str] = []
    for i, zh in enumerate(texts, 1):
        try:
            out.append(_one(zh))
        except (TencentCloudSDKException, RuntimeError) as e:
            raise RuntimeError(f"TMT 翻译失败 [{i}/{len(texts)}] {zh!r}: {e}") from e
        if i < len(texts):
            time.sleep(TMT_QPS_SLEEP)
    return out


def translate_all(
    targets: list[dict[str, Any]],
    secret_id: str,
    secret_key: str,
    region: str,
) -> tuple[int, int, list[str]]:
    """返回 (成功数, 失败数, 错误列表)。"""
    need = [t for t in targets if t["zh"]]
    texts = [t["zh"] for t in need]
    batches = chunk_by_char_limit(texts, TMT_MAX_CHARS)
    zh_to_en: dict[str, str] = {}
    errors: list[str] = []
    ok = 0
    fail = 0

    offset = 0
    for bi, batch in enumerate(batches, 1):
        print(f"  TMT 批次 {bi}/{len(batches)}: {len(batch)} 条, {sum(len(x) for x in batch)} 字符")
        try:
            ens = translate_batch_tmt(batch, secret_id, secret_key, region)
            for zh, en in zip(batch, ens):
                zh_to_en[zh] = en.strip()
                ok += 1
        except RuntimeError as e:
            msg = str(e)
            errors.append(f"批次{bi}: {msg}")
            for zh in batch:
                fail += 1
                zh_to_en.setdefault(zh, "")
        if bi < len(batches):
            time.sleep(TMT_QPS_SLEEP)
        offset += len(batch)

    for t in targets:
        t["en"] = zh_to_en.get(t["zh"], "")
        if not t["zh"]:
            t["result"] = "跳过"
            t["status"] = "空中文名"
            t["note"] = ""
        elif t["en"]:
            t["result"] = "成功"
            t["status"] = "已翻译"
            t["note"] = ""
        else:
            t["result"] = "失败"
            t["status"] = "TMT失败"
            t["note"] = errors[-1] if errors else "无译文"
    return ok, fail, errors


def build_report_rows(targets: list[dict[str, Any]], *, fetch_only: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, t in enumerate(targets, 1):
        if fetch_only:
            result, status, note = "待翻译", "缺TMT密钥", "请配置 TENCENT_SECRET_ID/KEY 后重跑"
            en = ""
        else:
            result = t.get("result", "待翻译")
            status = t.get("status", "")
            note = t.get("note", "")
            en = t.get("en", "")
        rows.append({
            COL_SEQ: i,
            COL_NAME: t["name"],
            COL_IG_NAME: t["item_group_name"],
            COL_MODEL: t["custom_model_id"],
            COL_PARENT: t["parent_item_group"],
            COL_NODE_TYPE: t["node_type"],
            COL_ZH: t["zh"],
            COL_EN: en,
            COL_EXISTING: t["existing_en"],
            COL_RESULT: result,
            COL_STATUS: status,
            COL_NOTE: note,
        })
    return rows


def write_excel(
    detail_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    path: Path,
) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame([summary]).to_excel(w, sheet_name="汇总", index=False)
        pd.DataFrame(detail_rows).to_excel(w, sheet_name="明细", index=False)


def apply_updates(client: ErpnextClient, targets: list[dict[str, Any]], dry_run: bool) -> tuple[int, int, int]:
    ok = skip = fail = 0
    for t in targets:
        if t.get("result") != "成功" or not t.get("en"):
            skip += 1
            continue
        if t.get("existing_en") == t["en"]:
            t["result"] = "跳过"
            t["status"] = "已有相同译文"
            skip += 1
            continue
        if dry_run:
            ok += 1
            continue
        try:
            client.update_translation(t["name"], t["en"])
            ok += 1
            time.sleep(0.15)
        except requests.RequestException as e:
            fail += 1
            t["result"] = "失败"
            t["status"] = "写回EN失败"
            t["note"] = str(e)[:200]
    return ok, skip, fail


def resolve_erp_creds(env: str) -> tuple[str, str, str]:
    base = _ENV_URLS[env]
    key_var, sec_var = _ENV_KEYS[env]
    key = os.getenv(key_var) or (os.getenv("ERP_API_KEY") if env == "prod" else "")
    sec = os.getenv(sec_var) or (os.getenv("ERP_API_SECRET") if env == "prod" else "")
    if not key or not sec:
        raise SystemExit(f"缺少 {key_var}/{sec_var}（生产可用 ERP_API_KEY/SECRET）")
    return base, key, sec


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="物料组中文名 → item_group_translation (TMT)")
    ap.add_argument("--env", choices=["test", "prod"], default="prod")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="只出报告，不写 EN（默认）")
    ap.add_argument("--apply", action="store_true", help="写回 item_group_translation")
    ap.add_argument("--fetch-only", action="store_true",
                    help="仅拉取中文名单，不调用 TMT")
    args = ap.parse_args()
    dry_run = not args.apply

    base, key, sec = resolve_erp_creds(args.env)
    print(f"环境: {args.env} ({base})")
    print(f"模式: {'DRY-RUN' if dry_run else 'APPLY'}"
          f"{' + 仅拉取' if args.fetch_only else ''}")

    client = ErpnextClient(base, key, sec)
    print("拉取 Item Group …")
    all_rows = client.fetch_all_item_groups()
    targets = select_targets(all_rows)
    print(f"目标节点: {len(targets)}")
    by_type: dict[str, int] = {}
    for t in targets:
        by_type[t["node_type"]] = by_type.get(t["node_type"], 0) + 1
    for k, v in sorted(by_type.items()):
        print(f"  {k}: {v}")

    tmt_ok = tmt_fail = 0
    tmt_errors: list[str] = []
    sid, sk, region = load_tencent_credentials()

    if args.fetch_only or not sid or not sk:
        if not args.fetch_only:
            print("未配置 TENCENT_SECRET_ID / TENCENT_SECRET_KEY → 仅输出中文名单")
        args.fetch_only = True
    else:
        print(f"TMT 区域: {region}")
        tmt_ok, tmt_fail, tmt_errors = translate_all(targets, sid, sk, region)
        print(f"TMT: 成功 {tmt_ok} 失败 {tmt_fail}")

    detail = build_report_rows(targets, fetch_only=args.fetch_only)

    apply_ok = apply_skip = apply_fail = 0
    if args.apply and not args.fetch_only:
        print("写回 EN …")
        apply_ok, apply_skip, apply_fail = apply_updates(client, targets, dry_run=False)
        detail = build_report_rows(targets, fetch_only=False)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "fetch" if args.fetch_only else ("dryrun" if dry_run else "apply")
    out_path = _OUT / f"物料组翻译_{suffix}_{ts}.xlsx"

    success = sum(1 for r in detail if r[COL_RESULT] == "成功")
    skipped = sum(1 for r in detail if r[COL_RESULT] == "跳过")
    failed = sum(1 for r in detail if r[COL_RESULT] == "失败")
    pending = sum(1 for r in detail if r[COL_RESULT] == "待翻译")

    summary = {
        "总行数": len(detail),
        "KS叶子": by_type.get("KS叶子", 0),
        "叶子组LGKS": by_type.get("叶子组(LGKS)", 0),
        "成功": success,
        "跳过": skipped,
        "失败": failed,
        "待翻译": pending,
        "TMT成功": tmt_ok,
        "TMT失败": tmt_fail,
        "写回成功": apply_ok,
        "写回跳过": apply_skip,
        "写回失败": apply_fail,
        "处理时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "模式": suffix,
    }
    write_excel(detail, summary, out_path)
    print(f"\n报告: {out_path}")
    print(f"汇总: 入 {len(detail)} | 成功 {success} | 跳过 {skipped} | 失败 {failed} | 待翻译 {pending}")
    if tmt_errors:
        print("TMT 错误:")
        for e in tmt_errors[:5]:
            print(f"  - {e}")

    # 样例
    print("\n样例（前 8 条）:")
    for r in detail[:8]:
        print(f"  {r[COL_ZH]} → {r[COL_EN] or '(空)'}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
