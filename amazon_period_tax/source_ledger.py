# -*- coding: utf-8 -*-
"""源文件总账（R01–R09）：每个候选文件恰好一个终态，文件/行/金额可对账。

设计要点（gate_audit_20261120.md / gate_remediation_plan_20261120.md U-E1）：

- **每个候选恰好一个终态**：``used`` / ``dup`` / ``failed`` / ``out_of_period`` /
  ``approved_excluded`` / ``needs_review``。不允许同一文件既算成功又算失败。
- ``files_total = used + dup + failed + out_of_period + approved_excluded + needs_review``
  由 :meth:`SourceLedger.assert_conservation` 强校验；不守恒直接抛错，不能只打印。
- 库存（inventory）记录覆盖根目录/深层/排除夹/非 AMZ txt/非 txt/隐藏目录，
  每项也有终态（``not_applicable``），不静默消失。
- ``publish_blockers`` 把 failed / needs_review / 无内部日期 / 未审定跨期转成发布阻断项；
  诊断模式仍可输出完整清单，正式写入前必须为空。

本模块只做账本，不读文件、不写文件；解析与分类在 ``read_amz_txt.py``。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 候选文件终态（互斥）
STATE_USED = "used"
STATE_DUP = "dup"
STATE_FAILED = "failed"
STATE_OUT_OF_PERIOD = "out_of_period"
STATE_APPROVED_EXCLUDED = "approved_excluded"
STATE_NEEDS_REVIEW = "needs_review"
TERMINAL_STATES = (
    STATE_USED,
    STATE_DUP,
    STATE_FAILED,
    STATE_OUT_OF_PERIOD,
    STATE_APPROVED_EXCLUDED,
    STATE_NEEDS_REVIEW,
)

# 库存项终态（不在 Tax 候选分母内，但必须留清单）
STATE_NOT_APPLICABLE = "not_applicable"

# 文件种类
KIND_AMZ_TXT = "amz_txt"
KIND_NON_AMZ_TXT = "non_amz_txt"
KIND_NON_TXT = "non_txt"
KIND_DIR = "dir"

# 库存范围
SCOPE_IN_SCOPE = "in_scope"
SCOPE_EXCLUDED_FOLDER = "excluded_folder"
SCOPE_HIDDEN_DIR = "hidden_dir"
SCOPE_ROOT_FILE = "root_file"
SCOPE_NESTED_FILE = "nested_file"
SCOPE_OTHER_FILE = "other_file"
SCOPE_DIR = "dir"


@dataclass
class SourceRecord:
    """一个被枚举到的文件/目录的账本行。"""

    bucket: str
    rel: str  # 相对桶目录的路径，统一 / 分隔
    kind: str = KIND_AMZ_TXT
    scope: str = SCOPE_IN_SCOPE
    state: str = STATE_NEEDS_REVIEW
    reason: str | None = None
    approval: str | None = None
    size: int = 0
    md5: str | None = None
    sha256: str | None = None
    settlement_id: str | None = None
    account: str | None = None
    schema: str | None = None
    currency: str | None = None
    rows_expected: int | None = None
    rows_parsed: int | None = None
    amount_total: float | None = None
    out_of_period: bool = False
    no_period_date: bool = False
    suspected_amz: bool = False

    @property
    def is_candidate(self) -> bool:
        """是否进入 Tax 候选分母（AMZ 结算 txt 或疑似误名结算文件）。"""
        return self.kind == KIND_AMZ_TXT or self.suspected_amz


@dataclass
class SourceLedger:
    """单桶（或跨桶合并）的文件总账。"""

    bucket: str
    bucket_dir: str = ""
    records: list[SourceRecord] = field(default_factory=list)

    # ---------------------------------------------------------------- 记录
    def add(self, record: SourceRecord) -> SourceRecord:
        self.records.append(record)
        return record

    def add_inventory(
        self,
        rel: str,
        *,
        kind: str,
        scope: str,
        size: int = 0,
        suspected: bool = False,
        reason: str | None = None,
        state: str = STATE_NOT_APPLICABLE,
    ) -> SourceRecord:
        return self.add(
            SourceRecord(
                bucket=self.bucket,
                rel=rel,
                kind=kind,
                scope=scope,
                state=state,
                reason=reason,
                size=size,
                suspected_amz=suspected,
            )
        )

    # ---------------------------------------------------------------- 对账
    @property
    def candidates(self) -> list[SourceRecord]:
        return [r for r in self.records if r.is_candidate]

    @property
    def inventory(self) -> list[SourceRecord]:
        return [r for r in self.records if not r.is_candidate]

    def partition(self) -> dict[str, int]:
        """候选文件的终态分区（六类互斥）。"""
        out = {s: 0 for s in TERMINAL_STATES}
        for r in self.candidates:
            if r.state not in out:  # 内部错误：库存终态混进候选
                raise ValueError(f"候选文件出现非终态 {r.state!r}: {r.rel}")
            out[r.state] += 1
        return out

    def inventory_partition(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.inventory:
            key = f"{r.kind}:{r.scope}"
            out[key] = out.get(key, 0) + 1
        return out

    def assert_conservation(self) -> int:
        """``文件总数 == used+dup+failed+out+approved_excluded+needs_review``。"""
        part = self.partition()
        total = len(self.candidates)
        mapped = sum(part[s] for s in TERMINAL_STATES)
        if total != mapped:
            raise AssertionError(
                f"源文件总账不守恒: total={total} 分区和={mapped} 分区={part}"
            )
        return total

    def rows_partition(self) -> dict[str, int]:
        part = self.partition()
        used_rows = sum(int(r.rows_parsed or 0) for r in self.candidates if r.state == STATE_USED)
        return {
            "files_total": len(self.candidates),
            **part,
            "rows_used": used_rows,
        }

    # ---------------------------------------------------------------- 门禁
    def publish_blockers(self) -> list[str]:
        """正式写入前必须为空的阻断清单（诊断模式仍可打印）。"""
        blockers: list[str] = []
        part = self.partition()
        if part[STATE_FAILED]:
            blockers.append(f"FAIL={part[STATE_FAILED]}")
        if part[STATE_NEEDS_REVIEW]:
            blockers.append(f"NEEDS-REVIEW={part[STATE_NEEDS_REVIEW]}")
        if part[STATE_OUT_OF_PERIOD]:
            blockers.append(f"OUT-OF-PERIOD={part[STATE_OUT_OF_PERIOD]}")
        no_date = [r for r in self.candidates if r.no_period_date]
        if no_date:
            blockers.append(f"NO-PERIOD-DATE={len(no_date)}")
        return blockers

    def summary_lines(self) -> list[str]:
        part = self.rows_partition()
        inv = self.inventory_partition()
        inv_total = sum(inv.values())
        return [
            "SUMMARY files={files_total} used={used} dup={dup} failed={failed} "
            "out_of_period={out_of_period} approved_excluded={approved_excluded} "
            "needs_review={needs_review} rows_used={rows_used}".format(**part),
            f"INVENTORY total={inv_total} "
            + " ".join(f"{k}={v}" for k, v in sorted(inv.items())),
        ]


def cross_bucket_settlement_conflicts(ledgers: dict[str, SourceLedger]) -> list[dict]:
    """同一 settlement-id 跨账期桶重复（R07）：返回分组，**不删除、不修改**。

    同桶内的多版本冲突由解析阶段记为 ``needs_review``；这里补充跨桶视角。
    """
    by_sid: dict[str, list[SourceRecord]] = {}
    for ledger in ledgers.values():
        for r in ledger.candidates:
            if r.settlement_id and r.state == STATE_USED:
                by_sid.setdefault(str(r.settlement_id), []).append(r)
    out: list[dict] = []
    for sid, group in sorted(by_sid.items()):
        buckets = sorted({r.bucket for r in group})
        if len(buckets) > 1:
            out.append(
                {
                    "settlement_id": sid,
                    "buckets": buckets,
                    "files": sorted(f"{r.bucket}/{r.rel}" for r in group),
                    "accounts": sorted({r.account or "?" for r in group}),
                }
            )
    return out


