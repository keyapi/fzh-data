# -*- coding: utf-8 -*-
"""D 批 Amazon 三方对账内核（**只读**）：赛狐结算组 ↔ 账期桶 txt ↔ 钉钉 OA。

对应 ``gate_remediation_plan_20261120.md`` U-D 与 ``gate_audit_20261120.md``：

- **D1 应有集**：``settlementSummary/groupPage`` 覆盖目标月（可加已批准的迟交边界），
  分页必须完整。负/0/未转账/处理中记录**全部保留**，不以 paid 定义是否应有。每个 group
  标 ``included`` / ``excluded_by_approved_policy`` / ``needs_review``；API 缺字段、早停、
  分页总数矛盾、重复页一律 :class:`ReconciliationError`（写前 FAIL）。
- **D2 group ↔ txt**：按 ``settlement-id`` 连接。总额口径：
  ``transferAmount != 0`` 用转账额（正结转的正常打款）；``transferAmount == 0``（未转账 /
  负结转）用 ``accountNetIncome``，**不因 0 判错**。同 sid 多版本 / V1+V2 双份 →
  ``needs_review``。
- **D3 OA ↔ txt/group**：按规范账号 + 结算结束日（仅允许**已批准**的日期容差）+ 原币金额
  ``abs(diff) <= Decimal('0.01')``。OA 用「账期收款额」对净额；「销售额」口径不同，只保留
  不参与比对（100 倍差只诊断，不自动 ÷100）。
- **D4 输出分区**：``group_only`` / ``txt_only`` / ``oa_only`` / ``pair_only`` /
  ``matched_triplet`` / ``ambiguous`` / ``amount_mismatch`` / ``period_mismatch`` /
  ``identity_conflict``。所有源记录/键/金额/差额保留；每个源记录恰好一个终态。例外绑定
  reason_code / 原键 / scope / 批准角色·时间·有效期；过期或换 hash 的例外失效，且**不改写
  成 PASS**，只标 ``approved_exception``。

本模块不读写任何表 / GSheet / NAS / Excel；txt 事实来自 E1 ``read_bucket_amz_txts`` 的
同一次读取结果（不重复扫描）。
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable

# 所有 Amazon 同口径金额比较的唯一容差；禁止 5% / 0.05 宽匹配。
AMOUNT_TOLERANCE = Decimal("0.01")

PARTITIONS = (
    "matched_triplet",
    "pair_only",
    "group_only",
    "txt_only",
    "oa_only",
    "ambiguous",
    "amount_mismatch",
    "period_mismatch",
    "identity_conflict",
)
# D1 的 group 状态（不属于三方分区，但必须显式计数）
STATE_EXCLUDED_BY_POLICY = "excluded_by_approved_policy"
STATE_NEEDS_REVIEW = "needs_review"
ALL_STATES = PARTITIONS + (STATE_EXCLUDED_BY_POLICY, STATE_NEEDS_REVIEW)

# groupPage 必备字段：缺任何一项都不能继续（写前 FAIL，不降级成 warning）。
GROUP_REQUIRED_FIELDS = (
    "settlementId",
    "groupId",
    "currency",
    "transferAmount",
    "accountNetIncome",
    "storeName",
    "processingStatusStr",
    "fundTransferStatusStr",
)
# 至少有一个，用于站点身份
GROUP_SITE_FIELDS = ("marketplaceName", "marketplaceId")
GROUP_END_FIELDS = ("siteGroupEndStr", "groupEndStr")
GROUP_TRANSFER_DATE_FIELDS = ("siteFundTransferDateStr", "utcFundTransferDateStr")

# 币种别名（申明式，不猜）：OA 下拉里出现过 ``墨西哥比索(MXI)`` 这一拼写。
CURRENCY_ALIASES = {"MXI": "MXN", "RMB": "CNY"}


class ReconciliationError(RuntimeError):
    """结构性失败：API 缺字段 / 早停 / 分页总数矛盾 / 重复页 / 重复结算号。"""


# --------------------------------------------------------------- 基础转换


def to_decimal(value) -> Decimal | None:
    """API / DataFrame 数值 → Decimal（空值 None；非有限值报错）。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"金额非有限值: {value!r}")
        return value
    if isinstance(value, bool):
        raise ValueError("布尔值不是金额")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"金额非有限值: {value!r}")
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    s = str(value).strip()
    if s.lower() in {"", "nan", "none", "<na>", "nat", "null"}:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"金额非法: {value!r}") from None
    if not d.is_finite():
        raise ValueError(f"金额非有限值: {value!r}")
    return d


def norm_currency(value) -> str | None:
    """`欧元(EUR)` / `EUR` / `eur` → `EUR`；别名表只在**声明**范围内生效。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    m = re.search(r"\(([A-Za-z]{3})\)", s)
    code = (m.group(1) if m else s).upper()
    return CURRENCY_ALIASES.get(code, code)


def parse_date(value) -> date | None:
    """支持 ``2026/07/29 09:16:07``、``2026-07-29``、``29.07.2026 ...``。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def month_of(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:7] if len(value) >= 7 else None
    return f"{value.year:04d}-{value.month:02d}"


def day_diff(a: date, b: date) -> int:
    return abs((a - b).days)


# --------------------------------------------------------------- 例外账本


@dataclass(frozen=True)
class ExceptionEntry:
    """一条批准例外。没有批准角色/时间/有效期即视为无效（不默认 approve）。"""

    reason_code: str
    key: str
    scope: str = "settlement"
    approver_role: str = ""
    approved_at: str = ""
    valid_until: str = ""
    policy_hash: str = ""
    payload: dict = field(default_factory=dict)

    def invalidity(self, *, today: date, observed_hash: str | None = None) -> str | None:
        if not self.approver_role.strip() or not self.approved_at.strip():
            return "exception_missing_approval"
        approved = parse_date(self.approved_at)
        if approved is None:
            return "exception_bad_approved_at"
        if approved > today:
            return "exception_approved_in_future"
        if self.valid_until:
            until = parse_date(self.valid_until)
            if until is None:
                return "exception_bad_valid_until"
            if today > until:
                return "exception_expired"
        bound = str(self.payload.get("sha256") or "").lower()
        if bound:
            if not observed_hash:
                return "exception_hash_unverifiable"
            if observed_hash.lower() != bound:
                return "exception_hash_changed"
        if not self.key:
            return "exception_missing_key"
        return None

    def is_valid(self, *, today: date, observed_hash: str | None = None) -> bool:
        return self.invalidity(today=today, observed_hash=observed_hash) is None


