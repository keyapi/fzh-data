# -*- coding: utf-8 -*-
"""Google 表「渠道账号」→ 规范渠道账号（钉钉下拉/txt 前缀/Colab 口径）。

快照来自 ``channel_account_sync/out/channel_account_gsheet.json``（gitignore）。
- 读取时打印 snapshot mtime + 行数；超过 30 天打印 WARN。
- **metadata（C1）**：快照应带 ``snapshot`` 段（fetched_at/source/content_hash/业务投影
  hash，见 ``channel_account_sync/snapshot.py``）。缺失或校验失败的快照**只能诊断**，
  ``require_metadata=True`` 时直接拒绝 —— 发布门禁走这条，且不看文件 mtime（``touch``
  不能刷新新鲜度）。
- **缓存按内容 hash 失效**：同一进程内快照刷新后立即生效，不会继续用旧 map。
- 别名映射冲突**不再静默 last-wins**：只有大小写/零宽/全角规范化后相同的别名保留
  first-wins + 醒目 WARN；其它真正的歧义直接 ``raise``，逼维护人回表修别名。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
GSHEET_JSON = _REPO / "channel_account_sync" / "out" / "channel_account_gsheet.json"
SNAPSHOT_ENV = "CHANNEL_ACCOUNT_SNAPSHOT"
STALE_DAYS = 30

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)

# (path, 内容 sha256, require_metadata) -> maps。按内容 hash 失效，替换 lru_cache。
_CACHE: dict[tuple, tuple[dict[str, str], dict[str, str]]] = {}


def snapshot_path() -> Path:
    raw = os.environ.get(SNAPSHOT_ENV, "").strip()
    return Path(raw) if raw else GSHEET_JSON


def norm_token(s: str) -> str:
    """别名比较口径：NFKC（全角→半角）+ 去零宽 + 去空白 + 大写。"""
    s = unicodedata.normalize("NFKC", str(s or ""))
    return re.sub(r"\s+", "", s.translate(_ZERO_WIDTH)).upper()


def snapshot_meta(path: Path | None = None) -> dict | None:
    """读取快照里的 ``snapshot`` metadata（旧快照返回 None）。"""
    p = path or snapshot_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    meta = raw.get("snapshot")
    return meta if isinstance(meta, dict) else None


def snapshot_status(path: Path | None = None) -> dict:
    """诊断用：metadata + 校验问题（不抛错）。"""
    p = path or snapshot_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"path": str(p), "meta": None, "problems": [f"快照不可读: {e}"]}
    from channel_account_sync.snapshot import validate_snapshot

    return {"path": str(p), "meta": raw.get("snapshot"), "problems": validate_snapshot(raw)}


def load_account_maps(require_metadata: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    """norm_token -> canonical 渠道账号；canonical -> 表上原样字符串（大小写）。

    ``require_metadata=True``：快照必须有真实抓取时间/来源/内容 hash 且未过默认 TTL，
    否则 ``ValueError``（发布门禁用）。默认 False 保留诊断能力。
    """
    path = snapshot_path()
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    key = (str(path), digest, bool(require_metadata))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    raw = json.loads(raw_bytes.decode("utf-8"))
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    rows = raw.get("rows") or []
    age_days = (datetime.now() - mtime).days
    print(f"[channel_canonical] snapshot={path.name} mtime={mtime:%Y-%m-%d %H:%M} rows={len(rows)}")
    meta = raw.get("snapshot")
    if isinstance(meta, dict):
        print(f"[channel_canonical] fetched_at={meta.get('fetched_at')} schema={meta.get('schema_version')}")
    else:
        print(
            "[channel_canonical][WARN] 快照缺 metadata（fetched_at/source/content_hash），"
            "只能用于诊断，不得用于发布；请重跑 channel_account_sync/fetch_sources.py",
            file=sys.stderr,
        )
    if age_days > STALE_DAYS:
        print(
            f"[channel_canonical][WARN] 渠道账号快照文件已 {age_days} 天未更新（>{STALE_DAYS} 天），"
            "可能缺新账号/新别名；重跑 channel_account_sync/fetch_sources.py",
            file=sys.stderr,
        )
    if require_metadata:
        from channel_account_sync.snapshot import validate_snapshot

        problems = validate_snapshot(raw)
        if problems:
            raise ValueError("渠道账号快照不可用于发布: " + "; ".join(problems))

    header = raw["header"][:]
    # 旧布局（20260521 前）第 3 列是样例账号名，没有「渠道账号」列；只有**确实缺列**时才改名，
    # 不能把已有的「渠道账号别名」覆盖成「渠道账号」（会把别名当账号）。
    if "渠道账号" not in header and len(header) >= 3 and "渠道" in header:
        header[2] = "渠道账号"

    from channel_account_sync.plan import sheet_records  # noqa: WPS433

    recs, _ = sheet_records(header, rows)
    to_canon: dict[str, str] = {}
    display: dict[str, str] = {}
    # token -> (canon, [raw 写法])，只在出现第二个不同 canon 时记为冲突
    conflicts: dict[str, tuple[str, list[str]]] = {}
    first_raw: dict[str, str] = {}
    for rec in recs:
        if (rec.get("渠道") or "").strip() != "Amazon":
            continue
        canon = (rec.get("渠道账号") or "").strip()
        if not canon.upper().startswith("AMZ"):
            continue
        display[norm_token(canon)] = canon
        keys = [canon] + [p.strip() for p in re.split(r"[,，]", rec.get("渠道账号别名") or "") if p.strip()]
        for key in keys:
            token = norm_token(key)
            prior = to_canon.get(token)
            if prior is not None and prior != canon:
                first_canon, forms = conflicts.get(token, (prior, [first_raw.get(token, key)]))
                conflicts[token] = (first_canon, sorted(set(forms + [key])))
                continue
            to_canon[token] = canon
            first_raw.setdefault(token, key)

    hard: list[str] = []
    case_only: list[str] = []
    for token, (first_canon, forms) in conflicts.items():
        label = f"{token}: {first_canon} vs {sorted(set(forms))}"
        # 只有「仅大小写不同」算可容忍的第一条优先；全角/零宽/空格差异是**真歧义**。
        if len({f.casefold() for f in forms}) == 1:
            case_only.append(label)
        else:
            hard.append(label)
    if case_only:
        print(
            "[channel_canonical][WARN] 别名冲突（仅大小写/全角/零宽不同，保留表上第一条，与 Colab 一致）："
            + "; ".join(case_only),
            file=sys.stderr,
        )
    if hard:
        raise ValueError(
            "渠道账号别名冲突（同一别名指向不同渠道账号），请先在「渠道账号」表修别名: "
            + "; ".join(hard)
        )
    result = (to_canon, display)
    _CACHE.clear()
    _CACHE[key] = result
    return result


# 兼容旧测试/调用（tests 会调用 load_account_maps.cache_clear()）。
load_account_maps.cache_clear = _CACHE.clear  # type: ignore[attr-defined]


def canonical_account(raw: str) -> str:
    """钉钉销售账户 / 文件名前缀 → 表上渠道账号列原样写法。"""
    a = (raw or "").strip()
    if not a:
        return ""
    to_canon, display = load_account_maps()
    hit = to_canon.get(norm_token(a))
    if hit:
        return display.get(norm_token(hit), hit)
    # 已是 AMZ 前缀但未收录：原样返回（去空白）
    if a.upper().startswith("AMZ"):
        return re.sub(r"\s+", "", a)
    return a
