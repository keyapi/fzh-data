"""把 parcel_track 出的运营异常 Excel 推到钉钉群。

复用 `dingtalk/dingtalk_robot` 的三个平铺脚本（不是包，需临时挂 sys.path）：
`send_file_card.send_file_to_dingtalk` 一步完成「上传 ERPNext → 发 ActionCard 卡片」。

导入是惰性的：`summarize()` 纯字符串、可离线测试，不发网络请求。
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any

_ROBOT_DIR = Path(__file__).resolve().parent.parent / "dingtalk" / "dingtalk_robot"

# 推文按「待办优先级」排列；同名分类可能来自多个 key（承运延误有 fedex 别名）
_HEADLINE: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("漏发/未交接", ("missing_not_handed",), "🔴"),
    ("卡件", ("stuck",), "🔴"),
    ("迟发", ("late_handover",), "🟠"),
    ("承运延误", ("carrier_slow", "fedex_slow"), "🟠"),
    ("数据异常/查无", ("not_found",), "⚪"),
)
_QUIET: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("正常交付", ("delivered_ok",)),
    ("在途", ("in_transit",)),
    ("建标未收件", ("fresh_no_pickup",)),
    ("已取消", ("cancelled",)),
    ("复用旧票", ("reused_no_label",)),
)
_CALIBER = "处理时间 3 营业日；UPS/FedEx 按美国联邦假日、GLS 按波兰法定假日"


def _robot_path() -> str:
    """把 dingtalk_robot 挂上 sys.path（其内部用绝对 import 互相引用）。"""
    if not _ROBOT_DIR.is_dir():
        raise FileNotFoundError(f"找不到钉钉推送脚本目录：{_ROBOT_DIR}")
    path = str(_ROBOT_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def summarize(stats: dict[str, Any], *, when: _dt.date | None = None) -> str:
    """run_report 的 stats → 钉钉 markdown 正文。

    钉钉自定义机器人的 markdown 不渲染表格，所以用列表。
    """
    day = when or _dt.date.today()
    counts = {str(k): int(v or 0) for k, v in (stats.get("counts") or {}).items()}
    lines = [
        f"## 尾程运营异常 · {day.isoformat()}",
        "",
        f"**入 {stats.get('in', 0)} 单**　→　UPS {stats.get('ups', 0)} / "
        f"FedEx {stats.get('fedex', 0)} / GLS {stats.get('gls', 0)}　·　停放 {stats.get('parked', 0)}",
        "",
    ]
    headline = [(zh, mark, sum(counts.get(k, 0) for k in keys)) for zh, keys, mark in _HEADLINE]
    headline = [(zh, mark, n) for zh, mark, n in headline if n]
    lines.append("**待办分类**")
    if headline:
        lines += [f"- {mark} {zh}：**{n}** 票" for zh, mark, n in headline]
    else:
        lines.append("- 无异常")
    quiet = [(zh, sum(counts.get(k, 0) for k in keys)) for zh, keys in _QUIET]
    quiet = [(zh, n) for zh, n in quiet if n]
    if quiet:
        lines += ["", "其余：" + "　".join(f"{zh} {n}" for zh, n in quiet)]
    lines += ["", f"> 口径：{_CALIBER}"]
    return "\n".join(lines)


def notify_report(
    out_xlsx: str | Path,
    stats: dict[str, Any],
    *,
    title: str | None = None,
    text: str | None = None,
    when: _dt.date | None = None,
    dry_run: bool = False,
) -> dict:
    """上传报表到 ERPNext 并发钉钉卡片；dry_run 只回正文、不碰网络。"""
    path = Path(out_xlsx)
    day = when or _dt.date.today()
    title = title or f"尾程运营异常 · {day.isoformat()}"
    text = text or summarize(stats, when=when)
    if dry_run:
        return {"errcode": 0, "dry_run": True, "title": title, "text": text, "file": str(path)}
    if not path.is_file():
        raise FileNotFoundError(f"报表不存在：{path}")
    _robot_path()
    from send_file_card import send_file_to_dingtalk

    return send_file_to_dingtalk(path, title=title, text=text)


def notify_failure(message: str, *, title: str = "尾程跟踪任务失败") -> dict:
    """无人值守跑挂时的告警；凭证缺失会同样抛出，由调用方兜底打印。"""
    _robot_path()
    from send_dingtalk import send_markdown

    return send_markdown(f"## {title}\n\n> {message}", title=title)
