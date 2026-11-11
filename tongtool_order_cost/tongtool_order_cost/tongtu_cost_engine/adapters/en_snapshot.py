# -*- coding: utf-8 -*-
"""月度快照冻结：把订单/EN/映射文件复制到 snapshots/YYYYMM 并生成 manifest。

manifest 记录 sha256、字节数、来源路径、抓取时间与时区，供结果复现与审计。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Mapping

TZ_CN = timezone(timedelta(hours=8))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_snapshot(
    month: str,
    sources: Mapping[str, Path],
    out_root: Path,
) -> Path:
    """冻结一个月度快照。

    Args:
        month: `YYYYMM`（如 202608）。
        sources: 逻辑名 → 本地文件路径（订单 CSV、EN 明细、仓库映射、flags 等）。
        out_root: snapshots 根目录。
    Returns:
        快照目录（`out_root/YYYYMM`）。
    """
    month = str(month).strip()
    if not (len(month) == 6 and month.isdigit()):
        raise ValueError(f"month 必须是 YYYYMM: {month!r}")
    dest = Path(out_root) / month
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"快照目录非空，拒绝覆盖: {dest}")
    dest.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict] = {}
    for name, src in sources.items():
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(f"快照源文件不存在: {name} -> {src}")
        target = dest / src.name
        if target.exists():
            raise FileExistsError(f"快照内重名文件: {target}")
        shutil.copy2(src, target)
        files[name] = {
            "file": src.name,
            "source": str(src),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
        }

    manifest = {
        "month": month,
        "created_at": datetime.now(TZ_CN).isoformat(),
        "timezone": "Asia/Shanghai",
        "sources": files,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dest


def verify_snapshot(snapshot_dir: Path) -> list[str]:
    """按 manifest 校验文件存在与 sha256；返回错误列表（空=通过）。"""
    snapshot_dir = Path(snapshot_dir)
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for name, meta in manifest.get("sources", {}).items():
        p = snapshot_dir / meta["file"]
        if not p.exists():
            errors.append(f"{name}: 文件缺失 {p.name}")
            continue
        if _sha256(p) != meta["sha256"]:
            errors.append(f"{name}: sha256 不一致 {p.name}")
    return errors
