# -*- coding: utf-8 -*-
"""修正策略（F 批）：预授权政策 + proposal/authorization 凭据 + 写前门禁 + 发布清单绑定。

对应 ``gate_remediation_plan_20261120.md`` U-F 与 ``correction_policy_20261120.md``：

- **政策**从 **git 外 JSON** 加载（``schema_version`` / 授权人 / 生效期 / 允许类别 /
  已关账期间 / 单条与批次影响上限 / 允许平台与字段 / TTL）。结构非法、未生效、已过期、
  TTL 超时一律 **FAIL**，不是 warning。
- **T1**（币种书写、去重副本、已验 V1、格式、仅大小写同账号别名）在政策有效时默认自动，
  但仍要求逐条凭据（``rule`` + 证据 hash）。
- **T2**（金额、账号归属、日期、跨月）只有「未关账 ∧ 类别在政策内 ∧ 平台/字段允许 ∧
  唯一硬证据 ∧ 单条与批次影响 ≤ 上限」才 ``auto_allowed``；否则 ``preview``，
  写入口必须 FAIL。
- **T3/T4**（缺件待核 / 未知账号、缺人员、别名冲突、非法金额、期间不明）保持阻断，
  人工签字也不能绕过——先修来源再重跑。
- 凭据里的 ``proposal_hash`` 绑定 before/after、行指纹、证据 hash 与影响额；内容一变
  旧授权即失效。``policy_hash`` 绑定政策原文，政策改版旧 PASS 失效。
- **只计算不写表**：本模块不写 GSheet / NAS / Excel，也不发送任何通知。

T2 加固（R1–R4，``reports/t2_hardening_20261120.md``）：

- **R1 人民币预算**：单条/批次上限按 **CNY** 判定——原币差乘已确认目标月 FX；
  纯文本（账号/日期/币种）修正按受影响金额规模（``affected_amount``）计价，不能是 0；
  同一期间 + 同源版本的累计影响跨 run 累加，正负号不抵消（每条取绝对值），防拆 run。
  缺 FX / 币种未确认 → 阻断（writer=0）。
- **R2 授权链**：``approved`` 不再只靠一个字符串——正式发布要求带
  ``authorization`` 凭据（绑定 proposal hash、授权依据、角色、时间、scope）。
- **R4 旧 PASS 失效**：写前用**当前**政策重新判定已存凭据，旧 ``auto_allowed``
  遇到 T2 关闭/政策改版必须拒绝；依赖 hash（input/master/FX/FBA/例外/证据/政策/
  proposal/目标基线）任一变化即旧 PASS 失效。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

POLICY_SCHEMA_VERSION = 1

TIER_T1 = "T1"
TIER_T2 = "T2"
TIER_T3 = "T3"
TIER_T4 = "T4"
TIER_UNKNOWN = "UNKNOWN"

STATUS_AUTO_ALLOWED = "auto_allowed"
STATUS_APPROVED = "approved"
STATUS_PREVIEW = "preview"
STATUS_BLOCKED = "blocked"

_PUBLISHABLE_STATUSES = frozenset({STATUS_AUTO_ALLOWED, STATUS_APPROVED})

# 问题类别 → 等级。未知类别一律按 T4 阻断（不能靠"没写 kind"绕过授权）。
KIND_TIERS: dict[str, str] = {
    # T1：确定性表示修复
    "currency_representation": TIER_T1,
    "duplicate_copy": TIER_T1,
    "v1_format": TIER_T1,
    "account_alias_case": TIER_T1,
    # T2：改变金额/经济主体/归属期间
    "amount_100x": TIER_T2,
    "amount_value": TIER_T2,
    "account_attribution": TIER_T2,
    "date_shift": TIER_T2,
    "cross_month": TIER_T2,
    # T3：缺件待核
    "missing_attachment": TIER_T3,
    # T4：主数据/结构缺失
    "unknown_account": TIER_T4,
    "missing_staff": TIER_T4,
    "alias_conflict": TIER_T4,
    "invalid_amount": TIER_T4,
    "unknown_period": TIER_T4,
}

_MD5_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PERIOD_RE = re.compile(r"^\d{6}$")


class PolicyError(ValueError):
    """政策 JSON 结构非法 / 不能用于授权。"""


# ------------------------------------------------------------------ 基础工具


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def digest(data: Any) -> str:
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


def _dec_str(value: Decimal) -> str:
    """Decimal → 稳定字符串：500.00 与 5E+2 都归一成 500。"""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _as_decimal(value, *, label: str, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise PolicyError(f"{label} 必须是数字: {value!r}")
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise PolicyError(f"{label} 不是合法十进制: {value!r}") from None
    if not d.is_finite():
        raise PolicyError(f"{label} 非有限值: {value!r}")
    if minimum is not None and d < minimum:
        raise PolicyError(f"{label} 不能小于 {minimum}: {value!r}")
    return d


def _parse_dt(value, *, label: str) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise PolicyError(f"{label} 不是 ISO 时间: {value!r}") from None


def _aware(dt: datetime) -> datetime:
    """naive 时间按本地时区解释，避免 policy(带时区) 与 now(naive) 比较抛 TypeError。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


def _now(now: datetime | None) -> datetime:
    return _aware(now) if now is not None else datetime.now().astimezone()


def _str_set(raw, *, label: str) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str) or not isinstance(raw, Iterable):
        raise PolicyError(f"{label} 必须是字符串数组")
    out: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise PolicyError(f"{label} 含空/非字符串项: {item!r}")
        out.add(item.strip())
    return frozenset(out)


# ------------------------------------------------------------------ 政策


@dataclass(frozen=True)
class CorrectionPolicy:
    """预授权的修正政策；``raw`` 是原 JSON，``hash`` 是原文规范化的 sha256。"""

    policy_id: str
    version: str
    authorized_by: str
    created_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    ttl_hours: Decimal | None
    auto_apply_t1: bool
    t2_enabled: bool
    t2_categories: frozenset[str]
    t2_platforms: frozenset[str]
    t2_fields: frozenset[str]
    closed_periods: frozenset[str]
    max_single_impact: Decimal
    max_batch_impact: Decimal
    raw: Mapping[str, Any] = field(repr=False, compare=False)
    hash: str = ""
    # R1/R2 加固开关：由政策显式声明；写入口（正式发布）强制按 True 处理。
    t2_require_fx: bool = False
    t2_require_receipt: bool = False
    authorization_roles: frozenset[str] = frozenset()

    def allows_platform(self, platform: str) -> bool:
        return str(platform or "").strip() in self.t2_platforms


