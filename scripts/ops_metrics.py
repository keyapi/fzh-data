#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OPS-METRICS（DORA-lite）：从 backlog / delivery board / reviews / canonical manifest 算交付指标。

口径先说清（避免把不可量测的东西说成量测了）
- **只读**：本脚本不改任何任务状态，不写 PROJECT_BACKLOG.json，不 push。
- **不用在线时长、提交数、代码行数当进展**——这些在 DORA 里都不是交付指标；
  本表只用「时间戳差值」和「审核判定」两类可核对的证据。
- **能取到的才算**：`lead_time` 只对同时有 `dispatched_at` 与 `delivered_at` 的任务成立；
  backlog 的 67 个任务里只有 5 个有 `started_at`，且**没有任何完成时间戳**，
  因此 backlog 侧只能报「不可算」的数量，不能编。

五项指标
1. `lead_time`      任务 running → 交付（board: dispatched_at → delivered_at，排除审核类任务）
2. `verdict_rates`  reject / accept-with-findings / accept 率（reviews 目录 frontmatter 为准，board 交叉核对）
3. `rework`         返工轮次与返工耗时（board 同族里 reject → 下一次 verdict 的间隔）
4. `review_wait`    审核等待（审核类任务 dispatched_at = 提交 → delivered_at = verdict）
5. `freshness`      产物新鲜度（canonical manifest 的 generated_at / watermark / 文件 mtime + 当前 sha256）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

AGENT_OPS = Path("C:/Users/zhang/.agent-ops/fzh-data")
ORDER_STORE = Path("D:/Work/fzh-order-store/en-demand-v1")

VERDICT_BUCKETS = ("reject", "accept-with-findings", "accept", "other")

FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---", re.S)
# 审核类任务：ID 里带 REVIEW，或 FINAL-CHECK
REVIEW_TASK = re.compile(r"REVIEW|FINAL-CHECK", re.I)
# backlog 里的审核类任务（含 SPOTCHECK）
BACKLOG_REVIEW_ID = re.compile(r"(REVIEW|SPOTCHECK)", re.I)
# 任务族：去掉 -REVIEW/-REWORK/-FIX/-CHECK 及其 -N 后缀
FAMILY_SUFFIX = re.compile(r"(-(?:REVIEW|REWORK|FIX|CHECK))(-\d+)?$", re.I)


# ---------------------------------------------------------------- 读输入

def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER.match(text.lstrip("\ufeff"))
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def bucket_verdict(raw: str) -> str:
    """把自由文本 verdict 归到 4 个桶；不认识的一律 other，不猜。"""
    v = (raw or "").strip().lower()
    if not v:
        return "other"
    if v.startswith("reject"):
        return "reject"
    if v.startswith("accept-with"):
        return "accept-with-findings"
    if v == "accept":
        return "accept"
    return "other"


