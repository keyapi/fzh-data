# -*- coding: utf-8 -*-
"""Google 表「渠道账号」→ 规范渠道账号（钉钉下拉/txt 前缀/Colab 口径）。"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
GSHEET_JSON = _REPO / "channel_account_sync" / "out" / "channel_account_gsheet.json"


def norm_token(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).upper()


@lru_cache(maxsize=1)
def load_account_maps() -> tuple[dict[str, str], dict[str, str]]:
    """norm_token -> canonical 渠道账号；canonical -> 表上原样字符串（大小写）。"""
    raw = json.loads(GSHEET_JSON.read_text(encoding="utf-8"))
    header = raw["header"][:]
    rows = raw["rows"]
    if len(header) > 2 and header[2] != "渠道账号":
        header[2] = "渠道账号"

    from channel_account_sync.plan import sheet_records  # noqa: WPS433

    recs, _ = sheet_records(header, rows)
    to_canon: dict[str, str] = {}
    display: dict[str, str] = {}
    for rec in recs:
        if (rec.get("渠道") or "").strip() != "Amazon":
            continue
        canon = (rec.get("渠道账号") or "").strip()
        if not canon.upper().startswith("AMZ"):
            continue
        display[norm_token(canon)] = canon
        to_canon[norm_token(canon)] = canon
        for part in re.split(r"[,，]", rec.get("渠道账号别名") or ""):
            p = part.strip()
            if p:
                to_canon[norm_token(p)] = canon
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
