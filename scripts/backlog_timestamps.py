#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BACKLOG-TIMESTAMPS：给 PROJECT_BACKLOG.json 的任务**补时间戳**（只补这三个字段）。

铁律
- **不改任务状态**：只允许新增 `started_at` / `finished_at` / `accepted_at` 三个键，
  其它任何字段（尤其 `state`）一个字节都不许变。脚本自带护栏，写完前逐任务比对。
- **不篡改历史**：已有值一律保留，绝不覆盖；宁可留空，也不猜。
- **证据可追**：每个填入值都记来源（文件路径 + 时间戳类型），写进 provenance CSV。

三类证据（只有这三类）
1. `attempt_id` 内嵌时间：`att-YYYYMMDD-HHMM-<slug>` → `started_at`。
   这条规则已用 5 个既有 `started_at` 逐个验证一致。
2. 产物 manifest 的 `generated_at`（或产物文件 mtime）→ 该任务的 `finished_at`。
3. 审核文档的**文件 mtime**（即 verdict 落盘时刻）→ 审核任务的 `finished_at`；
   若该审核判定为**严格 accept**，同一时刻记为对应任务的 `accepted_at`。

不填的情况（一律留空，并在报告里计数）
- `ready` / `blocked` / `running` 任务不填 `finished_at`（填了就与状态矛盾）；
- 同一份文件被两个任务认领（无法单独归属）→ 全部留空；
- 名字对不上 1:1 的，不猜（例：`M2-BACKTEST` 与 `forecast-backtest-horizon` 不认）。

用法
    uv run python scripts/backlog_timestamps.py            # 只预览，不写
    uv run python scripts/backlog_timestamps.py --write    # 备份后写入
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

AGENT_OPS = Path("C:/Users/zhang/.agent-ops/fzh-data")
ORDER_STORE = Path("D:/Work/fzh-order-store/en-demand-v1")
BACKLOG = AGENT_OPS / "PROJECT_BACKLOG.json"

ALLOWED_FIELDS = ("started_at", "finished_at", "accepted_at")
TZ = timezone(timedelta(hours=8))
ATTEMPT_RE = re.compile(r"^att-(\d{8})-(\d{4})-")

# 只在这些状态下补 finished_at（done = 已完成，review = 已交付待审）
FINISHED_STATES = {"done", "review"}

# --- 证据表：任务 id → 文件。全部显式列出，不做模糊匹配 -------------------
REVIEW_FOR_FINISH = {
    # 审核类任务：finished_at = 审核文档 mtime（verdict 落盘时刻）
    "WORKBOOK-V3-REVIEW": "reviews/business-workbook-v3-review-2026-10-28.md",
    "WORKBOOK-V4-REVIEW": "reviews/business-workbook-v4-review-2026-10-28.md",
    "WORKBOOK-V5-SPOTCHECK": "reviews/business-workbook-v5-spotcheck-2026-10-28.md",
    "LOOP-DESIGN-REVIEW": "reviews/loop-design-review-2026-10-28.md",
    "FRONTIER-UOM-REREVIEW": "reviews/frontier-uom-rereview-2026-10-28.md",
    "POLICY-OPTIONS-V2-REVIEW": "reviews/policy-options-v2-review-2026-10-28.md",
    "POLICY-OPTIONS-F5-SPOTCHECK": "reviews/policy-options-f5-spotcheck-2026-10-28.md",
    "POLICY-RECONCILE-V2-REVIEW": "reviews/policy-reconcile-v2-review-2026-10-28.md",
    "STOCKOUT-CENSORING-REVIEW": "reviews/stockout-censoring-review-2026-10-28.md",
    "PROMO-CLEARANCE-REVIEW": "reviews/promo-clearance-review-2026-10-28.md",
    "PROMO-CLEARANCE-V2-REVIEW": "reviews/promo-clearance-v2-review-2026-10-28.md",
    "STOCKOUT-WIRE-V2-REVIEW": "reviews/stockout-wire-v2-review-2026-10-28.md",
    "STOCKOUT-WIRE-V3-REVIEW": "reviews/stockout-wire-v3-review-2026-10-28.md",
}