def parse_policy(data: Mapping[str, Any], *, source: str = "<memory>") -> CorrectionPolicy:
    """把政策 JSON 解析成对象；任何结构问题直接 ``PolicyError``。"""
    if not isinstance(data, Mapping):
        raise PolicyError(f"{source}: 政策顶层必须是 JSON 对象")
    schema = data.get("schema_version")
    if schema != POLICY_SCHEMA_VERSION:
        raise PolicyError(
            f"{source}: schema_version={schema!r} 不受支持（需要 {POLICY_SCHEMA_VERSION}）"
        )
    for key in ("policy_id", "version", "authorized_by"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PolicyError(f"{source}: 缺 {key}（授权人/版本身份）")

    created_at = _parse_dt(data.get("created_at", data.get("effective_from")), label="created_at")
    effective_from = _parse_dt(data.get("effective_from"), label="effective_from")
    effective_to = (
        _parse_dt(data["effective_to"], label="effective_to") if data.get("effective_to") else None
    )
    if effective_to is not None and _aware(effective_to) < _aware(effective_from):
        raise PolicyError(f"{source}: effective_to 早于 effective_from")

    ttl_hours = (
        _as_decimal(data["ttl_hours"], label="ttl_hours", minimum=Decimal("0.01"))
        if data.get("ttl_hours") is not None
        else None
    )

    t2 = data.get("t2") or {}
    if not isinstance(t2, Mapping):
        raise PolicyError(f"{source}: t2 必须是对象")

    max_single = _as_decimal(
        t2.get("max_single_record_impact", 0), label="t2.max_single_record_impact", minimum=Decimal("0")
    )
    max_batch = _as_decimal(
        t2.get("max_batch_impact", 0), label="t2.max_batch_impact", minimum=Decimal("0")
    )
    if max_batch < max_single:
        raise PolicyError(f"{source}: max_batch_impact 小于 max_single_record_impact")

    closed = _str_set(t2.get("closed_periods"), label="t2.closed_periods")
    for period in closed:
        if not _PERIOD_RE.match(period):
            raise PolicyError(f"{source}: closed_periods 含非 YYYYMM: {period!r}")

    auth = data.get("authorization") or {}
    if not isinstance(auth, Mapping):
        raise PolicyError(f"{source}: authorization 必须是对象")

    raw = json.loads(_canonical(dict(data)))
    return CorrectionPolicy(
        policy_id=data["policy_id"].strip(),
        version=str(data["version"]).strip(),
        authorized_by=data["authorized_by"].strip(),
        created_at=created_at,
        effective_from=effective_from,
        effective_to=effective_to,
        ttl_hours=ttl_hours,
        auto_apply_t1=bool(data.get("auto_apply_t1", True)),
        t2_enabled=bool(t2.get("enabled", False)),
        t2_categories=_str_set(t2.get("allowed_categories"), label="t2.allowed_categories"),
        t2_platforms=_str_set(t2.get("allowed_platforms"), label="t2.allowed_platforms"),
        t2_fields=_str_set(t2.get("allowed_fields"), label="t2.allowed_fields"),
        closed_periods=closed,
        max_single_impact=max_single,
        max_batch_impact=max_batch,
        raw=raw,
        hash=digest(raw),
        t2_require_fx=bool(t2.get("require_fx", False)),
        t2_require_receipt=bool(t2.get("require_receipt", False)) or bool(auth.get("require_receipt", False)),
        authorization_roles=_str_set(auth.get("allowed_roles"), label="authorization.allowed_roles"),
    )


def load_policy(path: Path) -> CorrectionPolicy:
    """从 **git 外** JSON 文件加载政策；文件缺失/非 JSON/结构非法都 FAIL。"""
    p = Path(path)
    if not p.is_file():
        raise PolicyError(f"政策文件不存在: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PolicyError(f"政策文件不是合法 JSON: {p}: {e}") from None
    return parse_policy(data, source=str(p))


def policy_errors(policy: CorrectionPolicy | None, *, now: datetime | None = None) -> list[str]:
    """政策可用性问题：缺政策 / 未生效 / 已过期 / TTL 超时 / 阈值非法。空=可用。"""
    if policy is None:
        return ["未加载修正政策（任何语义修正都不得写入）"]
    ts = _now(now)
    problems: list[str] = []
    if ts < _aware(policy.effective_from):
        problems.append(
            f"政策 {policy.policy_id}@{policy.version} 尚未生效（effective_from={policy.effective_from.isoformat()}）"
        )
    if policy.effective_to is not None and ts > _aware(policy.effective_to):
        problems.append(
            f"政策 {policy.policy_id}@{policy.version} 已过期（effective_to={policy.effective_to.isoformat()}）"
        )
    if policy.ttl_hours is not None and ts > _aware(policy.created_at) + _hours(policy.ttl_hours):
        problems.append(
            f"政策 {policy.policy_id}@{policy.version} 超过 TTL {_dec_str(policy.ttl_hours)}h"
        )
    if policy.max_single_impact <= 0 and policy.t2_enabled:
        problems.append(f"政策 {policy.policy_id}@{policy.version}: T2 已启用但单条影响上限为 0")
    return problems


def _hours(value: Decimal) -> timedelta:
    return timedelta(seconds=float(value * Decimal(3600)))


# ------------------------------------------------------------------ FX / 人民币预算


class BudgetError(PolicyError):
    """人民币影响预算无法成立（缺 FX / 币种未确认 / 文本修正无受影响金额）。"""


def normalize_currency(value) -> str:
    """币种代码归一：与汇率表同口径（去零宽/NFKC/纯 ASCII 大写）。"""
    if value is None:
        return ""
    try:
        from exchange_rate import normalize_currency_label
    except Exception:  # pragma: no cover - 汇率模块不可用时退化为轻量归一
        import unicodedata

        return unicodedata.normalize("NFKC", str(value)).strip().upper()
    return normalize_currency_label(value)


@dataclass(frozen=True)
class FxTable:
    """**已确认目标月** 汇率表：``rates`` 是 1 单位原币 = 多少 CNY。"""

    month: str
    rates: Mapping[str, Decimal]
    source: str = ""
    source_hash: str = ""

    def rate(self, currency: str) -> Decimal | None:
        return self.rates.get(normalize_currency(currency))


def fx_table_from_mapping(
    data: Mapping[str, Any],
    *,
    month: str,
    source: str = "<memory>",
    source_hash: str = "",
) -> FxTable:
    """从 ``{currency: rate}`` 或 ``{"rates": {...}}`` 构造；非法/非正数直接报错。"""
    raw = data.get("rates") if isinstance(data, Mapping) and "rates" in data else data
    if not isinstance(raw, Mapping) or not raw:
        raise BudgetError(f"{source}: 汇率必须是 非空 {{币种: 汇率}}")
    rates: dict[str, Decimal] = {}
    for cur, value in raw.items():
        code = normalize_currency(cur)
        if not code:
            raise BudgetError(f"{source}: 空币种键")
        rate = _as_decimal(value, label=f"{source}.{code}", minimum=Decimal("0"))
        if rate <= 0:
            raise BudgetError(f"{source}: {code} 汇率必须 > 0，收到 {value!r}")
        if code in rates and rates[code] != rate:
            raise BudgetError(f"{source}: {code} 出现多个不同汇率")
        rates[code] = rate
    if not _PERIOD_RE.match(str(month)):
        raise BudgetError(f"{source}: FX 月份必须是 YYYYMM，收到 {month!r}")
    return FxTable(month=str(month), rates=rates, source=source, source_hash=source_hash)


def load_fx_table(path: Path, *, month: str | None = None) -> FxTable:
    """从 **git 外** JSON / CSV 加载已确认汇率；文件缺失/结构非法一律 ``BudgetError``。"""
    p = Path(path)
    if not p.is_file():
        raise BudgetError(f"汇率文件不存在: {p}")
    blob = p.read_bytes()
    digest_ = hashlib.sha256(blob).hexdigest()
    text = blob.decode("utf-8-sig")
    if p.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise BudgetError(f"汇率文件不是合法 JSON: {p}: {e}") from None
        if not isinstance(data, Mapping):
            raise BudgetError(f"{p}: 汇率 JSON 顶层必须是对象")
        file_month = str(data.get("month") or month or "").strip()
        if not file_month:
            raise BudgetError(f"{p}: 缺 month（已确认目标月）")
        if month and str(data.get("month") or month) != str(month):
            raise BudgetError(f"{p}: 汇率月份 {data.get('month')} != 目标月 {month}")
        return fx_table_from_mapping(
            data,
            month=file_month,
            source=str(p),
            source_hash=digest_,
        )
    # CSV：currency,rate[,month]
    import csv
    import io

    reader = csv.DictReader(io.StringIO(text))
    fields = {str(f or "").strip().lower() for f in (reader.fieldnames or [])}
    if not {"currency", "rate"} <= fields:
        raise BudgetError(f"{p}: CSV 需要 currency,rate 列，现有 {reader.fieldnames!r}")
    raw: dict[str, str] = {}
    file_month = str(month or "")
    for row in reader:
        cur = str(row.get("currency") or "").strip()
        if not cur:
            continue
        row_month = str(row.get("month") or "").strip()
        if row_month:
            if file_month and row_month != file_month:
                raise BudgetError(f"{p}: 行月份 {row_month} != 目标月 {file_month}")
            file_month = row_month
        raw[cur] = str(row.get("rate") or "").strip()
    if not file_month:
        raise BudgetError(f"{p}: 缺 month（CSV 需 month 列或显式 --month）")
    return fx_table_from_mapping(raw, month=file_month, source=str(p), source_hash=digest_)


def fx_digest(fx: FxTable | None) -> str | None:
    """汇率表依赖 hash（月 + 汇率 + 原文 hash）；无表返回 None。"""
    if fx is None:
        return None
    return digest(
        {
            "month": fx.month,
            "rates": {k: _dec_str(v) for k, v in sorted(fx.rates.items())},
            "source_hash": fx.source_hash,
        }
    )


# 文本列（改这些列不直接产生金额差，但会改变钱归谁/归哪期）。
TEXT_COLUMN_HINTS = ("账户", "账号", "平台", "币种", "日期", "归属", "人员")


def is_text_column(col) -> bool:
    return any(h in str(col) for h in TEXT_COLUMN_HINTS)


def amount_basis(field_changes: Mapping[str, Any]) -> Decimal:
    """受影响金额规模：字段里可解析的金额差绝对值之和（文本列贡献 0）。"""
    total = Decimal("0")
    for col, change in field_changes.items():
        if not isinstance(change, (list, tuple)) or len(change) != 2:
            continue
        before, after = change
        try:
            total += abs(Decimal(str(after)) - Decimal(str(before)))
        except (InvalidOperation, ValueError):
            continue
    return total


@dataclass(frozen=True)
class ImpactBudget:
    """一条修正的人民币影响。``basis``：amount_delta（金额差）/ affected_amount（文本修正）。"""

    currency: str
    impact_original: Decimal
    impact_cny: Decimal
    basis: str
    fx_rate: Decimal | None = None
    fx_month: str | None = None


def resolve_impact_budget(
    proposal: "CorrectionProposal",
    *,
    fx: FxTable | None,
    month: str = "",
    require_fx: bool = False,
) -> ImpactBudget:
    """把一条 proposal 的影响换算成 CNY；不能成立时抛 ``BudgetError``（写入口=0）。

    - ``require_fx`` 或给了 ``fx`` 时：必须声明币种、汇率表月份必须是目标月、币种必须有汇率。
    - 纯文本修正（账号/日期/币种）：影响 = ``affected_amount``（受影响金额规模），
      不能是 0；没有该字段直接拒绝，不允许静默按 0 通过。
    - 未启用 FX 的模式（历史兼容）：直接用原币 ``impact``，文本修正按声明值或 0。
    """
    delta = amount_basis(proposal.field_changes)
    text_only = delta == 0
    currency = normalize_currency(proposal.currency or proposal.evidence.get("currency") or "")
    if fx is None and not require_fx:
        impact = proposal.impact
        if text_only:
            impact = proposal.affected_amount or impact
        return ImpactBudget(
            currency=currency,
            impact_original=impact,
            impact_cny=impact,
            basis="affected_amount" if text_only else "amount_delta",
        )

    if fx is None:
        raise BudgetError("缺已确认目标月 FX 表（禁止用原币/0 代替人民币预算）")
    target_month = str(month or fx.month)
    if str(fx.month) != target_month:
        raise BudgetError(f"FX 月份 {fx.month} 与目标月 {target_month} 不符")
    if not currency:
        raise BudgetError("proposal 未声明币种（币种未确认不能算人民币影响）")
    rate = fx.rate(currency)
    if rate is None:
        raise BudgetError(f"币种 {currency} 在 {fx.month} 汇率表中缺失")
    if text_only:
        basis_amount = proposal.affected_amount
        if basis_amount is None or basis_amount <= 0:
            raise BudgetError(
                "纯文本修正（账号/日期/币种）缺受影响金额规模 affected_amount，"
                "不能按影响 0 通过"
            )
        return ImpactBudget(
            currency=currency,
            impact_original=basis_amount,
            impact_cny=(basis_amount * rate).quantize(Decimal("0.01")),
            basis="affected_amount",
            fx_rate=rate,
            fx_month=str(fx.month),
        )
    return ImpactBudget(
        currency=currency,
        impact_original=delta,
        impact_cny=(delta * rate).quantize(Decimal("0.01")),
        basis="amount_delta",
        fx_rate=rate,
        fx_month=str(fx.month),
    )


# ------------------------------------------------------------------ Proposal


@dataclass(frozen=True)
class CorrectionProposal:
    """一条待发布修正的不可变凭据；``hash`` 由 ``proposal_hash`` 计算。"""

    correction_id: str
    period: str
    platform: str
    kind: str
    tier: str
    row_key: Mapping[str, str]
    field_changes: Mapping[str, tuple]
    evidence: Mapping[str, Any]
    evidence_hash: str
    impact: Decimal
    account_after: str | None = None
    source_hash: str | None = None
    confirmed_by: str | None = None
    approved_at: datetime | None = None
    status: str = ""
    currency: str | None = None
    affected_amount: Decimal | None = None
    authorization: Mapping[str, Any] | None = None

    @property
    def human_approved(self) -> bool:
        return bool(self.confirmed_by) and str(self.status).strip().lower() == "approved"

    @property
    def hash(self) -> str:
        return proposal_hash(self)


def _tier_for(kind: str) -> str:
    """未知/未声明类别 = ``UNKNOWN``：不能自动授权，只能走人工精确批准。"""
    return KIND_TIERS.get(str(kind or "").strip().lower(), TIER_UNKNOWN)


def _evidence_digest(evidence: Mapping[str, Any]) -> str:
    explicit = str(evidence.get("evidence_hash") or "").strip().lower()
    if explicit:
        if not (_MD5_RE.match(explicit) or _SHA256_RE.match(explicit)):
            raise PolicyError(f"evidence.evidence_hash 不是 md5/sha256: {explicit!r}")
        return explicit
    md5 = str(evidence.get("attachment_md5") or "").strip().lower()
    return md5 if _MD5_RE.match(md5) else ""


def _computed_impact(field_changes: Mapping[str, Any]) -> Decimal:
    total = Decimal("0")
    for change in field_changes.values():
        if not isinstance(change, (list, tuple)) or len(change) != 2:
            continue
        before, after = change
        try:
            total += abs(Decimal(str(after)) - Decimal(str(before)))
        except (InvalidOperation, ValueError):
            continue  # 文本列（账号/币种/日期）不计金额影响
    return total


def build_proposal(item: Mapping[str, Any], *, period: str | None = None) -> CorrectionProposal:
    """从凭据 JSON 的单个 ``corrections[]`` 元素构造 proposal。

    只做结构提取，不判断政策；字段缺失由 ``evaluate_proposal`` 与 remediation 校验负责。
    """
    cid = str(item.get("correction_id") or "").strip()
    scope = item.get("scope") or {}
    item_period = str(scope.get("period") or period or "").strip()
    kind = str(item.get("kind") or "").strip().lower()
    evidence = item.get("evidence") or {}
    if not isinstance(evidence, Mapping):
        raise PolicyError(f"{cid}: evidence 必须是对象")
    field_changes = item.get("field_changes") or {}
    if not isinstance(field_changes, Mapping):
        raise PolicyError(f"{cid}: field_changes 必须是对象")
    row_key = item.get("source_row_key") or {}
    if not isinstance(row_key, Mapping):
        raise PolicyError(f"{cid}: source_row_key 必须是对象")
    impact = (
        _as_decimal(item["impact"], label=f"{cid}.impact", minimum=Decimal("0"))
        if item.get("impact") is not None
        else _computed_impact(field_changes)
    )
    approved_at = (
        _parse_dt(item["approved_at"], label=f"{cid}.approved_at") if item.get("approved_at") else None
    )
    affected_raw = item.get("affected_amount")
    if affected_raw is None:
        affected_raw = evidence.get("affected_amount")
    affected_amount = (
        _as_decimal(affected_raw, label=f"{cid}.affected_amount", minimum=Decimal("0"))
        if affected_raw is not None
        else None
    )
    authorization = item.get("authorization")
    if authorization is not None and not isinstance(authorization, Mapping):
        raise PolicyError(f"{cid}: authorization 必须是对象")
    return CorrectionProposal(
        correction_id=cid,
        period=item_period,
        platform=str(item.get("platform") or scope.get("platform") or "").strip(),
        kind=kind,
        tier=_tier_for(kind),
        row_key={str(k): str(v) for k, v in row_key.items()},
        field_changes=dict(field_changes),
        evidence=dict(evidence),
        evidence_hash=_evidence_digest(evidence),
        impact=impact,
        account_after=(str(item["account_after"]).strip() if item.get("account_after") else None),
        source_hash=(str(item["source_hash"]).strip() if item.get("source_hash") else None),
        confirmed_by=(str(item["confirmed_by"]).strip() if item.get("confirmed_by") else None),
        approved_at=approved_at,
        status=str(item.get("status") or "").strip().lower(),
        currency=(
            normalize_currency(item.get("currency") or scope.get("currency") or evidence.get("currency"))
            or None
        ),
        affected_amount=affected_amount,
        authorization=dict(authorization) if authorization is not None else None,
    )


def build_proposals(corrections: Mapping[str, Any], *, period: str) -> list[CorrectionProposal]:
    items = corrections.get("corrections") if isinstance(corrections, Mapping) else None
    if not isinstance(items, list):
        return []
    out: list[CorrectionProposal] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        scope = item.get("scope") or {}
        if str(scope.get("period") or "") != str(period):
            continue
        out.append(build_proposal(item, period=str(period)))
    return out


def _proposal_payload(p: CorrectionProposal) -> dict:
    return {
        "correction_id": p.correction_id,
        "period": p.period,
        "platform": p.platform,
        "kind": p.kind,
        "tier": p.tier,
        "row_key": dict(sorted(p.row_key.items())),
        "field_changes": {
            str(col): [str(change[0]), str(change[1])]
            for col, change in sorted(p.field_changes.items())
            if isinstance(change, (list, tuple)) and len(change) == 2
        },
        "evidence_hash": p.evidence_hash,
        "settlement_id": str(p.evidence.get("settlement_id") or ""),
        "group_id": str(p.evidence.get("group_id") or ""),
        "account_after": p.account_after or "",
        "impact": _dec_str(p.impact),
        "source_hash": p.source_hash or "",
        # R1：币种与受影响金额规模属于修正内容，改了就应使旧授权失效。
        "currency": p.currency or "",
        "affected_amount": _dec_str(p.affected_amount) if p.affected_amount is not None else "",
    }


def proposal_hash(p: CorrectionProposal) -> str:
    return digest(_proposal_payload(p))


def proposal_batch_hash(proposals: Iterable[CorrectionProposal]) -> str:
    parts = sorted(f"{p.correction_id}:{proposal_hash(p)}" for p in proposals)
    return digest(parts)


def evidence_complete(proposal: CorrectionProposal, *, automatic: bool = True) -> list[str]:
    """证据要求：按等级分别校验，返回缺失项（空=齐）。

    ``automatic=True`` 用于自动发布——除附件/结算身份外还要求 ``identity_unique``；
    人工精确批准（``automatic=False``）时由签字人确认身份，不再要求机器声明唯一。
    """
    ev = proposal.evidence
    problems: list[str] = []
    if not proposal.evidence_hash:
        problems.append("缺证据 hash（evidence_hash / attachment_md5）")
    if proposal.tier == TIER_T1:
        if not str(ev.get("rule") or "").strip():
            problems.append("T1 缺归一规则 rule")
        return problems
    if not str(ev.get("attachment") or "").strip():
        problems.append("缺附件文件名")
    if not _MD5_RE.match(str(ev.get("attachment_md5") or "").strip().lower()):
        problems.append("缺附件 md5")
    if not (str(ev.get("settlement_id") or "").strip() or str(ev.get("group_id") or "").strip()):
        problems.append("缺结算身份（settlement_id / group_id）")
    if automatic and ev.get("identity_unique") is not True:
        problems.append("证据未声明身份唯一（identity_unique）")
    return problems


# ------------------------------------------------------------------ 授权


@dataclass(frozen=True)
class AuthorizationResult:
    correction_id: str
    tier: str
    status: str
    proposal_hash: str
    evidence_hash: str
    impact: Decimal
    period: str = ""
    policy_id: str | None = None
    policy_version: str | None = None
    policy_hash: str | None = None
    approver: str | None = None
    evaluated_at: datetime | None = None
    reasons: tuple[str, ...] = ()
    # R1：人民币影响与计价依据（无 FX 时为原币口径，basis 标 legacy）。
    impact_cny: Decimal = Decimal("0")
    currency: str = ""
    budget_basis: str = "legacy"
    fx_month: str | None = None

    @property
    def publishable(self) -> bool:
        return self.status in _PUBLISHABLE_STATUSES


@dataclass(frozen=True)
class BatchAuthorization:
    results: tuple[AuthorizationResult, ...]
    batch_proposal_hash: str
    policy_id: str | None
    policy_version: str | None
    policy_hash: str | None
    batch_impact: Decimal
    errors: tuple[str, ...] = ()
    prior_impact: Decimal = Decimal("0")
    cumulative_impact: Decimal = Decimal("0")
    period: str = ""

    def by_id(self) -> dict[str, AuthorizationResult]:
        return {r.correction_id: r for r in self.results}

    @property
    def publishable(self) -> bool:
        return not self.errors and all(r.publishable for r in self.results)


def authorization_receipt_problems(
    proposal: CorrectionProposal,
    policy: CorrectionPolicy | None,
    *,
    now: datetime | None = None,
) -> list[str]:
    """R2：人工批准的授权凭据校验（proposal hash / 依据 / 角色 / 时间 / scope）。

    单个 ``confirmed_by`` 字符串不算授权；正式发布要求 ``authorization`` 对象绑定
    当前 proposal hash 与 scope，防止「伪 confirmed_by」和「换证据复用旧批准」。
    """
    receipt = proposal.authorization
    if not isinstance(receipt, Mapping) or not receipt:
        return ["approved 缺授权凭据 authorization（须绑定 proposal hash/依据/角色/时间/scope）"]
    problems: list[str] = []
    recorded_hash = str(receipt.get("proposal_hash") or "").strip().lower()
    if not recorded_hash:
        problems.append("授权凭据缺 proposal_hash")
    elif recorded_hash != proposal_hash(proposal):
        problems.append(
            f"授权凭据绑定的是别的 proposal（{recorded_hash[:12]}… != "
            f"{proposal_hash(proposal)[:12]}…），换证据后旧批准失效"
        )
    for key in ("authority_ref", "role", "decided_at"):
        if not str(receipt.get(key) or "").strip():
            problems.append(f"授权凭据缺 {key}")
    scope = receipt.get("scope")
    if not isinstance(scope, Mapping) or not scope:
        problems.append("授权凭据缺 scope")
    else:
        if str(scope.get("period") or "") != str(proposal.period):
            problems.append(
                f"授权 scope.period={scope.get('period')!r} 与 proposal 期间 {proposal.period!r} 不符"
            )
        scope_platform = str(scope.get("platform") or "").strip()
        if scope_platform and scope_platform != proposal.platform:
            problems.append(f"授权 scope.platform={scope_platform} 未覆盖 {proposal.platform}")
        ids = scope.get("correction_ids")
        if ids is not None:
            if not isinstance(ids, (list, tuple)) or proposal.correction_id not in ids:
                problems.append(f"授权 scope 未覆盖 correction_id {proposal.correction_id}")
    decided_by = str(receipt.get("decided_by") or "").strip()
    if decided_by and proposal.confirmed_by and decided_by != proposal.confirmed_by:
        problems.append(
            f"confirmed_by={proposal.confirmed_by!r} 与授权凭据 decided_by={decided_by!r} 不一致"
        )
    role = str(receipt.get("role") or "").strip()
    if policy is not None and policy.authorization_roles and role not in policy.authorization_roles:
        problems.append(f"角色 {role!r} 不在政策允许的授权角色 {sorted(policy.authorization_roles)}")
    decided_raw = receipt.get("decided_at")
    if decided_raw:
        try:
            decided_at = _parse_dt(decided_raw, label="authorization.decided_at")
        except PolicyError as e:
            problems.append(str(e))
        else:
            ts = _now(now)
            if _aware(decided_at) > ts:
                problems.append(f"授权时间 {decided_at.isoformat()} 晚于当前时间（未来批准）")
            if policy is not None:
                if _aware(decided_at) < _aware(policy.effective_from):
                    problems.append("授权时间早于政策生效期")
                if policy.effective_to is not None and _aware(decided_at) > _aware(policy.effective_to):
                    problems.append("授权时间晚于政策有效期")
    return problems


def _result(
    proposal: CorrectionProposal,
    status: str,
    *,
    policy: CorrectionPolicy | None,
    now: datetime,
    reasons: Sequence[str] = (),
    approver: str | None = None,
    budget: ImpactBudget | None = None,
) -> AuthorizationResult:
    return AuthorizationResult(
        correction_id=proposal.correction_id,
        tier=proposal.tier,
        status=status,
        proposal_hash=proposal_hash(proposal),
        evidence_hash=proposal.evidence_hash,
        impact=proposal.impact,
        period=proposal.period,
        policy_id=policy.policy_id if policy else None,
        policy_version=policy.version if policy else None,
        policy_hash=policy.hash if policy else None,
        approver=approver,
        evaluated_at=now,
        reasons=tuple(reasons),
        impact_cny=budget.impact_cny if budget else proposal.impact,
        currency=budget.currency if budget else "",
        budget_basis=budget.basis if budget else "legacy",
        fx_month=budget.fx_month if budget else None,
    )


def evaluate_proposal(
    proposal: CorrectionProposal,
    policy: CorrectionPolicy | None,
    *,
    now: datetime | None = None,
    fx: FxTable | None = None,
    require_fx: bool = False,
    month: str = "",
    require_receipt: bool = False,
    expected_period: str = "",
) -> AuthorizationResult:
    """按等级判定一条修正能否自动/人工批准；不能发布的一律 ``preview``/``blocked``。

    检查顺序（硬身份/有效期/期间**先于**任何批准捷径）：

    1. 政策有效性（缺/未生效/过期/TTL）；
    2. 期间（``expected_period``）与 proposal 期间一致；
    3. T3/T4 —— 签字也不能绕过；
    4. 证据完整性；
    5. 授权凭据（``require_receipt``/政策要求时）；
    6. T1 自动 / T2 窄通道（人民币预算）。
    """
    ts = _now(now)
    errors = policy_errors(policy, now=ts)
    if errors:
        return _result(proposal, STATUS_BLOCKED, policy=policy, now=ts, reasons=errors)

    if expected_period and str(proposal.period) != str(expected_period):
        return _result(
            proposal,
            STATUS_BLOCKED,
            policy=policy,
            now=ts,
            reasons=(f"proposal 期间 {proposal.period!r} 与目标期 {expected_period!r} 不符",),
        )

    if proposal.tier in (TIER_T3, TIER_T4):
        # 缺件待核 / 主数据缺失：签字也不能替代必需字段与唯一性，先修来源。
        return _result(
            proposal,
            STATUS_BLOCKED,
            policy=policy,
            now=ts,
            reasons=(
                f"{proposal.tier} 类别 {proposal.kind or '<未声明>'} 必须先修来源/主数据，"
                "人工签字不能绕过",
            ),
        )

    try:
        budget = resolve_impact_budget(
            proposal,
            fx=fx,
            month=month or proposal.period,
            require_fx=require_fx or bool(policy and policy.t2_require_fx),
        )
    except BudgetError as e:
        return _result(proposal, STATUS_BLOCKED, policy=policy, now=ts, reasons=(str(e),))

    evidence_problems = evidence_complete(proposal)
    needs_receipt = require_receipt or bool(policy and policy.t2_require_receipt)
    if proposal.human_approved:
        problems = evidence_complete(proposal, automatic=False)
        if needs_receipt:
            problems = problems + authorization_receipt_problems(proposal, policy, now=ts)
        if problems:
            return _result(
                proposal, STATUS_BLOCKED, policy=policy, now=ts, reasons=problems, budget=budget
            )
        return _result(
            proposal,
            STATUS_APPROVED,
            policy=policy,
            now=ts,
            approver=proposal.confirmed_by,
            budget=budget,
        )
    if proposal.status == STATUS_APPROVED and not proposal.confirmed_by:
        # 声称 approved 但没署名：不能悄悄降级成自动。
        return _result(
            proposal,
            STATUS_BLOCKED,
            policy=policy,
            now=ts,
            reasons=("status=approved 但缺 confirmed_by（无效批准）",),
            budget=budget,
        )
    if proposal.confirmed_by and proposal.status != STATUS_APPROVED:
        # preview/draft 里塞一个 confirmed_by 不能当批准用。
        return _result(
            proposal,
            STATUS_BLOCKED,
            policy=policy,
            now=ts,
            reasons=(f"status={proposal.status or '<空>'} 带有 confirmed_by，不能当 approved 使用",),
            budget=budget,
        )

    if proposal.tier == TIER_T1:
        if not policy.auto_apply_t1:
            return _result(
                proposal,
                STATUS_PREVIEW,
                policy=policy,
                now=ts,
                reasons=("政策关闭了 T1 自动",),
                budget=budget,
            )
        if evidence_problems:
            return _result(
                proposal, STATUS_BLOCKED, policy=policy, now=ts, reasons=evidence_problems, budget=budget
            )
        return _result(proposal, STATUS_AUTO_ALLOWED, policy=policy, now=ts, budget=budget)

    # T2
    reasons: list[str] = []
    if not policy.t2_enabled:
        reasons.append("政策未启用 T2 窄通道")
    if proposal.kind not in policy.t2_categories:
        reasons.append(f"类别 {proposal.kind or '<未声明>'} 不在政策允许范围")
    if not proposal.platform:
        reasons.append("proposal 未声明平台")
    elif not policy.allows_platform(proposal.platform):
        reasons.append(f"平台 {proposal.platform} 不在政策允许范围")
    fields = set(proposal.field_changes)
    if not policy.t2_fields:
        reasons.append("政策未声明允许字段")
    elif not fields <= policy.t2_fields:
        reasons.append(f"字段越界: {sorted(fields - policy.t2_fields)}")
    if proposal.period in policy.closed_periods:
        reasons.append(f"期间 {proposal.period} 已关账，只能人工重述批次")
    reasons.extend(evidence_problems)
    if budget.impact_cny > policy.max_single_impact:
        reasons.append(
            f"单条影响 {_dec_str(budget.impact_cny)} CNY 超过上限 "
            f"{_dec_str(policy.max_single_impact)}"
        )
    if reasons:
        return _result(proposal, STATUS_PREVIEW, policy=policy, now=ts, reasons=reasons, budget=budget)
    return _result(proposal, STATUS_AUTO_ALLOWED, policy=policy, now=ts, budget=budget)


def cumulative_prior_impact(
    prior_runs: Sequence[Mapping[str, Any]],
    *,
    period: str,
    source_hash: str | None = None,
) -> Decimal:
    """同一期间 + 同源版本的历史已应用影响（绝对值累加，正负不抵消）。

    ``prior_runs`` 是历史发布 manifest。缺 ``source_hash`` 的旧 manifest 按**同期间**
    纳入（fail-closed：宁可多算，不能靠拆 run 绕过批次上限）。
    """
    total = Decimal("0")
    for run in prior_runs or ():
        if not isinstance(run, Mapping):
            continue
        if str(run.get("period") or "") != str(period):
            continue
        run_source = run.get("source_hash") or run.get("input_md5")
        if source_hash and run_source and str(run_source) != str(source_hash):
            continue
        for item in run.get("corrections") or ():
            if not isinstance(item, Mapping):
                continue
            raw = item.get("impact_cny")
            if raw in (None, ""):
                raw = item.get("impact")
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                continue
            if value.is_finite():
                total += abs(value)
    return total


def evaluate_batch(
    proposals: Sequence[CorrectionProposal],
    policy: CorrectionPolicy | None,
    *,
    now: datetime | None = None,
    fx: FxTable | None = None,
    require_fx: bool = False,
    month: str = "",
    require_receipt: bool = False,
    expected_period: str = "",
    prior_runs: Sequence[Mapping[str, Any]] = (),
    source_hash: str | None = None,
) -> BatchAuthorization:
    """批量判定 + 批次影响上限（不能靠拆多笔/拆多 run 绕过）。

    批次人民币影响 = 本批每条 ``abs(impact_cny)`` 之和 + 同期间/同源版本的历史累计。
    每条取绝对值：正负修正**不相互抵消**（调增 500 + 调减 500 仍算 1000）。
    """
    ts = _now(now)
    errors = tuple(policy_errors(policy, now=ts))
    results = [
        evaluate_proposal(
            p,
            policy,
            now=ts,
            fx=fx,
            require_fx=require_fx,
            month=month,
            require_receipt=require_receipt,
            expected_period=expected_period,
        )
        for p in proposals
    ]
    batch_period = str(expected_period or (proposals[0].period if proposals else ""))
    prior_impact = cumulative_prior_impact(
        prior_runs, period=batch_period, source_hash=source_hash
    )
    batch_impact = sum(
        (abs(r.impact_cny) for r in results if r.status == STATUS_AUTO_ALLOWED), Decimal("0")
    )
    cumulative = batch_impact + prior_impact
    if policy is not None and not errors and cumulative > policy.max_batch_impact:
        downgraded: list[AuthorizationResult] = []
        for r in results:
            if r.status == STATUS_AUTO_ALLOWED and r.tier == TIER_T2:
                downgraded.append(
                    AuthorizationResult(
                        **{
                            **r.__dict__,
                            "status": STATUS_PREVIEW,
                            "reasons": r.reasons
                            + (
                                f"批次影响 {_dec_str(cumulative)} CNY（本批 {_dec_str(batch_impact)}"
                                f" + 同期间/同源历史 {_dec_str(prior_impact)}）超过上限 "
                                f"{_dec_str(policy.max_batch_impact)}",
                            ),
                        }
                    )
                )
            else:
                downgraded.append(r)
        results = downgraded
    return BatchAuthorization(
        results=tuple(results),
        batch_proposal_hash=proposal_batch_hash(proposals),
        policy_id=policy.policy_id if policy else None,
        policy_version=policy.version if policy else None,
        policy_hash=policy.hash if policy else None,
        batch_impact=batch_impact,
        errors=errors,
        prior_impact=prior_impact,
        cumulative_impact=cumulative,
        period=batch_period,
    )


# ------------------------------------------------------------------ 写前门禁


def write_gate_errors(
    *,
    period: str,
    policy: CorrectionPolicy | None,
    proposals: Sequence[CorrectionProposal] = (),
    results: Sequence[AuthorizationResult] | None = None,
    now: datetime | None = None,
    fx: FxTable | None = None,
    require_fx: bool = False,
    require_receipt: bool = False,
    require_proposals: bool = False,
    input_md5: str | None = None,
    approved_input_md5: str | None = None,
    prior_runs: Sequence[Mapping[str, Any]] = (),
    source_hash: str | None = None,
) -> list[str]:
    """写前硬门禁：未授权 T2 / 政策过期 / proposal/policy hash 变化 → 返回问题清单。

    ``proposals`` 是本次**打算写入**的修正；若为空则无修正可写，直接通过。
    ``results`` 可传入已存的授权凭据（用于校验 hash 未变）；不传则按当前政策现场判定。

    加固参数（正式发布入口一律传 True）：

    - ``require_proposals``：正式发布必须声明本批修正；空 proposal 但声称有批准源 → 拒绝。
    - ``require_fx`` / ``fx``：人民币预算必须有已确认目标月汇率（缺 → writer=0）。
    - ``require_receipt``：``approved`` 必须有绑定 proposal hash 的授权凭据。
    - ``input_md5`` + ``approved_input_md5``：输入与批准源不符 → 拒绝（空 proposal 也不能过）。
    - ``prior_runs`` + ``source_hash``：同一期间/同源版本的历史影响计入批次上限，防拆 run。

    已存 ``results`` 一律用**当前**政策重新判定（R4）：旧 ``auto_allowed`` 遇到
    T2 关闭/政策改版/汇率变化必须失效，不能只信旧 result.status。
    """
    proposals = list(proposals or [])
    # 批准源核对与 proposal 是否为空无关：输入变了，旧批准（哪怕声称「本批没修正」）失效。
    if approved_input_md5 and input_md5 and str(approved_input_md5) != str(input_md5):
        return [
            "AUTHORIZATION: 输入与批准源不符"
            f"（{str(input_md5)[:12]}… != {str(approved_input_md5)[:12]}…）；"
            "不能拿「没有 proposal」当正式输入未被修正的证明"
        ]
    if not proposals:
        if require_proposals:
            return [
                "AUTHORIZATION: 正式发布必须声明本批 corrections（空 proposal 不得写入）"
            ]
        return []

    errors = policy_errors(policy, now=now)
    if errors:
        return [f"POLICY: {e}" for e in errors]

    assert policy is not None  # policy_errors 已排除 None
    mismatched = sorted(
        {p.correction_id for p in proposals if str(p.period) != str(period)}
    )
    if mismatched:
        return [
            f"AUTHORIZATION: proposal 期间与门禁期间 {period!r} 不符: {mismatched}"
        ]

    fresh = evaluate_batch(
        proposals,
        policy,
        now=now,
        fx=fx,
        require_fx=require_fx,
        month=period,
        require_receipt=require_receipt,
        expected_period=period,
        prior_runs=prior_runs,
        source_hash=source_hash,
    )
    fresh_by_id = fresh.by_id()
    if results is None:
        results_by_id = dict(fresh_by_id)
    else:
        results_by_id: dict[str, AuthorizationResult] = {}
        for r in results:
            if r.correction_id in results_by_id:
                return [f"AUTHORIZATION: 授权凭据重复 correction_id {r.correction_id}"]
            results_by_id[r.correction_id] = r
        known = {p.correction_id for p in proposals}
        extra = sorted(set(results_by_id) - known)
        if extra:
            return [f"AUTHORIZATION: 授权凭据含未知 correction_id {extra}"]

    problems: list[str] = []
    for p in proposals:
        r = results_by_id.get(p.correction_id)
        if r is None:
            problems.append(f"{p.correction_id}: 缺授权结果（未授权修正）")
            continue
        current_hash = proposal_hash(p)
        if r.proposal_hash != current_hash:
            problems.append(
                f"{p.correction_id}: PROPOSAL-HASH 变化（凭据 {r.proposal_hash[:12]}… "
                f"!= 当前 {current_hash[:12]}…），旧授权失效"
            )
        if r.policy_hash != policy.hash:
            problems.append(
                f"{p.correction_id}: POLICY-HASH 变化（凭据 {str(r.policy_hash)[:12]}… "
                f"!= 当前 {policy.hash[:12]}…），旧 PASS 失效"
            )
        # R4：按当前政策/当前汇率重判；旧 PASS 与新判定不一致即失效。
        fresh_r = fresh_by_id.get(p.correction_id)
        if fresh_r is not None and fresh_r.status != r.status:
            problems.append(
                f"{p.correction_id}: 旧授权按当前政策重判为 {fresh_r.status}（原 {r.status}），"
                f"旧 PASS 失效: {'; '.join(fresh_r.reasons) or '—'}"
            )
        if r.status == STATUS_BLOCKED:
            problems.append(f"{p.correction_id}: {p.tier} 阻断: {'; '.join(r.reasons) or '未授权'}")
        elif r.status == STATUS_PREVIEW:
            problems.append(
                f"{p.correction_id}: {p.tier} 未获授权（preview 不得写入）: {'; '.join(r.reasons)}"
            )
        elif r.status not in _PUBLISHABLE_STATUSES:
            problems.append(f"{p.correction_id}: 未知授权状态 {r.status!r}")
        if r.status == STATUS_AUTO_ALLOWED and p.tier == TIER_T2:
            rechecked = fresh_by_id.get(p.correction_id)
            if rechecked is not None and rechecked.status != STATUS_AUTO_ALLOWED:
                problems.append(
                    f"{p.correction_id}: 旧 auto_allowed 结果在当前政策下不再成立"
                    f"（{rechecked.status}），拒绝写入"
                )
            if p.period in policy.closed_periods:
                problems.append(f"{p.correction_id}: 已关账期间 {p.period} 不得自动应用")
    return problems


# ------------------------------------------------------------------ 发布清单


def manifest_policy_fields(
    *,
    policy: CorrectionPolicy | None,
    proposals: Sequence[CorrectionProposal] = (),
    results: Sequence[AuthorizationResult] | None = None,
    now: datetime | None = None,
    fx: FxTable | None = None,
    batch: BatchAuthorization | None = None,
) -> dict:
    """manifest 需要的 policy/proposal/逐条 correction/证据/汇率/人民币影响。"""
    proposals = list(proposals or [])
    if not proposals:
        return {
            "policy_id": policy.policy_id if policy else None,
            "policy_version": policy.version if policy else None,
            "policy_hash": policy.hash if policy else None,
            "proposal_hash": None,
            "corrections": [],
            "fx_hash": fx_digest(fx),
            "fx_month": fx.month if fx else None,
            "batch_impact_cny": "0",
            "cumulative_impact_cny": (
                _dec_str(batch.cumulative_impact) if batch is not None else "0"
            ),
        }
    if results is None:
        results_by_id = (
            evaluate_batch(proposals, policy, now=now, fx=fx).by_id() if policy else {}
        )
    else:
        results_by_id = {r.correction_id: r for r in results}
    corrections = []
    for p in sorted(proposals, key=lambda x: x.correction_id):
        r = results_by_id.get(p.correction_id)
        corrections.append(
            {
                "correction_id": p.correction_id,
                "tier": p.tier,
                "status": r.status if r else STATUS_PREVIEW,
                "proposal_hash": proposal_hash(p),
                "evidence_hash": p.evidence_hash,
                "impact": _dec_str(p.impact),
                "impact_cny": _dec_str(r.impact_cny) if r else _dec_str(p.impact),
                "currency": (r.currency if r else p.currency) or "",
                "period": p.period,
            }
        )
    return {
        "policy_id": policy.policy_id if policy else None,
        "policy_version": policy.version if policy else None,
        "policy_hash": policy.hash if policy else None,
        "proposal_hash": proposal_batch_hash(proposals),
        "corrections": corrections,
        "fx_hash": fx_digest(fx),
        "fx_month": fx.month if fx else None,
        "batch_impact_cny": (
            _dec_str(batch.batch_impact)
            if batch is not None
            else _dec_str(sum((r.impact_cny for r in results_by_id.values()), Decimal("0")))
        ),
        "cumulative_impact_cny": (
            _dec_str(batch.cumulative_impact)
            if batch is not None
            else _dec_str(sum((abs(r.impact_cny) for r in results_by_id.values()), Decimal("0")))
        ),
    }


def stale_pass_problems(
    manifest: Mapping[str, Any] | None,
    *,
    input_md5: str | None,
    policy: CorrectionPolicy | None,
    proposals: Sequence[CorrectionProposal] = (),
    fx: FxTable | None = None,
    dependencies: Mapping[str, Any] | None = None,
    target_baseline_hash: str | None = None,
) -> list[str]:
    """旧 PASS 失效判定：输入 / 政策 / proposal / 汇率 / 依赖 / 目标基线任一变化即不可复用。

    ``dependencies`` 是当前批的依赖 hash（input/master/FX/FBA/例外/证据等），与 manifest
    里记录的 ``dependencies`` 逐键比较。``target_baseline_hash`` 是写前目标表基线——
    外部并发改动会让旧 PASS 失效。
    """
    if not manifest:
        return ["无历史发布 manifest（旧 PASS 不存在）"]
    problems: list[str] = []
    recorded_input = str(manifest.get("input_md5") or "").strip().lower()
    current_input = str(input_md5 or "").strip().lower()
    if not recorded_input:
        problems.append("manifest 未记录 input_md5（旧 PASS 不可核验）")
    elif current_input and recorded_input != current_input:
        problems.append(f"输入 hash 变化（{recorded_input[:12]}… != {current_input[:12]}…）")

    current_policy_hash = policy.hash if policy else None
    recorded_policy = manifest.get("policy_hash")
    if current_policy_hash:
        if not recorded_policy:
            problems.append("manifest 未记录 policy_hash（旧 PASS 不可复用）")
        elif recorded_policy != current_policy_hash:
            problems.append(
                f"政策 hash 变化（{str(recorded_policy)[:12]}… != {current_policy_hash[:12]}…）"
            )

    proposals = list(proposals or ())
    if proposals:
        current_proposal = proposal_batch_hash(proposals)
        recorded_proposal = manifest.get("proposal_hash")
        if not recorded_proposal:
            problems.append("manifest 未记录 proposal_hash（旧 PASS 不可复用）")
        elif recorded_proposal != current_proposal:
            problems.append(
                f"proposal hash 变化（{str(recorded_proposal)[:12]}… != {current_proposal[:12]}…）"
            )

    current_fx = fx_digest(fx)
    if current_fx is not None:
        recorded_fx = manifest.get("fx_hash")
        if not recorded_fx:
            problems.append("manifest 未记录 fx_hash（旧 PASS 不可核验汇率）")
        elif recorded_fx != current_fx:
            problems.append(
                f"汇率 hash 变化（{str(recorded_fx)[:12]}… != {current_fx[:12]}…）"
            )

    if dependencies:
        recorded_deps = manifest.get("dependencies")
        if not isinstance(recorded_deps, Mapping):
            problems.append("manifest 未记录 dependencies（旧 PASS 不可核验）")
        else:
            changed = sorted(
                key
                for key, value in dependencies.items()
                if str(recorded_deps.get(key) or "") != str(value or "")
            )
            if changed:
                problems.append(f"依赖 hash 变化: {changed}")

    if target_baseline_hash:
        recorded_baseline = manifest.get("target_baseline_hash")
        if not recorded_baseline:
            problems.append("manifest 未记录 target_baseline_hash（目标基线不可核验）")
        elif str(recorded_baseline) != str(target_baseline_hash):
            problems.append(
                f"目标表基线变化（{str(recorded_baseline)[:12]}… != "
                f"{str(target_baseline_hash)[:12]}…），目标已被外部改动"
            )
    return problems