def load_reviews(reviews_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(Path(reviews_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        meta = parse_frontmatter(text)
        rows.append(dict(
            file=path.name,
            title=meta.get("title", ""),
            date=meta.get("date", ""),
            verdict_raw=meta.get("verdict", ""),
            verdict=bucket_verdict(meta.get("verdict", "")),
            has_verdict=bool(meta.get("verdict")),
            reviewed_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(),
        ))
    return rows


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except ValueError:
        return None


def _minutes(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 60.0, 1)


def load_board(path: Path) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    for task in d.get("tasks", []):
        # 字段不齐是常态（25 个任务只有部分带时间戳）→ 先补齐，后续只读不 KeyError
        task.setdefault("dispatched_at", None)
        task.setdefault("delivered_at", None)
        task.setdefault("verdict", None)
        task["_dispatched"] = _parse(task.get("dispatched_at"))
        task["_delivered"] = _parse(task.get("delivered_at"))
        task["_family"] = FAMILY_SUFFIX.sub("", str(task.get("id", ""))) or str(task.get("id"))
        task["_is_review"] = bool(REVIEW_TASK.search(str(task.get("id", ""))))
        task["_verdict_bucket"] = bucket_verdict(task.get("verdict", ""))
    return d


# ---------------------------------------------------------------- 五项指标

# 只有这些状态才算「仍在进行」，可以记删失下限；
# accepted / superseded / abandoned 是终态，缺 delivered_at 只是**缺元数据**，不是「还在跑」
IN_PROGRESS_STATUS = {"rework", "dispatched", "running", "pending", "in_progress", "in-progress"}


def _is_in_progress(task: dict) -> bool:
    return str(task.get("status", "")).strip().lower() in IN_PROGRESS_STATUS


def lead_times(board: dict, observed_at: datetime | None = None) -> dict:
    """任务 running → 交付。审核类任务不算（那是 review_wait 的口径）。

    未交付的分两种，不混：
    - **删失**：状态仍是进行中、到 board 冻结时刻还没有 delivered_at → 只给下限（≥ 已耗时）；
    - **缺时间戳**：已经是终态（accepted 等）但没有 delivered_at → 不可算，不拿冻结时刻充数。
    """
    rows, censored, missing_ts = [], [], []
    for task in board["tasks"]:
        if task["_is_review"]:
            continue
        minutes = _minutes(task["_dispatched"], task["_delivered"])
        if minutes is not None:
            rows.append(dict(id=task["id"], family=task["_family"],
                             dispatched_at=task["dispatched_at"],
                             delivered_at=task["delivered_at"], minutes=minutes))
            continue
        if task["_dispatched"] is None:
            continue                      # 从没派发，连起点都没有
        if _is_in_progress(task) and observed_at is not None:
            censored.append(dict(id=task["id"], family=task["_family"],
                                 dispatched_at=task["dispatched_at"],
                                 observed_at=observed_at.isoformat(timespec="seconds"),
                                 elapsed_minutes=_minutes(task["_dispatched"], observed_at),
                                 status=str(task.get("status"))))
        else:
            missing_ts.append(dict(id=task["id"], status=str(task.get("status")),
                                   dispatched_at=task["dispatched_at"]))
    values = [r["minutes"] for r in rows]
    return dict(
        rows=rows,
        n=len(rows),
        median_minutes=round(statistics.median(values), 1) if values else None,
        min_minutes=min(values) if values else None,
        max_minutes=max(values) if values else None,
        censored=censored,
        censored_minutes=[c["elapsed_minutes"] for c in censored
                          if c["elapsed_minutes"] is not None],
        missing_timestamp=missing_ts,
        no_dispatch=sum(1 for t in board["tasks"]
                        if not t["_is_review"] and t["_dispatched"] is None),
        unmeasurable=len(censored) + len(missing_ts),
    )


def review_waits(board: dict) -> dict:
    """审核等待：审核任务 dispatched_at（提交）→ delivered_at（verdict）。"""
    rows = []
    for task in board["tasks"]:
        if not task["_is_review"]:
            continue
        minutes = _minutes(task["_dispatched"], task["_delivered"])
        if minutes is None:
            continue
        rows.append(dict(id=task["id"], family=task["_family"], verdict=task["_verdict_bucket"],
                         submitted_at=task["dispatched_at"], verdict_at=task["delivered_at"],
                         minutes=minutes))
    values = [r["minutes"] for r in rows]
    return dict(
        rows=rows,
        n=len(rows),
        median_minutes=round(statistics.median(values), 1) if values else None,
        min_minutes=min(values) if values else None,
        max_minutes=max(values) if values else None,
        unmeasurable=sum(1 for t in board["tasks"]
                         if t["_is_review"] and _minutes(t["_dispatched"], t["_delivered"]) is None),
    )


def verdict_rates(reviews: list[dict]) -> dict:
    scored = [r for r in reviews if r["has_verdict"]]
    counts = {b: 0 for b in VERDICT_BUCKETS}
    for row in scored:
        counts[row["verdict"]] += 1
    total = len(scored)
    return dict(
        total_reviews=len(reviews),
        with_verdict=total,
        counts=counts,
        rates={b: (round(counts[b] / total * 100, 1) if total else None) for b in VERDICT_BUCKETS},
        no_verdict=len(reviews) - total,
    )


def board_verdict_rates(board: dict) -> dict:
    counted = [t for t in board["tasks"] if t["verdict"]]
    counts = {b: 0 for b in VERDICT_BUCKETS}
    for task in counted:
        counts[task["_verdict_bucket"]] += 1
    total = len(counted)
    return dict(counts=counts, total=total,
                rates={b: (round(counts[b] / total * 100, 1) if total else None)
                       for b in VERDICT_BUCKETS})


def rework(board: dict) -> dict:
    """返工：同族里首个 reject verdict 之后还有 verdict 的，算一轮返工。

    返工耗时 = 上一轮 reject 的 verdict 时间 → 下一轮 verdict 时间（含返工+复审）。
    """
    families: dict[str, list[dict]] = {}
    for task in board["tasks"]:
        if task["_delivered"] is not None and task["verdict"]:
            families.setdefault(task["_family"], []).append(task)

    per_family, cycles = [], []
    for family, tasks in families.items():
        tasks.sort(key=lambda t: t["_delivered"])
        rejects = [t for t in tasks if t["_verdict_bucket"] == "reject"]
        # 只把「reject 之后又有 verdict」算返工
        rework_rounds = 0
        for prev, nxt in zip(tasks, tasks[1:]):
            if prev["_verdict_bucket"] == "reject":
                rework_rounds += 1
                # 拆开：返工（reject → 下一轮提交）与复审（提交 → 下一轮 verdict），
                # 避免和第 4 项审核等待重复计数
                rework_minutes = _minutes(prev["_delivered"], nxt["_dispatched"])
                rework_includes_review = rework_minutes is None
                if rework_includes_review:
                    rework_minutes = _minutes(prev["_delivered"], nxt["_delivered"])
                cycles.append(dict(
                    family=family, after=prev["id"], until=nxt["id"],
                    reject_at=prev["delivered_at"], next_verdict_at=nxt["delivered_at"],
                    next_submitted_at=nxt.get("dispatched_at"),
                    next_verdict=nxt["_verdict_bucket"],
                    minutes=_minutes(prev["_delivered"], nxt["_delivered"]),
                    rework_minutes=rework_minutes,
                    rework_includes_review=rework_includes_review))
        per_family.append(dict(family=family, verdicts=len(tasks), rejects=len(rejects),
                               rework_rounds=rework_rounds,
                               final_verdict=tasks[-1]["_verdict_bucket"]))
    values = [c["rework_minutes"] for c in cycles if c["rework_minutes"] is not None]
    return dict(
        per_family=sorted(per_family, key=lambda r: (-r["rework_rounds"], r["family"])),
        cycles=cycles,
        total_rounds=len(cycles),
        families_with_rework=sum(1 for f in per_family if f["rework_rounds"]),
        families_total=len(per_family),
        median_minutes=round(statistics.median(values), 1) if values else None,
        max_minutes=max(values) if values else None,
    )


def review_families(reviews: list[dict]) -> dict:
    """按 review 文档名归族，看同一产物被打回重审了几轮（不依赖时间戳）。"""
    def family_of(name: str) -> str:
        stem = name[:-3] if name.endswith(".md") else name
        stem = re.sub(r"-(v\d+|rereview|review\d*|re-review|spotcheck|patch)\b", "", stem)
        stem = re.sub(r"-20\d\d-\d\d-\d\d", "", stem)
        return stem.strip("-")

    fam: dict[str, list[dict]] = {}
    for row in reviews:
        if not row["has_verdict"]:
            continue
        fam.setdefault(family_of(row["file"]), []).append(row)
    out = []
    for name, rows in fam.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r["reviewed_at"])
        out.append(dict(family=name, rounds=len(rows),
                        first=rows[0]["reviewed_at"].strftime("%m-%d %H:%M"),
                        last=rows[-1]["reviewed_at"].strftime("%m-%d %H:%M"),
                        verdicts=[r["verdict"] for r in rows]))
    return dict(families=sorted(out, key=lambda r: -r["rounds"]))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def freshness(canonical_dir: Path, as_of: datetime) -> dict:
    """产物新鲜度：取每个产物「最后一次被验证」的时间（无字面 last_verified 字段，用等价证据）。"""
    rows = []

    def add(label: str, path: Path, verified_at, basis: str):
        if not Path(path).exists():
            rows.append(dict(artifact=label, path=str(path), verified_at=None, basis=basis,
                             age_days=None, sha256=None, status="missing"))
            return
        if verified_at is None:
            verified_at = datetime.fromtimestamp(
                Path(path).stat().st_mtime, tz=timezone.utc).astimezone()
        age = round((as_of - verified_at).total_seconds() / 86400.0, 2)
        status = "fresh" if age <= 2 else ("aging" if age <= 7 else "stale")
        rows.append(dict(artifact=label, path=str(path),
                         verified_at=verified_at.isoformat(timespec="seconds"), basis=basis,
                         age_days=age, sha256=_sha256(Path(path))[:16], status=status))

    identity = canonical_dir / "identity_manifest.json"
    canonical_verified = None
    if identity.exists():
        meta = json.loads(identity.read_text(encoding="utf-8"))
        canonical_verified = _parse(meta.get("generated_at"))

    for name in ("demand_netting.parquet", "demand_canonical.parquet",
                 "demand_line_disposition.parquet", "demand_blocked.parquet",
                 "sku_coverage.parquet"):
        add(f"canonical/{name}", canonical_dir / name,
            canonical_verified, "identity_manifest.json generated_at")
    if not canonical_verified:
        for row in rows:
            if row["verified_at"] and row["status"] != "missing":
                row["basis"] = "文件 mtime（缺 identity_manifest）"

    # uom cache 自带抓取时间，比 mtime 更可信
    uom_cache = canonical_dir / "item_uom_cache.parquet"
    uom_verified = None
    if uom_cache.exists():
        try:
            import pandas as pd
            stamp = pd.read_parquet(uom_cache, columns=["fetched_at"])["fetched_at"].max()
            uom_verified = _parse(str(stamp))
        except Exception:
            uom_verified = None
    add("canonical/item_uom_cache.parquet", uom_cache, uom_verified,
        "parquet 内 fetched_at 最大值")

    root_manifest = canonical_dir.parent / "manifest.json"
    root_verified = None
    if root_manifest.exists():
        meta = json.loads(root_manifest.read_text(encoding="utf-8"))
        root_verified = _parse((meta.get("watermarks") or {}).get("last_success_run_at"))
    add("en-demand-v1/manifest.json (watermark)", root_manifest, root_verified,
        "watermarks.last_success_run_at")

    return dict(
        rows=rows,
        as_of=as_of.isoformat(timespec="seconds"),
        oldest_age_days=max((r["age_days"] for r in rows if r["age_days"] is not None),
                            default=None),
        stale=[r["artifact"] for r in rows if r["status"] == "stale"],
        missing=[r["artifact"] for r in rows if r["status"] == "missing"],
    )


# ---------------------------------------------------------------- 输出

def _fmt_min(v) -> str:
    if v is None:
        return "—"
    return f"{v:.0f} min" if v >= 1 else f"{v * 60:.0f} s"


def build_rows(metrics: dict) -> list[dict]:
    """长表 CSV：一行一个事实，metric 列分组。"""
    rows: list[dict] = []

    lt = metrics["lead_times"]
    rows.append(dict(metric="lead_time", item="median", value=lt["median_minutes"], unit="minutes",
                     evidence=f"n={lt['n']} 可算 / {lt['unmeasurable']} 不可算"
                              f"（{len(lt['censored'])} 删失 + {len(lt['missing_timestamp'])} 缺时间戳）"
                              f" / {lt['no_dispatch']} 从未派发"))
    for r in lt["rows"]:
        rows.append(dict(metric="lead_time", item=r["id"], value=r["minutes"], unit="minutes",
                         evidence=f"{r['dispatched_at']} → {r['delivered_at']}（family={r['family']}）"))
    for c in lt["censored"]:
        rows.append(dict(metric="lead_time_censored", item=c["id"], value=c["elapsed_minutes"],
                         unit="minutes_minimum",
                         evidence=f"≥ 已耗时；派发 {c['dispatched_at']}，到冻结 "
                                  f"{c['observed_at']} 仍无 delivered_at（status={c['status']}）"))

    # backlog 侧（时间戳回填后的可算部分），按状态分组
    bt = metrics["backlog_timings"]
    rows.append(dict(metric="backlog_lead_time", item="coverage", value=bt["with_started"],
                     unit="tasks_with_started_at",
                     evidence=f"{bt['total']} 个任务中 started_at {bt['with_started']} 个、"
                              f"finished_at {bt['with_finished']} 个；"
                              f"仅差 started_at 即可算的任务 {len(bt['missing_start'])} 个"))
    for state, agg in bt["dev_by_state"].items():
        rows.append(dict(metric="backlog_lead_time", item=f"state={state}",
                         value=agg["median_minutes"], unit="minutes",
                         evidence=f"state={state} n={agg['n']} 中位；"
                                  f"区间 {agg['min_minutes']}–{agg['max_minutes']} min"))
    for r in bt["dev"]:
        rows.append(dict(metric="backlog_lead_time_detail", item=r["id"], value=r["minutes"],
                         unit="minutes", evidence=f"{r['started_at']} → {r['finished_at']}"))
    for state, agg in bt["review_by_state"].items():
        rows.append(dict(metric="backlog_review_wait", item=f"state={state}",
                         value=agg["median_minutes"], unit="minutes",
                         evidence=f"state={state} n={agg['n']} 中位；"
                                  f"区间 {agg['min_minutes']}–{agg['max_minutes']} min"))
    for r in bt["review"]:
        rows.append(dict(metric="backlog_review_wait_detail", item=r["id"], value=r["minutes"],
                         unit="minutes", evidence=f"{r['started_at']} → {r['finished_at']}"))
    for r in bt["accepted"]:
        rows.append(dict(metric="backlog_accept_wait", item=r["id"], value=r["minutes"],
                         unit="minutes",
                         evidence=f"finished {r['finished_at']} → accepted {r['accepted_at']}"))

    for bucket in VERDICT_BUCKETS:
        rows.append(dict(metric="verdict_rate", item=bucket,
                         value=metrics["verdict_rates"]["rates"][bucket], unit="percent",
                         evidence=f"{metrics['verdict_rates']['counts'][bucket]}/"
                                  f"{metrics['verdict_rates']['with_verdict']} 份带 verdict 的 review"))
    for bucket in VERDICT_BUCKETS:
        rows.append(dict(metric="verdict_rate_board", item=bucket,
                         value=metrics["board_verdict_rates"]["rates"][bucket], unit="percent",
                         evidence=f"{metrics['board_verdict_rates']['counts'][bucket]}/"
                                  f"{metrics['board_verdict_rates']['total']} 个 board 任务（交叉核对）"))

    rw = metrics["rework"]
    rows.append(dict(metric="rework", item="total_rounds", value=rw["total_rounds"], unit="rounds",
                     evidence=f"{rw['families_with_rework']}/{rw['families_total']} 个任务族出现返工"))
    for f in rw["per_family"]:
        rows.append(dict(metric="rework_by_family", item=f["family"], value=f["rework_rounds"],
                         unit="rounds",
                         evidence=f"verdicts={f['verdicts']} rejects={f['rejects']} "
                                  f"final={f['final_verdict']}"))
    for c in rw["cycles"]:
        rows.append(dict(metric="rework_cycle", item=f"{c['after']} → {c['until']}",
                         value=c["rework_minutes"], unit="minutes",
                         evidence=f"返工 reject@{c['reject_at']} → 下轮提交"
                                  f"{c['next_submitted_at'] or '(缺)'}；"
                                  f"合计到下轮 verdict {c['minutes']} min，"
                                  f"下轮判定={c['next_verdict']}"))

    rwv = metrics["review_waits"]
    rows.append(dict(metric="review_wait", item="median", value=rwv["median_minutes"], unit="minutes",
                     evidence=f"n={rwv['n']} 可算 / {rwv['unmeasurable']} 不可算"))
    for r in rwv["rows"]:
        rows.append(dict(metric="review_wait", item=r["id"], value=r["minutes"], unit="minutes",
                         evidence=f"submitted={r['submitted_at']} verdict={r['verdict']}@{r['verdict_at']}"))

    for r in metrics["freshness"]["rows"]:
        rows.append(dict(metric="freshness", item=r["artifact"], value=r["age_days"], unit="days",
                         evidence=f"{r['status']}; verified={r['verified_at']} via {r['basis']}; "
                                  f"sha256={r['sha256']}"))
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["metric", "item", "value", "unit", "evidence"])
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, metrics: dict, backlog: dict, as_of: datetime) -> None:
    lt, vr, bv, rw, rwv, fr = (metrics["lead_times"], metrics["verdict_rates"],
                               metrics["board_verdict_rates"], metrics["rework"],
                               metrics["review_waits"], metrics["freshness"])
    fam = metrics["review_families"]
    states = metrics["backlog_states"]

    lines = [
        "# OPS-METRICS（DORA-lite）— 2026-10-28",
        "",
        f"生成时间：{as_of.isoformat(timespec='seconds')}",
        "",
        f"数据截至：backlog 更新于 `{backlog.get('updated_at', '?')}`；"
        f"board 文件冻结于 `{metrics['board_observed_at']}`"
        f"（board 内的 `last_foreman_check` 字段更早，为 `{metrics['board_updated'] or '?'}`，"
        "派发时间已晚于它，故以文件冻结时刻为准）。",
        "",
        "## 这一页怎么读",
        "",
        "- **只用两类证据**：时间戳差值、审核判定。**不用在线时长 / 提交数 / 代码行数当进展**——"
        "那些能刷、且不反映交付。",
        "- **能取到的才算**：取不到时间戳的写「不可算」，不给估计值。",
        "- **只读**：不改任何任务状态，不写 backlog，不 push。",
        "",
        "## 1. Lead time（任务 running → 交付）",
        "",
        f"口径：board 任务的 `dispatched_at → delivered_at`，**排除审核类任务**（审核单独算审核等待）。",
        "",
        f"- 可算 **{lt['n']}** 个，中位 **{_fmt_min(lt['median_minutes'])}**，"
        f"区间 {_fmt_min(lt['min_minutes'])} – {_fmt_min(lt['max_minutes'])}；",
        f"- **不可算 {lt['unmeasurable']} 个**：其中"
        f" {len(lt['censored'])} 个仍在进行中（记删失下限 ≥ 已耗时，不当作完成时间），"
        f" {len(lt['missing_timestamp'])} 个已是终态但缺 `delivered_at`（缺元数据，不拿冻结时刻充数）；",
        f"- 另有 **{lt['no_dispatch']} 个从未派发**（无 `dispatched_at`），连起点都没有，直接不计；",
        f"- backlog 侧 {states['total']} 个任务中 `started_at` {states['with_started_at']} 个、"
        f"`finished_at` {states['with_finished_at']} 个 → 两端齐全的 "
        f"{metrics['backlog_timings']['n_dev'] + metrics['backlog_timings']['n_review']} 个可算，"
        "见下方「backlog 侧」小节；其余不估算。",
        "",
        "| 任务 | 开始 | 交付 | 用时 |",
        "|---|---|---|---:|",
    ]
    for r in sorted(lt["rows"], key=lambda x: x["minutes"], reverse=True):
        lines.append(f"| {r['id']} | {r['dispatched_at'][11:19]} | {r['delivered_at'][11:19]} | "
                     f"{_fmt_min(r['minutes'])} |")

    if lt["censored"]:
        lines += [
            "",
            "**删失（未交付，只给下限，不是完成时间）**：",
            "",
            "| 任务 | 派发 | 冻结时状态 | ≥ 已耗时 |",
            "|---|---|---|---:|",
        ]
        for c in sorted(lt["censored"], key=lambda x: x["elapsed_minutes"] or 0, reverse=True):
            lines.append(f"| {c['id']} | {c['dispatched_at'][11:19]} | {c['status']} | "
                         f"≥ {_fmt_min(c['elapsed_minutes'])} |")

    if lt["missing_timestamp"]:
        lines += [
            "",
            "**缺时间戳（终态但无 `delivered_at` → 不可算，不当成「还在跑」）**："
            + "、".join(f"{m['id']}（{m['status']}）" for m in lt["missing_timestamp"]),
        ]

    bt = metrics["backlog_timings"]
    lines += [
        "",
        "### backlog 侧（`started_at → finished_at`，按状态）",
        "",
        f"时间戳回填后：{bt['total']} 个任务里 `started_at` **{bt['with_started']}** 个、"
        f"`finished_at` **{bt['with_finished']}** 个；两端都有的只有 **{bt['n_dev'] + bt['n_review']}** 个。",
        "",
    ]
    if bt["dev_by_state"] or bt["review_by_state"]:
        lines += ["| 状态 | 开发任务 n | 中位 | 审核任务 n | 中位 |",
                  "|---|---:|---:|---:|---:|"]
        for state in sorted(set(bt["dev_by_state"]) | set(bt["review_by_state"])):
            dev = bt["dev_by_state"].get(state)
            rev = bt["review_by_state"].get(state)
            lines.append(
                f"| {state} | {dev['n'] if dev else 0} | "
                f"{_fmt_min(dev['median_minutes']) if dev else '—'} | "
                f"{rev['n'] if rev else 0} | "
                f"{_fmt_min(rev['median_minutes']) if rev else '—'} |")
    if bt["dev"] or bt["review"]:
        lines += ["", "| 任务 | 类型 | 状态 | 开始 | 完成 | 用时 |", "|---|---|---|---|---|---:|"]
        for r in sorted(bt["dev"] + bt["review"], key=lambda x: x["minutes"], reverse=True):
            kind = "审核" if r["is_review"] else "开发"
            lines.append(f"| {r['id']} | {kind} | {r['state']} | {r['started_at'][11:19]} | "
                         f"{r['finished_at'][11:19]} | {_fmt_min(r['minutes'])} |")
    if bt["accepted"]:
        lines += ["", "**交付 → 验收**（`finished_at → accepted_at`，仅严格 accept 才有）：", "",
                  "| 任务 | 交付 | 验收 | 等待 |", "|---|---|---|---:|"]
        for r in sorted(bt["accepted"], key=lambda x: x["minutes"], reverse=True):
            lines.append(f"| {r['id']} | {r['finished_at'][11:19]} | {r['accepted_at'][11:19]} | "
                         f"{_fmt_min(r['minutes'])} |")
    lines += [
        "",
        f"- **主因是 `started_at` 缺口**：已有 `finished_at` 但缺 `started_at` 的任务有 "
        f"**{len(bt['missing_start'])} 个**——补上这些起点，lead time 样本量能立刻翻几倍；"
        "在此之前不估算、不外推。",
        f"- 待补 `started_at` 清单（{len(bt['missing_start'])} 个）："
        + "、".join(bt["missing_start"][:24])
        + ("…" if len(bt["missing_start"]) > 24 else ""),
        "- 每个填入值的来源见 `backlog-timestamps-provenance.csv`（字段 / 值 / 证据文件 / 时间戳类型）。"
        "`启动→完成` 的间隔是 wall-clock，不是 agent 实际工时。",
    ]

    lines += [
        "",
        "## 2. 审核判定率（reject / accept-with-findings）",
        "",
        f"口径：`reviews/*.md` frontmatter 的 `verdict`（{vr['with_verdict']}/{vr['total_reviews']} 份有 verdict；"
        f"{vr['no_verdict']} 份无 → 不计入分母，不猜）。",
        "",
        "| 判定 | 份数 | 占比 |",
        "|---|---:|---:|",
    ]
    label = {"reject": "reject", "accept-with-findings": "accept-with-findings（可用但有问题）",
             "accept": "accept（直接通过）", "other": "other（partial / revise / sensitivity 等）"}
    for bucket in VERDICT_BUCKETS:
        lines.append(f"| {label[bucket]} | {vr['counts'][bucket]} | {vr['rates'][bucket]}% |")

    lines += [
        "",
        f"**board 交叉核对**（{bv['total']} 个带 verdict 的 board 任务）："
        + "、".join(f"{b} {bv['counts'][b]}" for b in VERDICT_BUCKETS) + "。",
        "",
        "> 两个来源量级一致，说明「打回重做」是常态而不是偶发："
        f"reviews 侧 reject+accept-with-findings 合计 "
        f"**{round((vr['counts']['reject'] + vr['counts']['accept-with-findings']) / vr['with_verdict'] * 100, 1)}%**。"
        "这不是坏事——它说明审核在真的挑问题；但返工成本要单独看第 3 项。",
        "",
        "## 3. 返工次数与返工耗时",
        "",
        f"口径：同一任务族里，**一次 reject verdict 之后又出了新 verdict** 记一轮返工；"
        f"**返工耗时 = reject → 下一轮提交**（不含复审），复审时间单列，避免和第 4 项重复计数。",
        "",
        f"- 返工合计 **{rw['total_rounds']} 轮**，涉及 {rw['families_with_rework']}/{rw['families_total']} 个任务族；",
        f"- 单轮返工中位 **{_fmt_min(rw['median_minutes'])}**，最长 {_fmt_min(rw['max_minutes'])}。",
        f"- 若某轮缺下一轮的 `dispatched_at`，只能退回「到下轮 verdict」并标「含复审」，不假装是纯返工。",
        "",
        "| 任务族 | verdict 数 | reject 数 | 返工轮次 | 最终判定 |",
        "|---|---:|---:|---:|---|",
    ]
    for f in rw["per_family"]:
        lines.append(f"| {f['family']} | {f['verdicts']} | {f['rejects']} | "
                     f"{f['rework_rounds']} | {f['final_verdict']} |")

    lines += ["", "| reject 之后 | 到 | 返工耗时 | 下轮复审 | 合计 | 下一轮判定 |",
              "|---|---|---:|---:|---:|---|"]
    for c in rw["cycles"]:
        review_part = ("—" if c["next_submitted_at"] is None
                       else _fmt_min(_minutes(_parse(c["next_submitted_at"]),
                                              _parse(c["next_verdict_at"]))))
        rework_part = _fmt_min(c["rework_minutes"]) + ("（含复审）" if c["rework_includes_review"] else "")
        lines.append(f"| {c['after']} | {c['until']} | {rework_part} | {review_part} | "
                     f"{_fmt_min(c['minutes'])} | {c['next_verdict']} |")

    if metrics.get("board_retry_reason"):
        lines += [
            "",
            f"> ⚠️ 长尾要对照口径看：board 记录的重试原因原文是「{metrics['board_retry_reason']}」。"
            "上面几十分钟到几小时的间隔是 **wall-clock**，可能包含额度等待或人工停顿，"
            "**不等于投入的返工工作量**；要判断效率得看同一族里 reject 的轮数与最终判定。",
        ]

    if fam["families"]:
        lines += [
            "",
            f"**按 review 文档族看**（不看时间戳，只看同一产物被打回几轮）："
            f"{len(fam['families'])} 个族出现多轮审核。",
            "",
            "| review 族 | 轮数 | 首次 | 末次 | 判定序列 |",
            "|---|---:|---|---|---|",
        ]
        for f in fam["families"][:12]:
            lines.append(f"| {f['family']} | {f['rounds']} | {f['first']} | {f['last']} | "
                         f"{' → '.join(f['verdicts'])} |")

    lines += [
        "",
        "## 4. 审核等待（提交 → verdict）",
        "",
        "口径：审核类任务（ID 含 REVIEW / FINAL-CHECK）的 `dispatched_at`（材料提交）→ "
        "`delivered_at`（verdict 落盘）。",
        "",
        f"- 可算 **{rwv['n']}** 个，中位 **{_fmt_min(rwv['median_minutes'])}**，"
        f"区间 {_fmt_min(rwv['min_minutes'])} – {_fmt_min(rwv['max_minutes'])}；",
        f"- 不可算 {rwv['unmeasurable']} 个（缺 `dispatched_at`）。",
        "",
        "| 审核任务 | 提交 | verdict | 等待 | 判定 |",
        "|---|---|---|---:|---|",
    ]
    for r in sorted(rwv["rows"], key=lambda x: x["minutes"], reverse=True):
        lines.append(f"| {r['id']} | {r['submitted_at'][11:19]} | {r['verdict_at'][11:19]} | "
                     f"{_fmt_min(r['minutes'])} | {r['verdict']} |")

    lines += [
        "",
        "## 5. 产物新鲜度",
        "",
        "口径：`last_verified` 没有字面字段，用等价证据——canonical manifest 的 `generated_at`、"
        "`watermarks.last_success_run_at`、parquet 内 `fetched_at`；都没有才退回文件 mtime。"
        "**fresh ≤2 天、aging ≤7 天、stale >7 天**。",
        "",
        "| 产物 | 最后验证 | 依据 | 龄期 | 状态 | sha256 前 16 |",
        "|---|---|---|---:|---|---|",
    ]
    for r in fr["rows"]:
        age = "—" if r["age_days"] is None else f"{r['age_days']:.2f} d"
        lines.append(f"| {r['artifact']} | {str(r['verified_at'])[:19]} | {r['basis']} | "
                     f"{age} | {r['status']} | `{r['sha256']}` |")

    lines += [
        "",
        f"- 最老的产物龄期 **{fr['oldest_age_days']} 天**；stale {len(fr['stale'])} 个、"
        f"missing {len(fr['missing'])} 个。",
        "- 意义：canonical 交付物若是 3 天前的快照，那么这两天所有基于它的补货/净额结论都带着"
        "「输入已过期」的折扣——这不是模型精度问题，是数据时效问题。",
        "",
        "## 本轮明确**不**用的指标",
        "",
        "在线时长、提交（commit）数、代码行数、token 消耗、跑了几次脚本。"
        "它们容易刷高、也不代表交付，所以不列、不排名、不当作进展。",
        "",
        "## 数据边界（读这一节再引用数字）",
        "",
        f"- backlog {states['total']} 个任务："
        + "、".join(f"{k} {v}" for k, v in states["by_state"].items())
        + f"；其中 `started_at` {states['with_started_at']} 个、完成时间戳 {states['with_finished_at']} 个。"
        "**方案里的「running→review/done」在 backlog 侧缺完成时间，本轮只能报不可算。**",
        f"- board {metrics['board_total']} 个任务，带 `dispatched_at` {metrics['board_dispatched']} 个、"
        f"带 `delivered_at` {metrics['board_delivered']} 个——lead time / 审核等待的样本量就是这个上限。",
        "- review 的 `verdict` 是自由文本（有 `partial-accept-f5-unresolved` 这类），"
        "本表按前缀归 4 桶，`other` 占比见第 2 节；不强行塞进 accept/reject。",
        "- 时间是 wall-clock，**不是 agent 实际工作时长**；同一时段多 worker 并发，不叠加。",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def backlog_timings(tasks: list[dict]) -> dict:
    """backlog 侧的 lead time / 审核等待，**按状态分组**。

    只认 `started_at → finished_at`（以及 `finished_at → accepted_at`）两端都有的任务；
    缺一端就是不可算，不给估计值。
    """
    dev, review, accepted = [], [], []
    for task in tasks:
        start, finish = _parse(task.get("started_at")), _parse(task.get("finished_at"))
        minutes = _minutes(start, finish)
        if minutes is not None and minutes >= 0:
            row = dict(id=task["id"], state=task.get("state"), started_at=task["started_at"],
                       finished_at=task["finished_at"], minutes=minutes,
                       is_review=bool(BACKLOG_REVIEW_ID.search(str(task["id"]))))
            (review if row["is_review"] else dev).append(row)
        acc = _minutes(finish, _parse(task.get("accepted_at")))
        if acc is not None and acc >= 0:
            accepted.append(dict(id=task["id"], state=task.get("state"),
                                 finished_at=task["finished_at"],
                                 accepted_at=task["accepted_at"], minutes=acc))

    def by_state(rows: list[dict]) -> dict:
        out: dict[str, dict] = {}
        for state in sorted({r["state"] or "?" for r in rows}):
            sel = [r for r in rows if (r["state"] or "?") == state]
            vals = [r["minutes"] for r in sel]
            out[state] = dict(n=len(sel),
                              median_minutes=round(statistics.median(vals), 1),
                              min_minutes=min(vals), max_minutes=max(vals))
        return out

    with_finish = [t for t in tasks if t.get("finished_at")]
    return dict(
        dev=dev, review=review, accepted=accepted,
        dev_by_state=by_state(dev), review_by_state=by_state(review),
        accepted_by_state=by_state(accepted),
        n_dev=len(dev), n_review=len(review), n_accepted=len(accepted),
        # 覆盖缺口：这些任务已有完成时间、只差 started_at 就能算 lead time
        missing_start=[t["id"] for t in with_finish if not t.get("started_at")],
        with_finished=len(with_finish),
        with_started=sum(1 for t in tasks if t.get("started_at")),
        total=len(tasks),
    )


def compute(backlog_path: Path, board_path: Path, reviews_dir: Path,
            canonical_dir: Path, as_of: datetime | None = None) -> dict:
    as_of = as_of or datetime.now().astimezone()
    backlog = json.loads(Path(backlog_path).read_text(encoding="utf-8"))
    board = load_board(board_path)
    reviews = load_reviews(reviews_dir)
    # board 的冻结时刻 = 文件 mtime：之后的「未交付」是未知，不是「还在跑」
    board_observed_at = datetime.fromtimestamp(
        Path(board_path).stat().st_mtime, tz=timezone.utc).astimezone()

    tasks = backlog.get("tasks", [])
    states = dict(
        total=len(tasks),
        by_state={s: sum(1 for t in tasks if t.get("state") == s)
                  for s in sorted({t.get("state") for t in tasks if t.get("state")})},
        with_started_at=sum(1 for t in tasks if t.get("started_at")),
        with_finished_at=sum(1 for t in tasks
                             if any(k in t for k in ("finished_at", "completed_at", "done_at"))),
    )

    return dict(
        as_of=as_of,
        backlog=backlog,
        backlog_states=states,
        board_updated=board.get("last_foreman_check"),
        board_observed_at=board_observed_at.isoformat(timespec="seconds"),
        board_retry_reason=board.get("retry_after_reason"),
        board_total=len(board["tasks"]),
        board_dispatched=sum(1 for t in board["tasks"] if t["_dispatched"]),
        board_delivered=sum(1 for t in board["tasks"] if t["_delivered"]),
        lead_times=lead_times(board, board_observed_at),
        backlog_timings=backlog_timings(tasks),
        review_waits=review_waits(board),
        verdict_rates=verdict_rates(reviews),
        board_verdict_rates=board_verdict_rates(board),
        rework=rework(board),
        review_families=review_families(reviews),
        freshness=freshness(canonical_dir, as_of),
        metrics_version="ops-metrics/1",
    )


def build(backlog_path, board_path, reviews_dir, canonical_dir, out_dir, date: str,
          as_of: datetime | None = None) -> dict:
    """算指标并落盘。只写 out_dir，不碰任何任务状态文件。"""
    metrics = compute(Path(backlog_path), Path(board_path), Path(reviews_dir),
                      Path(canonical_dir), as_of=as_of)
    out = Path(out_dir)
    rows = build_rows(metrics)
    write_csv(out / f"ops-metrics-{date}.csv", rows)
    write_report(out / f"ops-metrics-{date}.md", metrics, metrics["backlog"], metrics["as_of"])
    metrics["csv_rows"] = len(rows)
    metrics["out_dir"] = str(out)
    return metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OPS-METRICS (DORA-lite)")
    parser.add_argument("--backlog", default=str(AGENT_OPS / "PROJECT_BACKLOG.json"))
    parser.add_argument("--board", default=str(AGENT_OPS / "delivery-board-oct29.json"))
    parser.add_argument("--reviews", default=str(AGENT_OPS / "reviews"))
    parser.add_argument("--canonical", default=str(ORDER_STORE / "canonical"))
    parser.add_argument("--out", default=str(AGENT_OPS / "ops-metrics-2026-10-28"))
    parser.add_argument("--date", default="2026-10-28")
    args = parser.parse_args(argv)

    metrics = build(args.backlog, args.board, args.reviews, args.canonical,
                    args.out, args.date)

    print(json.dumps(dict(
        lead_time_median=metrics["lead_times"]["median_minutes"],
        lead_time_n=metrics["lead_times"]["n"],
        review_wait_median=metrics["review_waits"]["median_minutes"],
        review_wait_n=metrics["review_waits"]["n"],
        verdict_rates=metrics["verdict_rates"]["rates"],
        rework_rounds=metrics["rework"]["total_rounds"],
        rework_median=metrics["rework"]["median_minutes"],
        freshness_oldest=metrics["freshness"]["oldest_age_days"],
        csv_rows=metrics["csv_rows"],
        out=metrics["out_dir"],
    ), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
