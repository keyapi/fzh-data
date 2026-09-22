#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上传/产物的物理文件管理：分块落盘、哈希、原子发布、路径越界防护。

约定：
- 上传文件一律写进 `inputs/<job-id>/`，物理名固定为 `packslip.pdf` / `order.csv`。
  用户文件名只用来校验扩展名。
- worker 只在 `work/<job-id>/` 里生成临时文件。
- 全部硬校验通过后，产物按内容哈希原子移动到 `artifacts/`，再登记到数据库。
- 下载时用 `resolve_artifact_path` 复查绝对路径必须在 artifacts 根之下。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

CHUNK = 1024 * 1024

PACKSLIP_NAME = "packslip.pdf"
ORDER_NAME = "order.csv"
PACKSLIP_SUFFIX = ".pdf"
ORDER_SUFFIX = ".csv"


class UploadTooLarge(Exception):
    pass


class StoredPathError(Exception):
    pass


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_display_name(name: str) -> str:
    """只保留文件名部分，去掉任何目录成分，防止路径穿越。"""
    return Path(str(name or "")).name.strip() or "unnamed"


def validate_upload_name(name: str, kind: str, suffix: str) -> str:
    """校验这个槽位的扩展名。返回清洗后的显示名，不作为磁盘文件名。"""
    display = safe_display_name(name)
    got = Path(display).suffix.lower()
    if got != suffix.lower():
        raise ValueError(f"{kind}只接受 {suffix} 文件，收到 {got or '无扩展名'}")
    return display


def save_upload_stream(fileobj, dest: Path, max_bytes: int) -> tuple[int, str]:
    """把上传流分块写盘，同时算 SHA-256。绝不 `read()` 整个文件进内存。

    超限时删除半成品并抛 `UploadTooLarge`。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = fileobj.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge(
                        f"文件超过上限 {max_bytes // (1024 * 1024)} MB"
                    )
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest()


def publish_artifact(src: Path, artifacts_dir: Path, download_name: str) -> tuple[str, int, str]:
    """把产物原子移动到 artifacts 目录，按内容哈希命名。返回 (相对路径, 大小, hash)。

    同名不同内容不会互相覆盖；同名同内容复用同一物理文件。
    """
    src = Path(src)
    content_hash = sha256_file(src)
    suffix = src.suffix
    final_dir = Path(artifacts_dir) / content_hash[:2]
    final_dir.mkdir(parents=True, exist_ok=True)
    final = final_dir / f"{content_hash[:16]}{suffix}"

    if final.exists():
        src.unlink(missing_ok=True)
    else:
        os.replace(src, final)

    return str(final.relative_to(Path(artifacts_dir))).replace("\\", "/"), final.stat().st_size, content_hash


def resolve_artifact_path(artifacts_dir: Path, rel_path: str) -> Path:
    """把数据库里的相对路径还原成绝对路径，并确认没跑出 artifacts 根目录。"""
    root = Path(artifacts_dir).resolve()
    candidate = (root / str(rel_path)).resolve()
    if not candidate.is_file() or root not in candidate.parents:
        raise StoredPathError("产物路径无效或不在存储目录内")
    return candidate


def remove_work_dir(work_dir: Path, job_id: str) -> None:
    """清理某个任务的临时目录（保留 inputs 与 artifacts）。

    inputs 必须留着：页面上的「用相同输入重新处理」要从原文件重新排队。
    清理窗口由保留策略统一处理，不在每次出件后删。
    """
    target = Path(work_dir) / job_id
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def remove_job_dirs(inputs_dir: Path, work_dir: Path, job_id: str) -> None:
    """清理某个任务的上传与临时目录（保留 artifacts）。保留策略清理时使用。"""
    for base in (inputs_dir, work_dir):
        target = Path(base) / job_id
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)


def clone_inputs(src_dir: Path, dest_dir: Path) -> list[str]:
    """把源任务的上传文件复制到新任务目录（重试用）。优先硬链接省磁盘。

    返回复制过去的文件名列表。
    """
    src_dir, dest_dir = Path(src_dir), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for path in sorted(src_dir.iterdir()):
        if not path.is_file():
            continue
        dest = dest_dir / path.name
        dest.unlink(missing_ok=True)
        try:
            os.link(path, dest)
        except OSError:
            shutil.copy2(path, dest)
        names.append(path.name)
    return names