class ExceptionBook:
    """批准例外集合；lookup 只返回**有效**条目，过期/换 hash 自动失效。"""

    def __init__(self, entries: Iterable[ExceptionEntry] = ()):
        self.entries = list(entries)

    @classmethod
    def from_json(cls, path: str | Path) -> "ExceptionBook":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = []
        for item in raw.get("entries") or []:
            entries.append(
                ExceptionEntry(
                    reason_code=str(item.get("reason_code") or "").upper(),
                    key=str(item.get("key") or ""),
                    scope=str(item.get("scope") or "settlement"),
                    approver_role=str(item.get("approver_role") or ""),
                    approved_at=str(item.get("approved_at") or ""),
                    valid_until=str(item.get("valid_until") or ""),
                    policy_hash=str(item.get("policy_hash") or ""),
                    payload=item.get("payload") or {},
                )
            )
        return cls(entries)

    def lookup(
        self,
        reason_code: str,
        keys: Iterable[str],
        *,
        today: date,
        observed_hash: str | None = None,
    ) -> ExceptionEntry | None:
        wanted = {str(k) for k in keys if k}
        code = reason_code.upper()
        for entry in self.entries:
            if entry.reason_code != code:
                continue
            if not ({entry.key, "*"} & wanted):
                continue
            if entry.is_valid(today=today, observed_hash=observed_hash):
                return entry
        return None

    def date_tolerance_days(self, account: str | None, *, today: date) -> tuple[int, ExceptionEntry | None]:
        """已批准的 OA↔结算日容差；没有批准就是 0 天。"""
        if not account:
            return 0, None
        entry = self.lookup("DATE_TOLERANCE", [account, "*"], today=today)
        if not entry:
            return 0, None
        try:
            days = int(entry.payload.get("days", 0))
        except (TypeError, ValueError):
            return 0, entry
        return max(0, days), entry


# --------------------------------------------------------------- 结算组


@dataclass
class GroupFact:
    settlement_id: str
    group_id: str
    store_name: str
    marketplace: str
    currency: str
    account: str | None
    end_date: date | None
    transfer_date: date | None
    transfer_amount: Decimal | None
    account_net_income: Decimal | None
    account_income: Decimal | None
    account_refund: Decimal | None
    account_expenditure: Decimal | None
    beginning_balance: Decimal | None
    ending_balance: Decimal | None
    processing_status: str
    transfer_status: str
    raw: dict = field(default_factory=dict)
    # 分类结果
    state: str = "included"
    reason: str | None = None
    approval: dict | None = None

    @property
    def compare_amount(self) -> Decimal | None:
        """D2 口径：非零转账额优先；transfer==0（未转账/负结转）用净收入。"""
        if self.transfer_amount is not None and self.transfer_amount != 0:
            return self.transfer_amount
        return self.account_net_income

    @property
    def compare_rule(self) -> str:
        if self.transfer_amount is not None and self.transfer_amount != 0:
            return "transfer_amount"
        return "account_net_income"


def _first_raw(raw: dict, names: Iterable[str]) -> Any:
    for n in names:
        v = raw.get(n)
        if v not in (None, ""):
            return v
    return None


