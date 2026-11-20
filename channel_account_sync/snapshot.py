# -*- coding: utf-8 -*-
"""渠道账号快照的 metadata / 业务投影 hash（C1：来源、新鲜度、可核验）。

背景（gate_remediation_plan_20261120.md U-C，审计 M03/T03）：旧快照只有 Google 表
``get_all_values`` 的原始行，**没有抓取时间、来源标识和内容 hash**；读取端只能看文件
mtime（``touch`` 一下就能刷新），也无法证明 live 与快照是同一批身份映射。

本模块定义 ``MasterSnapshot`` 的稳定契约：

- ``fetched_at``：真实抓取时间（ISO8601，带时区），**不是文件 mtime**；
- ``source``：spreadsheet_id / worksheet / gid，防止拿错表的快照发布；
- ``content_hash``：整表（header+rows）的 sha256，全表变化留痕；
- ``business_projection_hashes``：按 ``运营人员{YYYYMM}`` 逐月计算的业务投影 hash，
  只覆盖渠道/渠道账号/别名/当期运营人员（无关历史人员列变化不误报）；
- ``rows`` / ``header_hash``：截断/换表头可被发现。

纯标准库，不依赖 pandas；写快照（``fetch_sources.py``）与读快照（``channel_canonical``、
``amazon_period_tax/master_data.py``）共用同一套 hash 口径。
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = "v1"

# 建议值，**未经业务批准**（计划 U-C：TTL 未批准 = 不允许用旧快照发布，取保守 24h）。
DEFAULT_TTL_HOURS = 24.0
# 允许的时钟偏移（抓取端与本机时间略有差异不当作“未来时间”）。
FUTURE_TOLERANCE = timedelta(minutes=5)

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)

_SHEET_ALIAS_COL = "渠道账号别名"
_SHEET_ACCOUNT_COL = "渠道账号"
_SHEET_CHANNEL_COL = "渠道"
_MONTH_COL_RE = re.compile(r"^运营人员(\d{6})$")


def norm_alias(value: str | None) -> str:
    """别名规范化：NFKC + 去零宽 + 去空白 + 大写（别名比较/hash 的唯一口径）。"""
    s = unicodedata.normalize("NFKC", str(value or ""))
    s = s.translate(_ZERO_WIDTH)
    return re.sub(r"\s+", "", s).upper()


def resolve_header(header: list[str]) -> list[str]:
    """与 ``phase3_merge.load_channel_accounts`` 一致：第 3 列常是样例账号名。"""
    h = [str(x) for x in (header or [])]
    if _SHEET_ACCOUNT_COL not in h and len(h) >= 3 and _SHEET_CHANNEL_COL in h:
        h[2] = _SHEET_ACCOUNT_COL
    return h


def data_rows(header: list[str], rows: list[list]) -> list[list]:
    """去掉第一行（Google 导出常把表头又放一次在 rows[0]）。"""
    rows = [list(r) for r in (rows or [])]
    if rows and [str(x).strip() for x in rows[0][: len(header)]] == [str(x).strip() for x in header]:
        rows = rows[1:]
    return rows


def _cell(row: list, idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) and row[idx] is not None else ""


def _split_aliases(cell: str) -> list[str]:
    raw = str(cell or "").replace("，", ",")
    return [p.strip() for p in raw.split(",") if p.strip()]


def month_columns(header: list[str]) -> list[str]:
    return [c for c in resolve_header(header) if _MONTH_COL_RE.match(str(c))]


def business_projection(header: list[str], rows: list[list], exchange_month: str | None) -> list[dict]:
    """本批所需业务投影：渠道 / 渠道账号 / 别名（规范化）/ 当期运营人员。

    ``exchange_month`` 为空时使用表内**第一个** ``运营人员YYYYMM`` 列（用于整表 hash 快照）；
    指定月份但列不存在时返回空投影（由调用方判错）。
    """
    hdr = resolve_header(header)
    if _SHEET_ACCOUNT_COL not in hdr:
        raise ValueError(f"快照表头无法识别渠道账号列: {hdr[:8]!r}")
    i_acct = hdr.index(_SHEET_ACCOUNT_COL)
    i_chan = hdr.index(_SHEET_CHANNEL_COL) if _SHEET_CHANNEL_COL in hdr else None
    i_alias = hdr.index(_SHEET_ALIAS_COL) if _SHEET_ALIAS_COL in hdr else None
    months = month_columns(hdr)
    if exchange_month:
        staff_col = f"运营人员{exchange_month}"
        i_staff = hdr.index(staff_col) if staff_col in hdr else None
        if i_staff is None:
            return []
    elif months:
        i_staff = hdr.index(months[0])
    else:
        i_staff = None

    out: list[dict] = []
    for row in data_rows(hdr, rows):
        account = _cell(row, i_acct)
        if not account:
            continue
        aliases = {norm_alias(account)}
        if i_alias is not None:
            aliases.update(norm_alias(a) for a in _split_aliases(_cell(row, i_alias)))
        aliases.discard("")
        staff = _cell(row, i_staff) if i_staff is not None else ""
        out.append(
            {
                "渠道": _cell(row, i_chan) if i_chan is not None else "",
                "渠道账号": account,
                "aliases": sorted(aliases),
                "运营人员": staff or None,
            }
        )
    out.sort(key=lambda r: (r["渠道账号"].upper(), r["渠道"] or "", r["运营人员"] or "", r["aliases"]))
    return out


def projection_hash(projection: list[dict]) -> str:
    payload = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def header_hash(header: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(list(header), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def content_hash(header: list[str], rows: list[list]) -> str:
    """整表内容 hash（含表头与原始行顺序），只做留痕/截断检测，不用于业务投影比较。"""
    payload = json.dumps(
        {"header": list(header), "rows": [list(r) for r in rows]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_source(sheet: dict) -> dict:
    return {
        "kind": "google_sheet",
        "spreadsheet_id": sheet.get("spreadsheet_id"),
        "spreadsheet_title": sheet.get("spreadsheet_title"),
        "worksheet": sheet.get("target_title"),
        "gid": sheet.get("target_gid"),
    }


def build_metadata(
    sheet: dict,
    *,
    fetched_at: datetime | None = None,
    exchange_months: list[str] | None = None,
) -> dict:
    """构造快照 metadata；``fetched_at`` 默认当前 UTC 时间（写入端必须真实抓取后调用）。"""
    header = sheet.get("header") or []
    rows = sheet.get("rows") or []
    months = exchange_months if exchange_months is not None else [
        m[len("运营人员") :] for m in month_columns(header)
    ]
    projections = {}
    for month in months:
        projections[str(month)] = projection_hash(business_projection(header, rows, str(month)))
    fetched = fetched_at or datetime.now(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": fetched.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "source": snapshot_source(sheet),
        "rows": len(rows),
        "header_hash": header_hash(header),
        "content_hash": content_hash(header, rows),
        "business_projection_hashes": projections,
    }


def attach_metadata(
    sheet: dict,
    *,
    fetched_at: datetime | None = None,
    exchange_months: list[str] | None = None,
) -> dict:
    """返回带 ``snapshot`` metadata 的新 dict（不修改入参）。"""
    out = dict(sheet)
    out["snapshot"] = build_metadata(sheet, fetched_at=fetched_at, exchange_months=exchange_months)
    return out


def parse_fetched_at(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:  # 无时区的时间不能证明新鲜度
        return None
    return dt


def validate_snapshot(
    snapshot: dict,
    *,
    exchange_month: str | None = None,
    now: datetime | None = None,
    ttl_hours: float | None = DEFAULT_TTL_HOURS,
    expected_source: dict | None = None,
) -> list[str]:
    """校验快照 metadata + 内容 hash（+ 指定月的业务投影 hash）。返回问题清单。"""
    problems: list[str] = []
    meta = (snapshot or {}).get("snapshot")
    if not isinstance(meta, dict) or not meta:
        return ["快照缺 metadata（fetched_at/source/content_hash）；旧快照只能诊断，不得用于发布"]

    if meta.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"快照 schema_version={meta.get('schema_version')!r} != {SCHEMA_VERSION!r}"
        )
    fetched = parse_fetched_at(meta.get("fetched_at"))
    now = now or datetime.now(timezone.utc)
    if fetched is None:
        problems.append("快照 fetched_at 缺失或非法（无时区/格式错误）")
    else:
        if fetched > now + FUTURE_TOLERANCE:
            problems.append(f"快照 fetched_at={fetched.isoformat()} 在未来（时钟/伪造）")
        elif ttl_hours is not None:
            age_hours = (now - fetched).total_seconds() / 3600.0
            if age_hours > ttl_hours:
                problems.append(
                    f"快照已过期：抓取于 {fetched.isoformat()}（{age_hours:.1f}h > TTL {ttl_hours}h）"
                )

    source = meta.get("source") or {}
    if not source.get("spreadsheet_id"):
        problems.append("快照 source 缺 spreadsheet_id")
    if expected_source:
        for key, want in expected_source.items():
            if want is not None and source.get(key) != want:
                problems.append(f"快照 source.{key}={source.get(key)!r} != 期望 {want!r}")

    header = snapshot.get("header") or []
    rows = snapshot.get("rows") or []
    if meta.get("rows") is not None and int(meta["rows"]) != len(rows):
        problems.append(f"快照行数不符：metadata={meta['rows']} 实际 rows={len(rows)}")
    if meta.get("header_hash") and meta["header_hash"] != header_hash(header):
        problems.append("快照 header_hash 与当前表头不符")
    if not meta.get("content_hash"):
        problems.append("快照缺 content_hash")
    elif meta["content_hash"] != content_hash(header, rows):
        problems.append("快照 content_hash 与当前内容不符（内容被改动或损坏）")

    if exchange_month:
        hashes = meta.get("business_projection_hashes") or {}
        if exchange_month not in hashes:
            problems.append(f"快照缺 {exchange_month} 业务投影 hash（该月列未收录）")
        else:
            try:
                actual = projection_hash(business_projection(header, rows, exchange_month))
            except ValueError as e:
                problems.append(f"快照业务投影无法计算: {e}")
            else:
                if actual != hashes[exchange_month]:
                    problems.append(
                        f"快照 {exchange_month} 业务投影 hash 不符（渠道/账号/别名/当期人员被改动）"
                    )
    return problems
