# -*- coding: utf-8 -*-
"""Google 表「渠道账号」→ 规范渠道账号（钉钉下拉/txt 前缀/Colab 口径）。

快照来自 ``channel_account_sync/out/channel_account_gsheet.json``（gitignore）。
- 读取时打印 snapshot mtime + 行数；超过 30 天打印 WARN。
- 别名映射冲突**不再静默 last-wins**：只有大小写不同的同名别名（Colab 也是 upper 后去重，
  会取第一条）保留 first-wins + 醒目 WARN；其它真正的歧义直接 ``raise``，
  逼维护人回表修别名。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
GSHEET_JSON = _REPO / "channel_account_sync" / "out" / "channel_account_gsheet.json"
SNAPSHOT_ENV = "CHANNEL_ACCOUNT_SNAPSHOT"
STALE_DAYS = 30


def snapshot_path() -> Path:
    raw = os.environ.get(SNAPSHOT_ENV, "").strip()
    return Path(raw) if raw else GSHEET_JSON


def norm_token(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).upper()


@lru_cache(maxsize=1)
def load_account_maps() -> tuple[dict[str, str], dict[str, str]]:
    """norm_token -> canonical 渠道账号；canonical -> 表上原样字符串（大小写）。"""
    path = snapshot_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    rows = raw.get("rows") or []
    age_days = (datetime.now() - mtime).days
    print(f"[channel_canonical] snapshot={path.name} mtime={mtime:%Y-%m-%d %H:%M} rows={len(rows)}")
    if age_days > STALE_DAYS:
        print(
            f"[channel_canonical][WARN] 渠道账号快照已 {age_days} 天未更新（>{STALE_DAYS} 天），"
            "可能缺新账号/新别名；重跑 channel_account_sync/fetch_sources.py",
            file=sys.stderr,
        )

    header = raw["header"][:]
    if len(header) > 2 and header[2] != "渠道账号":
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
        if len({f.casefold() for f in forms}) == 1:
            case_only.append(label)
        else:
            hard.append(label)
    if case_only:
        print(
            "[channel_canonical][WARN] 别名冲突（仅大小写不同，保留表上第一条，与 Colab 一致）："
            + "; ".join(case_only),
            file=sys.stderr,
        )
    if hard:
        raise ValueError(
            "渠道账号别名冲突（同一别名指向不同渠道账号），请先在「渠道账号」表修别名: "
            + "; ".join(hard)
        )
    return to_canon, display


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