def parse_group(raw: dict, store_to_account: dict[str, str] | None = None) -> GroupFact:
    """单条 groupPage 记录 → :class:`GroupFact`；缺必备字段直接 FAIL。"""
    missing = [f for f in GROUP_REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ReconciliationError(f"groupPage 记录缺字段 {missing}: {raw!r}"[:400])
    blank = [
        f
        for f in ("settlementId", "groupId", "currency", "storeName", "processingStatusStr", "fundTransferStatusStr")
        if raw.get(f) in (None, "")
    ]
    if blank:
        raise ReconciliationError(f"groupPage 记录关键字段为空 {blank}: {raw!r}"[:400])
    if _first_raw(raw, GROUP_SITE_FIELDS) is None:
        raise ReconciliationError(f"groupPage 记录缺 marketplaceName/marketplaceId: {raw!r}"[:400])
    end_raw = _first_raw(raw, GROUP_END_FIELDS)
    if end_raw is None:
        raise ReconciliationError(f"groupPage 记录缺结算结束日 siteGroupEndStr/groupEndStr: {raw!r}"[:400])
    end_date = parse_date(end_raw)
    if end_date is None:
        raise ReconciliationError(f"groupPage 记录结算结束日非法 {end_raw!r}")

    transfer = to_decimal(raw.get("transferAmount"))
    net = to_decimal(raw.get("accountNetIncome"))
    if transfer is None or net is None:
        raise ReconciliationError(f"groupPage 记录金额为空 settlementId={raw.get('settlementId')}")

    store = str(raw.get("storeName") or "").strip()
    account = (store_to_account or {}).get(store)
    return GroupFact(
        settlement_id=str(raw.get("settlementId")),
        group_id=str(raw.get("groupId")),
        store_name=store,
        marketplace=str(_first_raw(raw, GROUP_SITE_FIELDS) or ""),
        currency=norm_currency(raw.get("currency")) or "",
        account=account,
        end_date=end_date,
        transfer_date=parse_date(_first_raw(raw, GROUP_TRANSFER_DATE_FIELDS)),
        transfer_amount=transfer,
        account_net_income=net,
        account_income=to_decimal(raw.get("accountIncome")),
        account_refund=to_decimal(raw.get("accountRefund")),
        account_expenditure=to_decimal(raw.get("accountExpenditure")),
        beginning_balance=to_decimal(raw.get("beginningBalance")),
        ending_balance=to_decimal(raw.get("endingBalance")),
        processing_status=str(raw.get("processingStatusStr") or ""),
        transfer_status=str(raw.get("fundTransferStatusStr") or ""),
        raw=dict(raw),
    )


@dataclass
class GroupFetchResult:
    groups: list[GroupFact]
    start: str
    end: str
    pages: list[dict]
    total_size: int | None
    diagnostics: list[str] = field(default_factory=list)


def fetch_groups(
    post: Callable[[str, dict], Any],
    start: str,
    end: str,
    *,
    page_size: int = 200,
    store_to_account: dict[str, str] | None = None,
    path: str = "/api/financial/v2/settlementSummary/groupPage.json",
    max_pages: int = 1000,
) -> GroupFetchResult:
    """拉取完整 groupPage，并做 D1 完整性校验。

    ``post(body)`` 返回接口原始 dict（``groupVoList``/``rows`` + ``totalPage``/``totalSize``）。
    任何一项不完整都抛 :class:`ReconciliationError`（调用方在写前拒绝发布）。
    """
    page = 1
    rows: list[dict] = []
    pages: list[dict] = []
    seen_page_fp: dict[tuple, int] = {}
    seen_group_ids: set[str] = set()
    declared_total_page: int | None = None
    declared_total_size: int | None = None

    while True:
        if page > max_pages:
            raise ReconciliationError(f"groupPage 分页超过上限 {max_pages} 页，疑似死循环")
        body = {
            "timeType": "settlementEndTime",
            "startTime": start,
            "endTime": end,
            "pageNo": str(page),
            "pageSize": str(page_size),
            "isSite": True,
        }
        data = post(path, body)
        if not isinstance(data, dict):
            raise ReconciliationError(f"groupPage 返回非对象: {type(data).__name__}")
        page_rows = data.get("groupVoList")
        if page_rows is None:
            page_rows = data.get("rows")
        if page_rows is None:
            raise ReconciliationError("groupPage 返回缺 groupVoList/rows 字段")
        if not isinstance(page_rows, list):
            raise ReconciliationError("groupPage rows 不是列表")
        total_page = data.get("totalPage")
        if total_page in (None, ""):
            raise ReconciliationError("groupPage 返回缺 totalPage")
        total_page = int(total_page)
        total_size = data.get("totalSize")
        if total_size not in (None, ""):
            total_size = int(total_size)
        if declared_total_page is None:
            declared_total_page, declared_total_size = total_page, total_size
        else:
            if total_page != declared_total_page:
                raise ReconciliationError(
                    f"groupPage 分页总数矛盾: 首页 totalPage={declared_total_page} 第{page}页={total_page}"
                )
            if total_size is not None and declared_total_size is not None and total_size != declared_total_size:
                raise ReconciliationError(
                    f"groupPage totalSize 中途变化: {declared_total_size} → {total_size}"
                )
        pages.append({"page": page, "totalPage": total_page, "totalSize": total_size, "rows": len(page_rows)})

        # 重复页：同一批 groupId 整页重复返回（分页参数未生效）
        fp = tuple(str(r.get("groupId") or "") for r in page_rows)
        if page_rows:
            if fp in seen_page_fp:
                raise ReconciliationError(
                    f"groupPage 重复页: 第{page}页与第{seen_page_fp[fp]}页内容完全相同"
                )
            seen_page_fp[fp] = page
        for raw in page_rows:
            gid = str(raw.get("groupId") or "")
            if gid and gid in seen_group_ids:
                raise ReconciliationError(f"groupPage 跨页重复 groupId={gid}")
            if gid:
                seen_group_ids.add(gid)
        rows.extend(page_rows)

        if page >= total_page:
            break
        if not page_rows:
            raise ReconciliationError(
                f"groupPage 早停: totalPage={total_page} 但第{page}页为空（仅拉到 {len(rows)} 行）"
            )
        page += 1

    if declared_total_size is not None and declared_total_size != len(rows):
        raise ReconciliationError(
            f"groupPage 分页总数矛盾: totalSize={declared_total_size} 实际行数={len(rows)}"
        )
    if declared_total_page is not None and len(pages) != declared_total_page:
        raise ReconciliationError(
            f"groupPage 分页总数矛盾: totalPage={declared_total_page} 实际页数={len(pages)}"
        )

    groups = [parse_group(raw, store_to_account) for raw in rows]
    return GroupFetchResult(
        groups=groups,
        start=start,
        end=end,
        pages=pages,
        total_size=declared_total_size,
    )


def load_cached_groups(path: str | Path, store_to_account: dict[str, str] | None = None) -> GroupFetchResult:
    """离线读取冻结的 groupPage 原始 JSON（``{"window": [...], "groups": [...]}``）。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("groups") or []
    window = raw.get("window") or ["", ""]
    groups = [parse_group(r, store_to_account) for r in rows]
    pages = raw.get("pages") or [{"page": 1, "totalPage": 1, "totalSize": len(rows), "rows": len(rows)}]
    return GroupFetchResult(
        groups=groups,
        start=str(window[0]),
        end=str(window[1]),
        pages=pages,
        total_size=raw.get("total_size", len(rows)),
    )


def store_account_map(header: list[str], rows: list[list]) -> dict[str, str]:
    """渠道主数据快照：``赛狐店铺`` → ``渠道账号``（只读，未知店铺不猜）。"""
    if not header or not rows:
        return {}
    hdr = [str(h).strip() for h in header]
    if "赛狐店铺" not in hdr or "渠道账号" not in hdr:
        return {}
    si, ai = hdr.index("赛狐店铺"), hdr.index("渠道账号")
    out: dict[str, str] = {}
    for row in rows:
        if len(row) <= max(si, ai):
            continue
        store = str(row[si] or "").strip()
        account = str(row[ai] or "").strip()
        if store and account and store != "赛狐店铺":
            out[store] = account
    return out


# --------------------------------------------------------------- txt 事实


@dataclass
class TxtFact:
    settlement_id: str
    rel: str
    bucket: str
    account: str | None
    currency: str | None
    end_date: date | None
    deposit_date: date | None
    header_total: Decimal | None
    detail_net: Decimal | None
    schema: str | None
    sha256: str | None
    rows: int
    approval: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def amount(self) -> Decimal | None:
        return self.header_total if self.header_total is not None else self.detail_net


def _cell_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    s = str(value).strip()
    return "" if s.lower() in {"nan", "none", "<na>", "nat", "null"} else s


def _is_missing_numeric(value) -> bool:
    """NaN / Inf / pd.NA / NaT 等不能当金额送入严格解析。"""
    if value is None:
        return True
    if isinstance(value, float) and not math.isfinite(value):
        return True
    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return False


def txt_facts_from_read(
    df,
    ledger,
    *,
    used_states: Iterable[str] = ("used",),
) -> tuple[list[TxtFact], list[dict]]:
    """把 E1 那次读桶结果（df + SourceLedger）转成按 settlement-id 的结算事实。

    返回 ``(facts, non_used_inventory)``；不在 ``used`` 终态的文件只进 inventory，
    不进入三方对账（不重复计数、不静默消失）。
    """
    used = set(used_states)
    inventory: list[dict] = []
    rec_by_rel: dict[str, Any] = {}
    for rec in getattr(ledger, "records", []):
        if getattr(rec, "is_candidate", False):
            rec_by_rel[str(rec.rel)] = rec
            if rec.state not in used:
                inventory.append(
                    {
                        "rel": rec.rel,
                        "bucket": rec.bucket,
                        "state": rec.state,
                        "reason": rec.reason,
                        "settlement_id": rec.settlement_id,
                        "account": rec.account,
                        "sha256": rec.sha256,
                    }
                )
    facts: list[TxtFact] = []
    if df is None or getattr(df, "empty", True):
        return facts, inventory
    needed = {"文件名", "子文件夹名", "settlement-id"}
    if not needed.issubset(df.columns):
        raise ReconciliationError(f"读桶结果缺列 {sorted(needed - set(df.columns))}，无法生成 txt 结算事实")

    work = df.copy()
    work["_rel"] = work["子文件夹名"].astype(str) + "/" + work["文件名"].astype(str)
    for (rel, sid), part in work.groupby(["_rel", "settlement-id"], dropna=False, sort=True):
        sid = _cell_str(sid)
        if not sid:
            continue
        rec = rec_by_rel.get(rel)
        if rec is not None and rec.state not in used:
            continue
        amount_col = "amount" if "amount" in part.columns else None
        detail = Decimal("0")
        if amount_col:
            for v in part[amount_col].tolist():
                if _is_missing_numeric(v):
                    continue
                d = to_decimal(v)
                if d is not None:
                    detail += d
        header = None
        if "total-amount" in part.columns:
            for v in part["total-amount"].tolist():
                if _is_missing_numeric(v):
                    continue
                header = to_decimal(v)
                break
        currency = None
        if "currency" in part.columns:
            for v in part["currency"].tolist():
                c = norm_currency(v)
                if c:
                    currency = c
                    break
        end = deposit = None
        for col, attr in (("settlement-end-date", "end_date"), ("deposit-date", "deposit_date")):
            if col in part.columns:
                for v in part[col].tolist():
                    d = parse_date(v)
                    if d is not None:
                        if attr == "end_date":
                            end = d
                        else:
                            deposit = d
                        break
        facts.append(
            TxtFact(
                settlement_id=sid,
                rel=rel,
                bucket=str(rec.bucket) if rec is not None else "",
                account=(str(rec.account) if rec is not None and rec.account else None),
                currency=currency,
                end_date=end,
                deposit_date=deposit,
                header_total=header,
                detail_net=detail if amount_col else None,
                schema=(str(rec.schema) if rec is not None and rec.schema else None),
                sha256=(str(rec.sha256) if rec is not None and rec.sha256 else None),
                rows=int(len(part)),
                approval=(str(getattr(rec, "approval", "") or "") or None) if rec is not None else None,
            )
        )
    return facts, inventory


# --------------------------------------------------------------- OA 事实


@dataclass
class OaFact:
    row_id: str
    approval_id: str
    account: str
    currency: str | None
    settle_date: date | None
    amount: Decimal | None
    sales_amount: Decimal | None
    platform: str
    person: str
    submit_class: str
    raw: dict = field(default_factory=dict)
    state: str = "oa_only"
    reason: str | None = None
    exception: dict | None = None


def _oa_amount(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    if s.lower() in {"", "nan", "none", "<na>", "nat", "null"}:
        return None
    return to_decimal(s.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", s) else s)


def oa_facts_from_frame(
    df,
    period: str,
    *,
    book: ExceptionBook | None = None,
    today: date | None = None,
    canonical_account: Callable[[str], str] | None = None,
) -> tuple[list[OaFact], list[dict], list[str]]:
    """钉钉宽表 → OA 事实；只取 Amazon + 目标月（含已批准迟交边界）。

    返回 ``(facts, out_of_scope_rows, problems)``。``out_of_scope_rows`` 是同一导出的
    其它平台/其它账期行，保留计数以便追溯但不参与本期对账。
    """
    if df is None or getattr(df, "empty", True):
        return [], [], []
    book = book or ExceptionBook()
    today = today or date.today()
    canon = canonical_account or (lambda s: str(s or "").strip())
    required = {"选择平台", "账期日期", "销售账户_展开", "账期收款额"}
    problems = [f"OA 导出缺列 {sorted(required - set(df.columns))}"] if not required.issubset(df.columns) else []
    if problems:
        raise ReconciliationError(problems[0])

    facts: list[OaFact] = []
    out_of_scope: list[dict] = []
    for _, row in df.iterrows():
        platform = _cell_str(row.get("选择平台"))
        account_raw = _cell_str(row.get("销售账户_展开"))
        if platform != "亚马逊":
            out_of_scope.append({"reason": "not_amazon", "platform": platform, "account": account_raw})
            continue
        settle_date = parse_date(row.get("账期日期"))
        row_month = month_of(settle_date)
        in_period = row_month == period
        approval = None
        if not in_period:
            approval = book.lookup(
                "OUT_OF_PERIOD",
                [f"oa:{_cell_str(row.get('审批编号'))}", f"oa:{account_raw}:{row_month}", f"oa:*"],
                today=today,
            )
            if not approval:
                out_of_scope.append(
                    {
                        "reason": "other_period",
                        "platform": platform,
                        "account": account_raw,
                        "date": settle_date.isoformat() if settle_date else None,
                        "month": row_month,
                    }
                )
                continue
        account = canon(account_raw)
        amount = _oa_amount(row.get("账期收款额"))
        sales = _oa_amount(row.get("销售额"))
        approval_id = _cell_str(row.get("审批编号"))
        row_id = "|".join(
            [
                approval_id,
                settle_date.isoformat() if settle_date else "",
                account,
                "" if amount is None else format(amount, "f"),
            ]
        )
        facts.append(
            OaFact(
                row_id=row_id,
                approval_id=approval_id,
                account=account,
                currency=norm_currency(row.get("币种")),
                settle_date=settle_date,
                amount=amount,
                sales_amount=sales,
                platform=platform,
                person=_cell_str(row.get("销售账户_展开")),
                submit_class=_cell_str(row.get("提交分类")),
                raw={k: row.get(k) for k in row.index if k in {
                    "审批编号", "账期日期", "销售账户_展开", "币种", "账期收款额", "销售额",
                    "审批状态", "审批结果", "发起时间", "选择平台", "_sheet",
                }},
                exception=(approval.payload if approval else None),
            )
        )
    return facts, out_of_scope, problems


# --------------------------------------------------------------- 对账链接


@dataclass
class Link:
    settlement_id: str
    group: GroupFact | None = None
    txt: TxtFact | None = None
    oa: list[OaFact] = field(default_factory=list)
    state: str = STATE_NEEDS_REVIEW
    reason: str | None = None
    pair_kind: str | None = None
    amount_diff: Decimal | None = None
    group_amount: Decimal | None = None
    txt_amount: Decimal | None = None
    oa_amount: Decimal | None = None
    exception: dict | None = None
    blocking: bool = True
    group_txt_date_delta: int | None = None

    def to_dict(self) -> dict:
        return {
            "settlement_id": self.settlement_id,
            "state": self.state,
            "reason": self.reason,
            "pair_kind": self.pair_kind,
            "blocking": self.blocking,
            "group_amount": None if self.group_amount is None else str(self.group_amount),
            "txt_amount": None if self.txt_amount is None else str(self.txt_amount),
            "oa_amount": None if self.oa_amount is None else str(self.oa_amount),
            "amount_diff": None if self.amount_diff is None else str(self.amount_diff),
            "group_txt_date_delta": self.group_txt_date_delta,
            "group": None
            if not self.group
            else {
                "settlement_id": self.group.settlement_id,
                "group_id": self.group.group_id,
                "store_name": self.group.store_name,
                "marketplace": self.group.marketplace,
                "account": self.group.account,
                "currency": self.group.currency,
                "end_date": self.group.end_date.isoformat() if self.group.end_date else None,
                "transfer_amount": None if self.group.transfer_amount is None else str(self.group.transfer_amount),
                "account_net_income": None
                if self.group.account_net_income is None
                else str(self.group.account_net_income),
                "compare_rule": self.group.compare_rule,
                "processing_status": self.group.processing_status,
                "transfer_status": self.group.transfer_status,
                "group_state": self.group.state,
            },
            "txt": None
            if not self.txt
            else {
                "settlement_id": self.txt.settlement_id,
                "rel": self.txt.rel,
                "account": self.txt.account,
                "currency": self.txt.currency,
                "end_date": self.txt.end_date.isoformat() if self.txt.end_date else None,
                "deposit_date": self.txt.deposit_date.isoformat() if self.txt.deposit_date else None,
                "header_total": None if self.txt.header_total is None else str(self.txt.header_total),
                "detail_net": None if self.txt.detail_net is None else str(self.txt.detail_net),
                "schema": self.txt.schema,
                "sha256": self.txt.sha256,
                "rows": self.txt.rows,
                "approval": self.txt.approval,
            },
            "oa": [
                {
                    "row_id": o.row_id,
                    "approval_id": o.approval_id,
                    "account": o.account,
                    "currency": o.currency,
                    "settle_date": o.settle_date.isoformat() if o.settle_date else None,
                    "amount": None if o.amount is None else str(o.amount),
                    "sales_amount": None if o.sales_amount is None else str(o.sales_amount),
                    "person": o.person,
                    "submit_class": o.submit_class,
                    "state": o.state,
                    "reason": o.reason,
                }
                for o in self.oa
            ],
            "exception": self.exception,
        }


@dataclass
class ReconResult:
    period: str
    links: list[Link] = field(default_factory=list)
    groups: list[GroupFact] = field(default_factory=list)
    txt_facts: list[TxtFact] = field(default_factory=list)
    oa_facts: list[OaFact] = field(default_factory=list)
    txt_inventory: list[dict] = field(default_factory=list)
    oa_out_of_scope: dict | list = field(default_factory=dict)
    fetch_meta: dict = field(default_factory=dict)
    tolerance_policy: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    # ---------------------------------------------------------- 计数
    def partition_counts(self) -> dict[str, int]:
        out = {s: 0 for s in ALL_STATES}
        for link in self.links:
            out[link.state] = out.get(link.state, 0) + 1
        return out

    def source_counts(self) -> dict[str, dict[str, int]]:
        def blank() -> dict[str, int]:
            return {s: 0 for s in ALL_STATES}

        out = {"group": blank(), "txt": blank(), "oa": blank()}
        for link in self.links:
            if link.group:
                out["group"][link.state] += 1
            if link.txt:
                out["txt"][link.state] += 1
            for oa in link.oa:
                out["oa"][link.state] += 1
        return out

    def source_totals(self) -> dict[str, int]:
        return {
            "group": len(self.groups),
            "txt": len(self.txt_facts),
            "oa": len(self.oa_facts),
        }

    def assert_conservation(self) -> None:
        totals = self.source_totals()
        counts = self.source_counts()
        for kind in ("group", "txt", "oa"):
            mapped = sum(counts[kind].values())
            if mapped != totals[kind]:
                raise AssertionError(
                    f"{kind} 源记录不守恒: total={totals[kind]} 终态和={mapped} 明细={counts[kind]}"
                )

    # ---------------------------------------------------------- 门禁
    def blockers(self) -> list[str]:
        out: list[str] = list(self.problems)
        state_count = self.partition_counts()
        for state in (
            "ambiguous",
            "amount_mismatch",
            "period_mismatch",
            "identity_conflict",
            STATE_NEEDS_REVIEW,
        ):
            blocking = sum(1 for l in self.links if l.state == state and l.blocking)
            if blocking:
                out.append(f"{state}={blocking}")
        for state in ("group_only", "txt_only", "oa_only", "pair_only"):
            blocking = sum(1 for l in self.links if l.state == state and l.blocking)
            if blocking:
                out.append(f"UNREVIEWED-ORPHAN {state}={blocking}")
        non_used = [i for i in self.txt_inventory if i.get("state") not in ("used",)]
        failed = [i for i in non_used if i.get("state") == "failed"]
        review = [i for i in non_used if i.get("state") == "needs_review"]
        if failed:
            out.append(f"TXT-FAILED={len(failed)}")
        if review:
            out.append(f"TXT-NEEDS-REVIEW={len(review)}")
        return out

    @property
    def publishable(self) -> bool:
        return not self.blockers()

    # ---------------------------------------------------------- 输出
    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_totals": self.source_totals(),
            "partition_counts": self.partition_counts(),
            "source_counts": self.source_counts(),
            "tolerance_policy": self.tolerance_policy,
            "fetch": self.fetch_meta,
            "problems": self.problems,
            "blockers": self.blockers(),
            "publishable": self.publishable,
            "txt_inventory_non_used": self.txt_inventory,
            "oa_out_of_scope": self.oa_out_of_scope,
            "links": [l.to_dict() for l in self.links],
        }


def _identity_problem(group: GroupFact, txt: TxtFact) -> str | None:
    if txt.account:
        group.account = group.account or txt.account
    if group.account and txt.account and group.account != txt.account:
        return f"account group={group.account} txt={txt.account}"
    if group.currency and txt.currency and group.currency != txt.currency:
        return f"currency group={group.currency} txt={txt.currency}"
    # 结算日不参与身份判定：赛虎 siteGroupEnd 与 Amazon txt 的 UTC 结算日可能差 1 天，
    # 真正的身份键是 settlement-id（D2）；日期差只作为诊断保留。
    return None


def _txt_amount(txt: TxtFact) -> tuple[Decimal | None, str | None]:
    if txt.header_total is not None and txt.detail_net is not None:
        if abs(txt.header_total - txt.detail_net) > AMOUNT_TOLERANCE:
            return txt.header_total, f"header_detail_mismatch header={txt.header_total} detail={txt.detail_net}"
    if txt.header_total is None and txt.detail_net is None:
        return None, "txt_no_amount"
    return txt.amount, None


def _classify_group(g: GroupFact, period: str, book: ExceptionBook, today: date) -> None:
    if g.end_date is not None and month_of(g.end_date) == period:
        g.state = "included"
        return
    entry = book.lookup(
        "OUT_OF_PERIOD",
        [f"group:{g.settlement_id}", g.settlement_id, f"store:{g.store_name}"],
        today=today,
    )
    if entry is None:
        g.state = STATE_NEEDS_REVIEW
        g.reason = f"OUT_OF_PERIOD_NO_POLICY end={g.end_date} target={period}"
        return
    action = str(entry.payload.get("action") or "include").lower()
    g.approval = {
        "reason_code": entry.reason_code,
        "key": entry.key,
        "scope": entry.scope,
        "approver_role": entry.approver_role,
        "approved_at": entry.approved_at,
        "valid_until": entry.valid_until,
        "action": action,
    }
    if action == "exclude":
        g.state = STATE_EXCLUDED_BY_POLICY
        g.reason = f"APPROVED_EXCLUDE end={g.end_date} key={entry.key}"
    else:
        g.state = "included"
        g.reason = f"APPROVED_LATE_INCLUDE end={g.end_date} key={entry.key}"


def reconcile(
    period: str,
    groups: list[GroupFact],
    txt_facts: list[TxtFact],
    oa_facts: list[OaFact],
    *,
    book: ExceptionBook | None = None,
    today: date | None = None,
    txt_inventory: list[dict] | None = None,
    oa_out_of_scope: list[dict] | None = None,
    fetch_meta: dict | None = None,
    default_tolerance_days: int = 0,
) -> ReconResult:
    """执行三方对账并给出每源唯一终态。纯函数，不读写外部系统。"""
    book = book or ExceptionBook()
    today = today or date.today()
    result = ReconResult(
        period=period,
        groups=list(groups),
        txt_facts=list(txt_facts),
        oa_facts=list(oa_facts),
        txt_inventory=list(txt_inventory or []),
        oa_out_of_scope=list(oa_out_of_scope or []),
        fetch_meta=dict(fetch_meta or {}),
        tolerance_policy={"default_days": default_tolerance_days, "source": "builtin"},
    )

    # 1) D1：group 期间分类 + 重复结算号
    sid_multi: dict[str, int] = {}
    for g in groups:
        sid_multi[g.settlement_id] = sid_multi.get(g.settlement_id, 0) + 1
    for g in groups:
        _classify_group(g, period, book, today)
        if sid_multi[g.settlement_id] > 1 and g.state == "included":
            g.state = STATE_NEEDS_REVIEW
            g.reason = f"DUPLICATE_SETTLEMENT_ID groups={sid_multi[g.settlement_id]}"

    # 2) D2：同 sid txt 多版本 / V1+V2 双份 → needs_review（保留全部）
    by_sid_txt: dict[str, list[TxtFact]] = {}
    for t in txt_facts:
        by_sid_txt.setdefault(t.settlement_id, []).append(t)
    txt_conflict: dict[str, str] = {}
    for sid, facts in by_sid_txt.items():
        if len(facts) < 2:
            continue
        hashes = {f.sha256 for f in facts if f.sha256}
        schemas = {f.schema for f in facts if f.schema}
        if schemas == {"v1", "v2"}:
            tag = "V1_V2_DUAL"
        elif len(hashes) > 1:
            tag = "SID_MULTIPLE_VERSIONS"
        else:
            tag = "SID_MULTIPLE_FILES"
        txt_conflict[sid] = f"{tag} files={[f.rel for f in facts]}"

    # 3) 建立 group/txt 链接（按 settlement-id）
    links: dict[str, Link] = {}
    for g in groups:
        if g.state != "included":
            links[f"g:{g.settlement_id}:{g.group_id}"] = Link(
                settlement_id=g.settlement_id,
                group=g,
                state=g.state,
                reason=g.reason,
                blocking=True,
                exception=g.approval,
            )
            continue
        if g.settlement_id in txt_conflict:
            links[f"g:{g.settlement_id}:{g.group_id}"] = Link(
                settlement_id=g.settlement_id,
                group=g,
                state=STATE_NEEDS_REVIEW,
                reason=txt_conflict[g.settlement_id],
            )
            continue
        links[f"g:{g.settlement_id}:{g.group_id}"] = Link(
            settlement_id=g.settlement_id,
            group=g,
            state="group_only",
            pair_kind=None,
            group_amount=g.compare_amount,
        )
    for t in txt_facts:
        if t.settlement_id in txt_conflict:
            links[f"t:{t.rel}:{t.settlement_id}"] = Link(
                settlement_id=t.settlement_id,
                txt=t,
                state=STATE_NEEDS_REVIEW,
                reason=txt_conflict[t.settlement_id],
            )
            continue
        # 已有期内的 group 链接（未被 needs_review 占用）→ 合并
        merged = False
        for key, link in links.items():
            if link.group and link.group.settlement_id == t.settlement_id and link.state in ("group_only",):
                link.txt = t
                problem = _identity_problem(link.group, t)
                if link.group.end_date and t.end_date:
                    link.group_txt_date_delta = (t.end_date - link.group.end_date).days
                txt_amount, txt_problem = _txt_amount(t)
                link.txt_amount = txt_amount
                link.group_amount = link.group.compare_amount
                if problem:
                    link.state = "identity_conflict"
                    link.reason = problem
                elif txt_problem:
                    link.state = STATE_NEEDS_REVIEW
                    link.reason = txt_problem
                elif txt_amount is None or link.group_amount is None:
                    link.state = STATE_NEEDS_REVIEW
                    link.reason = "missing_amount"
                else:
                    diff = txt_amount - link.group_amount
                    link.amount_diff = diff
                    if abs(diff) > AMOUNT_TOLERANCE:
                        link.state = "amount_mismatch"
                        link.reason = (
                            f"group({link.group.compare_rule})={link.group_amount} txt={txt_amount}"
                        )
                    else:
                        link.state = "pair_only"
                        link.pair_kind = "group+txt"
                merged = True
                break
        if merged:
            continue
        links[f"t:{t.rel}:{t.settlement_id}"] = Link(
            settlement_id=t.settlement_id,
            txt=t,
            state="txt_only",
            txt_amount=_txt_amount(t)[0],
            reason=(f"PERIOD_EXCEPTION_INCLUDE {t.approval}" if t.approval else None),
        )

    # 4) D3：OA → 链接（账号 + 结算结束日[已批准容差] + 原币 ±0.01）
    accounts_with_tolerance: set[str] = set()
    for link in links.values():
        if link.group and link.group.account:
            accounts_with_tolerance.add(link.group.account)
        if link.txt and link.txt.account:
            accounts_with_tolerance.add(link.txt.account)
    tolerance_by_account: dict[str, int] = {}
    tolerance_entries: dict[str, dict] = {}
    for acct in sorted(accounts_with_tolerance):
        days, entry = book.date_tolerance_days(acct, today=today)
        if days <= 0:
            days = max(0, default_tolerance_days)
        tolerance_by_account[acct] = days
        if entry is not None:
            tolerance_entries[acct] = {
                "reason_code": entry.reason_code,
                "key": entry.key,
                "days": days,
                "approver_role": entry.approver_role,
                "approved_at": entry.approved_at,
                "valid_until": entry.valid_until,
            }
    if tolerance_entries:
        result.tolerance_policy = {
            "default_days": default_tolerance_days,
            "accounts": tolerance_entries,
            "source": "approved_exception",
        }

    def cand_ident(link: Link) -> tuple[str | None, str | None, Decimal | None, date | None]:
        if link.group:
            # 有 txt 时以 Amazon 结算表的 settlement-end-date 为准（group siteGroupEnd 可能差 1 天）
            end = link.txt.end_date if link.txt and link.txt.end_date else link.group.end_date
            return link.group.account, link.group.currency, link.group_amount, end
        if link.txt:
            return link.txt.account, link.txt.currency, link.txt_amount, link.txt.end_date
        return None, None, None, None

    def _eligible_links(*, require_unclaimed: bool):
        for link in links.values():
            if not (link.group or link.txt):
                continue
            # 已判定身份/期间冲突或非本期的 group 不再接受 OA 认领
            if link.state in (STATE_NEEDS_REVIEW, STATE_EXCLUDED_BY_POLICY, "identity_conflict"):
                continue
            if link.group and link.group.state != "included":
                continue
            if require_unclaimed and link.oa:
                continue
            yield link

    def _match_guard(oa: OaFact, link: Link) -> tuple[Decimal | None, date | None, int] | None:
        account, currency, amount, end_date = cand_ident(link)
        if not account or amount is None or oa.amount is None or not oa.settle_date or not end_date:
            return None
        if oa.account != account:
            return None
        if currency and oa.currency and currency != oa.currency:
            return None
        tol = tolerance_by_account.get(account, max(0, default_tolerance_days))
        return amount, end_date, tol

    def _exact_candidates(oa: OaFact) -> list[tuple[Link, int]]:
        out: list[tuple[Link, int]] = []
        for link in _eligible_links(require_unclaimed=False):
            guard = _match_guard(oa, link)
            if guard is None:
                continue
            amount, end_date, tol = guard
            delta = day_diff(oa.settle_date, end_date)
            if abs(oa.amount - amount) <= AMOUNT_TOLERANCE and delta <= tol:
                out.append((link, delta))
        return out

    def _near_candidates(oa: OaFact) -> tuple[list[tuple[Link, int]], list[Link]]:
        near_period: list[tuple[Link, int]] = []
        near_amount: list[Link] = []
        for link in _eligible_links(require_unclaimed=True):
            guard = _match_guard(oa, link)
            if guard is None:
                continue
            amount, end_date, tol = guard
            delta = day_diff(oa.settle_date, end_date)
            if abs(oa.amount - amount) <= AMOUNT_TOLERANCE:
                if delta > tol:
                    near_period.append((link, delta))
            elif delta <= tol:
                near_amount.append(link)
        return near_period, near_amount

    def _claim(link: Link, oa: OaFact, *, delta: int) -> None:
        link.oa.append(oa)
        link.oa_amount = oa.amount
        if link.state not in ("group_only", "pair_only", "txt_only"):
            # group↔txt 已冲突（金额/期间）：记录 OA 证据，但绝不升级成 PASS
            oa.state = link.state
            oa.reason = link.reason
            return
        if link.group and link.txt:
            link.state = "matched_triplet"
            link.pair_kind = None
            link.reason = f"DATE_TOLERANCE days={delta}" if delta else None
        elif link.group:
            link.state = "pair_only"
            link.pair_kind = "group+oa"
        else:
            link.state = "pair_only"
            link.pair_kind = "txt+oa"
        oa.state = link.state
        oa.reason = link.reason

    def _duplicate_claim(link: Link, oa: OaFact) -> None:
        for prev in link.oa:
            prev.state = "ambiguous"
            prev.reason = f"DUPLICATE_OA_CLAIM with {oa.row_id}"
        oa.state = "ambiguous"
        oa.reason = f"DUPLICATE_OA_CLAIM with {[p.row_id for p in link.oa]}"
        link.state = "ambiguous"
        link.reason = "DUPLICATE_OA_CLAIM"
        link.pair_kind = None
        link.oa.append(oa)

    def _ambiguous(oa: OaFact, cands: list[Link], reason: str) -> None:
        oa.state = "ambiguous"
        oa.reason = f"{reason} {[c.settlement_id for c in cands]}"
        for i, link in enumerate(cands):
            link.state = "ambiguous"
            link.reason = "MULTI_CANDIDATE"
            if i == 0:  # OA 只登记一次，守恒不重复计数
                link.oa.append(oa)
                link.oa_amount = oa.amount

    # 第一轮：只认「金额一致 + 日期在容差内」的唯一候选；先占位，避免近似候选抢走真匹配。
    pending: list[OaFact] = []
    for oa in oa_facts:
        oa.state = "oa_only"
        exact = _exact_candidates(oa)
        if len(exact) == 1:
            link, delta = exact[0]
            if link.oa:
                _duplicate_claim(link, oa)
            else:
                _claim(link, oa, delta=delta)
        elif len(exact) > 1:
            _ambiguous(oa, [c[0] for c in exact], "multi_candidate")
        else:
            pending.append(oa)

    # 第二轮：精确匹配失败的 OA 才看近似候选（绝不降级已认领的 triplet）。
    for oa in pending:
        near_period, near_amount = _near_candidates(oa)
        if len(near_period) == 1:
            link, delta = near_period[0]
            oa.state = "period_mismatch"
            oa.reason = f"date_delta={delta} tolerance={tolerance_by_account.get(oa.account, 0)}"
            link.state = "period_mismatch"
            link.reason = oa.reason
            link.oa.append(oa)
            link.oa_amount = oa.amount
            continue
        if len(near_period) > 1:
            _ambiguous(oa, [c[0] for c in near_period], "multi_period_candidate")
            continue
        if len(near_amount) == 1:
            link = near_amount[0]
            _, _, amount, _ = cand_ident(link)
            oa.state = "amount_mismatch"
            oa.reason = f"oa={oa.amount} source={amount} diff={oa.amount - amount}"
            link.state = "amount_mismatch"
            link.reason = oa.reason
            link.oa.append(oa)
            link.oa_amount = oa.amount
            continue
        if len(near_amount) > 1:
            _ambiguous(oa, near_amount, "multi_amount_candidate")
            continue
        # 真孤儿
        links[f"o:{oa.row_id}"] = Link(settlement_id=f"OA:{oa.row_id}", oa=[oa], state="oa_only")
        oa.state = "oa_only"

    # 5) 例外应用（不改写 PASS，只解除阻断并记录）
    for link in links.values():
        if link.state in (
            "ambiguous",
            "amount_mismatch",
            "period_mismatch",
            "identity_conflict",
            STATE_NEEDS_REVIEW,
        ):
            code = {
                "ambiguous": "AMBIGUOUS",
                "amount_mismatch": "AMOUNT_MISMATCH",
                "period_mismatch": "PERIOD_MISMATCH",
                "identity_conflict": "IDENTITY_CONFLICT",
                STATE_NEEDS_REVIEW: "NEEDS_REVIEW",
            }[link.state]
            keys = [link.settlement_id]
            if link.txt and link.txt.sha256:
                keys.append(f"{link.settlement_id}#sha256={link.txt.sha256}")
            if link.oa:
                keys.extend(oa.row_id for oa in link.oa)
            entry = book.lookup(
                code,
                keys,
                today=today,
                observed_hash=link.txt.sha256 if link.txt else None,
            )
            if entry is not None:
                link.exception = {
                    "reason_code": entry.reason_code,
                    "key": entry.key,
                    "scope": entry.scope,
                    "approver_role": entry.approver_role,
                    "approved_at": entry.approved_at,
                    "valid_until": entry.valid_until,
                }
                link.blocking = False
            continue
        if link.state in ("group_only", "txt_only", "oa_only", "pair_only"):
            code = {
                "group_only": "GROUP_WITHOUT_TXT_OA",
                "txt_only": "TXT_WITHOUT_GROUP_OA",
                "oa_only": "OA_WITHOUT_TXT_GROUP",
                "pair_only": "PAIR_WITHOUT_THIRD",
            }[link.state]
            keys = [link.settlement_id]
            if link.txt and link.txt.sha256:
                keys.append(f"{link.settlement_id}#sha256={link.txt.sha256}")
            entry = book.lookup(code, keys, today=today, observed_hash=link.txt.sha256 if link.txt else None)
            if entry is not None:
                link.exception = {
                    "reason_code": entry.reason_code,
                    "key": entry.key,
                    "scope": entry.scope,
                    "approver_role": entry.approver_role,
                    "approved_at": entry.approved_at,
                    "valid_until": entry.valid_until,
                }
                link.blocking = False

    result.links = sorted(links.values(), key=lambda l: (l.state, l.settlement_id))
    result.assert_conservation()
    return result


# --------------------------------------------------------------- 报告辅助


def summary_lines(result: ReconResult) -> list[str]:
    """人读摘要（写入报告/日志；不参与业务判断）。"""
    parts = result.partition_counts()
    totals = result.source_totals()
    counts = result.source_counts()
    lines = [
        f"period={result.period} group={totals['group']} txt={totals['txt']} oa={totals['oa']}",
        "partitions: "
        + " ".join(f"{k}={parts[k]}" for k in PARTITIONS if parts.get(k))
        + f" needs_review={parts.get(STATE_NEEDS_REVIEW, 0)}"
        + f" excluded_by_approved_policy={parts.get(STATE_EXCLUDED_BY_POLICY, 0)}",
    ]
    for kind in ("group", "txt", "oa"):
        lines.append(
            f"{kind} states: "
            + " ".join(f"{k}={v}" for k, v in counts[kind].items() if v)
        )
    lines.append("blockers: " + ("; ".join(result.blockers()) or "none"))
    return lines
