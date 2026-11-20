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

    def by_id(self) -> dict[str, AuthorizationResult]:
        return {r.correction_id: r for r in self.results}

    @property
    def publishable(self) -> bool:
        return not self.errors and all(r.publishable for r in self.results)


def _result(
    proposal: CorrectionProposal,
    status: str,
    *,
    policy: CorrectionPolicy | None,
    now: datetime,
    reasons: Sequence[str] = (),
    approver: str | None = None,
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
    )


def evaluate_proposal(
    proposal: CorrectionProposal,
    policy: CorrectionPolicy | None,
    *,
    now: datetime | None = None,
) -> AuthorizationResult:
    """按等级判定一条修正能否自动/人工批准；不能发布的一律 ``preview``/``blocked``。"""
    ts = _now(now)
    errors = policy_errors(policy, now=ts)
    if errors:
        return _result(proposal, STATUS_BLOCKED, policy=policy, now=ts, reasons=errors)

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

    evidence_problems = evidence_complete(proposal)
    if proposal.human_approved:
        problems = evidence_complete(proposal, automatic=False)
        if problems:
            return _result(
                proposal, STATUS_BLOCKED, policy=policy, now=ts, reasons=problems
            )
        return _result(
            proposal,
            STATUS_APPROVED,
            policy=policy,
            now=ts,
            approver=proposal.confirmed_by,
        )

    if proposal.tier == TIER_T1:
        if not policy.auto_apply_t1:
            return _result(
                proposal, STATUS_PREVIEW, policy=policy, now=ts, reasons=("政策关闭了 T1 自动",)
            )
        if evidence_problems:
            return _result(
                proposal, STATUS_BLOCKED, policy=policy, now=ts, reasons=evidence_problems
            )
        return _result(proposal, STATUS_AUTO_ALLOWED, policy=policy, now=ts)

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
    if proposal.impact > policy.max_single_impact:
        reasons.append(
            f"单条影响 {_dec_str(proposal.impact)} 超过上限 {_dec_str(policy.max_single_impact)}"
        )
    if reasons:
        return _result(proposal, STATUS_PREVIEW, policy=policy, now=ts, reasons=reasons)
    return _result(proposal, STATUS_AUTO_ALLOWED, policy=policy, now=ts)


def evaluate_batch(
    proposals: Sequence[CorrectionProposal],
    policy: CorrectionPolicy | None,
    *,
    now: datetime | None = None,
) -> BatchAuthorization:
    """批量判定 + 批次影响上限（不能靠拆多笔绕过）。"""
    ts = _now(now)
    errors = tuple(policy_errors(policy, now=ts))
    results = [evaluate_proposal(p, policy, now=ts) for p in proposals]
    batch_impact = sum(
        (r.impact for r in results if r.status == STATUS_AUTO_ALLOWED), Decimal("0")
    )
    if policy is not None and not errors and batch_impact > policy.max_batch_impact:
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
                                f"批次影响 {_dec_str(batch_impact)} 超过上限 "
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
    )


# ------------------------------------------------------------------ 写前门禁


def write_gate_errors(
    *,
    period: str,
    policy: CorrectionPolicy | None,
    proposals: Sequence[CorrectionProposal] = (),
    results: Sequence[AuthorizationResult] | None = None,
    now: datetime | None = None,
) -> list[str]:
    """写前硬门禁：未授权 T2 / 政策过期 / proposal/policy hash 变化 → 返回问题清单。

    ``proposals`` 是本次**打算写入**的修正；若为空则无修正可写，直接通过。
    ``results`` 可传入已存的授权凭据（用于校验 hash 未变）；不传则按当前政策现场判定。
    """
    proposals = list(proposals or [])
    if not proposals:
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
    if results is None:
        results_by_id = evaluate_batch(proposals, policy, now=now).by_id()
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
        if r.status == STATUS_BLOCKED:
            problems.append(f"{p.correction_id}: {p.tier} 阻断: {'; '.join(r.reasons) or '未授权'}")
        elif r.status == STATUS_PREVIEW:
            problems.append(
                f"{p.correction_id}: {p.tier} 未获授权（preview 不得写入）: {'; '.join(r.reasons)}"
            )
        elif r.status not in _PUBLISHABLE_STATUSES:
            problems.append(f"{p.correction_id}: 未知授权状态 {r.status!r}")
        if r.status == STATUS_AUTO_ALLOWED and p.tier == TIER_T2 and p.period in policy.closed_periods:
            problems.append(f"{p.correction_id}: 已关账期间 {p.period} 不得自动应用")
    return problems


# ------------------------------------------------------------------ 发布清单


def manifest_policy_fields(
    *,
    policy: CorrectionPolicy | None,
    proposals: Sequence[CorrectionProposal] = (),
    results: Sequence[AuthorizationResult] | None = None,
    now: datetime | None = None,
) -> dict:
    """manifest 需要的 policy/proposal/逐条 correction/证据 hash。"""
    proposals = list(proposals or [])
    if not proposals:
        return {
            "policy_id": policy.policy_id if policy else None,
            "policy_version": policy.version if policy else None,
            "policy_hash": policy.hash if policy else None,
            "proposal_hash": None,
            "corrections": [],
        }
    if results is None:
        results_by_id = evaluate_batch(proposals, policy, now=now).by_id() if policy else {}
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
                "period": p.period,
            }
        )
    return {
        "policy_id": policy.policy_id if policy else None,
        "policy_version": policy.version if policy else None,
        "policy_hash": policy.hash if policy else None,
        "proposal_hash": proposal_batch_hash(proposals),
        "corrections": corrections,
    }


def stale_pass_problems(
    manifest: Mapping[str, Any] | None,
    *,
    input_md5: str | None,
    policy: CorrectionPolicy | None,
    proposals: Sequence[CorrectionProposal] = (),
) -> list[str]:
    """旧 PASS 失效判定：输入 / 政策 / proposal hash 任一变化即不可复用。"""
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

    proposals = list(proposals or [])
    if proposals:
        current_proposal = proposal_batch_hash(proposals)
        recorded_proposal = manifest.get("proposal_hash")
        if not recorded_proposal:
            problems.append("manifest 未记录 proposal_hash（旧 PASS 不可复用）")
        elif recorded_proposal != current_proposal:
            problems.append(
                f"proposal hash 变化（{str(recorded_proposal)[:12]}… != {current_proposal[:12]}…）"
            )
    return problems