ARTIFACT_FOR_FINISH = {
    # 产物类任务：finished_at = manifest.generated_at（无 manifest 时用产物文件 mtime）
    "POLICY-OPTIONS": "en-demand-v1/supply-netting/policy-options-2026-10-28/manifest.json",
    "POLICY-OPTIONS-FIX": "en-demand-v1/supply-netting/policy-options-2026-10-28-v2/manifest.json",
    "POLICY-RECONCILE": "en-demand-v1/supply-netting/policy-reconcile-2026-10-28/manifest.json",
    "POLICY-RECONCILE-FIX": "en-demand-v1/supply-netting/policy-reconcile-2026-10-28-v2/manifest.json",
    "SKU-SEGMENT-POLICY": "en-demand-v1/supply-netting/sku-segment-policy-2026-10-28/manifest.json",
    "STOCKOUT-CENSORING": "en-demand-v1/stockout-censoring-2026-10-28/manifest.json",
    "PROMO-CLEARANCE-FIX": "en-demand-v1/supply-netting/promo-clearance-2026-10-28-v2/manifest.json",
    # v1 没有 manifest，用产物 report.md 的 mtime 作 finished_at
    "PROMO-CLEARANCE": "en-demand-v1/supply-netting/promo-clearance-2026-10-28/report.md",
}

# --- 审核通过：只有**严格 accept** 才记 accepted_at -----------------------
ACCEPTING_REVIEWS = {
    # 任务 id → 判它通过的审核文档
    "PROMO-CLEARANCE-FIX": "reviews/promo-clearance-v2-review-2026-10-28.md",
    "POLICY-RECONCILE-FIX": "reviews/policy-reconcile-v2-review-2026-10-28.md",
    "PROMO-CLEARANCE-V2-REVIEW": "reviews/promo-clearance-v2-review-2026-10-28.md",
    "POLICY-RECONCILE-V2-REVIEW": "reviews/policy-reconcile-v2-review-2026-10-28.md",
    "POLICY-OPTIONS-F5-SPOTCHECK": "reviews/policy-options-f5-spotcheck-2026-10-28.md",
}


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse_attempt_ts(attempt_id: str | None) -> datetime | None:
    m = ATTEMPT_RE.match(str(attempt_id or ""))
    if not m:
        return None
    day, hhmm = m.group(1), m.group(2)
    return datetime(int(day[:4]), int(day[4:6]), int(day[6:8]),
                    int(hhmm[:2]), int(hhmm[2:]), tzinfo=TZ)


def resolve_path(rel: str) -> Path:
    if rel.startswith("reviews/"):
        return AGENT_OPS / rel
    if rel.startswith("en-demand-v1/"):
        return ORDER_STORE.parent / rel
    raise ValueError(rel)


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(TZ)


def _manifest_generated_at(path: Path) -> datetime | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    raw = meta.get("generated_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def read_verdict(path: Path) -> str:
    """读 frontmatter 的 verdict 原文（不做归桶）。"""
    text = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        if line.startswith("verdict:"):
            return line.partition(":")[2].strip()
    return ""


def is_strict_accept(verdict: str) -> bool:
    return verdict.strip().lower() == "accept"


def plan(backlog_path: Path = BACKLOG) -> dict:
    """算出该补哪些值；不写文件。"""
    doc = json.loads(Path(backlog_path).read_text(encoding="utf-8"))
    tasks = doc.get("tasks", [])
    by_id = {t["id"]: t for t in tasks}

    proposals: list[dict] = []      # 待填
    skipped: list[dict] = []        # 留空及原因

    # ---- 证据收敛：同一 (文件, 字段) 被多个任务认领 → 全部作废
    claims: dict[tuple[str, str], list[str]] = {}
    for task_id in REVIEW_FOR_FINISH:
        claims.setdefault((REVIEW_FOR_FINISH[task_id], "finished_at"), []).append(task_id)
    for task_id in ARTIFACT_FOR_FINISH:
        claims.setdefault((ARTIFACT_FOR_FINISH[task_id], "finished_at"), []).append(task_id)
    conflicts = {k: v for k, v in claims.items() if len(v) > 1}

    # ---- started_at（attempt_id 内嵌时间）
    for task in tasks:
        if task.get("started_at"):
            continue
        ts = parse_attempt_ts(task.get("attempt_id"))
        if ts is None:
            continue
        proposals.append(dict(task_id=task["id"], field="started_at", value=_iso(ts),
                              source=f"attempt_id={task['attempt_id']}",
                              evidence="attempt_id 内嵌 YYYYMMDD-HHMM", verdict=""))

    # ---- finished_at
    for task in tasks:
        task_id = task["id"]
        if task.get("finished_at"):
            continue
        if task.get("state") not in FINISHED_STATES:
            if task_id in REVIEW_FOR_FINISH or task_id in ARTIFACT_FOR_FINISH:
                skipped.append(dict(task_id=task_id, field="finished_at",
                                    reason=f"state={task.get('state')}，填 finished_at 会与状态矛盾"))
            continue
        rel = REVIEW_FOR_FINISH.get(task_id) or ARTIFACT_FOR_FINISH.get(task_id)
        if rel is None:
            continue
        if (rel, "finished_at") in conflicts:
            skipped.append(dict(task_id=task_id, field="finished_at",
                                reason=f"证据被 {len(conflicts[(rel, 'finished_at')])} 个任务共享，无法归属"))
            continue
        path = resolve_path(rel)
        if not path.exists():
            skipped.append(dict(task_id=task_id, field="finished_at",
                                reason=f"证据文件不存在：{rel}"))
            continue
        if task_id in REVIEW_FOR_FINISH:
            ts, kind = _mtime(path), "审核文档 mtime（verdict 落盘）"
        else:
            ts = _manifest_generated_at(path)
            kind = "manifest.generated_at"
            if ts is None:
                ts, kind = _mtime(path), "产物文件 mtime（无 manifest）"
        proposals.append(dict(task_id=task_id, field="finished_at", value=_iso(ts),
                              source=rel, evidence=kind, verdict=""))

    # ---- accepted_at（严格 accept）
    for task_id, rel in ACCEPTING_REVIEWS.items():
        task = by_id.get(task_id)
        if task is None:
            skipped.append(dict(task_id=task_id, field="accepted_at", reason="任务不在 backlog"))
            continue
        if task.get("accepted_at"):
            continue
        path = resolve_path(rel)
        if not path.exists():
            skipped.append(dict(task_id=task_id, field="accepted_at",
                                reason=f"证据文件不存在：{rel}"))
            continue
        verdict = read_verdict(path)
        if not is_strict_accept(verdict):
            skipped.append(dict(task_id=task_id, field="accepted_at",
                                reason=f"verdict={verdict or '(无)'} 不是严格 accept"))
            continue
        proposals.append(dict(task_id=task_id, field="accepted_at", value=_iso(_mtime(path)),
                              source=rel, evidence="审核文档 mtime（verdict=accept）",
                              verdict=verdict))

    # ---- 时序自检：finished_at 不得早于 started_at
    #  两条证据打架时，**产物/审核时间戳是可核实事实，attempt_id 只是「某次派发」**；
    #  attempt_id 晚于产物完成，说明那是二次派发而非任务起点 → 只丢 started_at，保留 finished_at。
    by_task: dict[str, dict[str, dict]] = {}
    for p in proposals:
        by_task.setdefault(p["task_id"], {})[p["field"]] = p

    valid, rejected = [], []
    for task_id, fields in by_task.items():
        start_p, finish_p = fields.get("started_at"), fields.get("finished_at")
        if start_p and finish_p:
            try:
                if datetime.fromisoformat(finish_p["value"]) < datetime.fromisoformat(start_p["value"]):
                    skipped.append(dict(
                        task_id=task_id, field="started_at",
                        reason=f"与 {finish_p['source']} 的完成时间({finish_p['value']})矛盾："
                               f"attempt_id 晚于产物完成，疑似二次派发，不作任务起点"))
                    start_p = None
            except ValueError:
                pass
        for p in (start_p, finish_p, fields.get("accepted_at")):
            if p is not None:
                valid.append(p)

    # `rejected` 预留：被剔除的项都已进 `skipped` 并带原因，不重复记账
    rejected: list[dict] = []
    return dict(doc=doc, proposals=valid, rejected=rejected, skipped=skipped,
                conflicts={f"{k[0]}#{k[1]}": v for k, v in conflicts.items()})


def apply_plan(result: dict) -> dict:
    """把 proposals 写进 doc（仅新增键），返回新 doc。"""
    doc = result["doc"]
    by_id = {t["id"]: t for t in doc["tasks"]}
    for p in result["proposals"]:
        by_id[p["task_id"]].setdefault(p["field"], p["value"])
    return doc


def diff_guard(before: dict, after: dict) -> list[str]:
    """只允许新增 ALLOWED_FIELDS；任何其它差异都算违规。"""
    problems: list[str] = []
    if list(before.keys()) != list(after.keys()):
        problems.append(f"顶层键变化：{list(before.keys())} → {list(after.keys())}")
    if before.get("updated_at") != after.get("updated_at"):
        problems.append("updated_at 被改动")

    before_tasks = {t["id"]: t for t in before.get("tasks", [])}
    after_tasks = {t["id"]: t for t in after.get("tasks", [])}
    if set(before_tasks) != set(after_tasks):
        problems.append("任务集合发生变化")
    for task_id, old in before_tasks.items():
        new = after_tasks.get(task_id, {})
        for key, old_val in old.items():
            if new.get(key) != old_val:
                problems.append(f"{task_id}.{key} 被改动：{old_val!r} → {new.get(key)!r}")
        for key in new:
            if key not in old and key not in ALLOWED_FIELDS:
                problems.append(f"{task_id} 新增了非白名单字段 {key}")
    return problems


def write_provenance(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["task_id", "field", "value", "source", "evidence", "verdict", "status", "reason"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for p in result["proposals"]:
            writer.writerow(dict(p, status="filled", reason=""))
        for r in result["rejected"]:
            writer.writerow(dict(r, status="rejected"))
        for s in result["skipped"]:
            writer.writerow(dict(s, value="", source="", evidence="", verdict="", status="skipped"))


def run(backlog_path: Path = BACKLOG, write: bool = False,
        provenance_path: Path | None = None) -> dict:
    backlog_path = Path(backlog_path)
    result = plan(backlog_path)
    after = apply_plan(result)
    problems = diff_guard(result["doc"], after)

    if provenance_path is not None:
        write_provenance(Path(provenance_path), result)

    written = False
    backup = None
    if write and not problems:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        backup = backlog_path.with_suffix(backlog_path.suffix + f".bak-{stamp}")
        shutil.copy2(backlog_path, backup)
        text = json.dumps(after, ensure_ascii=False, indent=1)
        backlog_path.write_text(text, encoding="utf-8")
        written = True

    return dict(proposals=result["proposals"], rejected=result["rejected"],
                skipped=result["skipped"], conflicts=result["conflicts"],
                problems=problems, written=written, backup=str(backup) if backup else None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BACKLOG-TIMESTAMPS 时间戳回填")
    parser.add_argument("--backlog", default=str(BACKLOG))
    parser.add_argument("--write", action="store_true", help="真的写入（默认只预览）")
    parser.add_argument("--provenance",
                        default=str(AGENT_OPS / "ops-metrics-2026-10-28"
                                    / "backlog-timestamps-provenance.csv"))
    args = parser.parse_args(argv)

    out = run(Path(args.backlog), write=args.write, provenance_path=Path(args.provenance))

    by_field: dict[str, int] = {}
    for p in out["proposals"]:
        by_field[p["field"]] = by_field.get(p["field"], 0) + 1
    print(json.dumps(dict(
        filled=by_field,
        filled_total=len(out["proposals"]),
        rejected=len(out["rejected"]),
        skipped=len(out["skipped"]),
        conflicts=out["conflicts"],
        guard_problems=out["problems"],
        written=out["written"],
        backup=out["backup"],
    ), ensure_ascii=False, indent=1))
    if not args.write:
        print("（预览模式，未写入；加 --write 生效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
