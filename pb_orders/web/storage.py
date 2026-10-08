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


def _artifact_placement(src: Path, artifacts_dir: Path) -> tuple[Path, str, int]:
    """算出内容寻址的落点：返回 (目标路径, sha256, 大小)。"""
    src = Path(src)
    content_hash = sha256_file(src)
    final_dir = Path(artifacts_dir) / content_hash[:2]
    final_dir.mkdir(parents=True, exist_ok=True)
    return final_dir / f"{content_hash[:16]}{src.suffix}", content_hash, src.stat().st_size


def publish_artifact(src: Path, artifacts_dir: Path, download_name: str) -> tuple[str, int, str]:
    """把**产物**原子移动到 artifacts 目录，按内容哈希命名。返回 (相对路径, 大小, hash)。

    产物是一次性的：登记完就不需要留在 work 目录，所以移走省一份磁盘。
    同内容复用同一个物理文件（不同任务出同样的件不会各存一份）。
    """
    src = Path(src)
    final, content_hash, size = _artifact_placement(src, artifacts_dir)
    if final.exists():
        src.unlink(missing_ok=True)
    else:
        os.replace(src, final)
    return str(final.relative_to(Path(artifacts_dir))).replace("\\", "/"), size, content_hash


def publish_input_copy(src: Path, artifacts_dir: Path) -> tuple[str, int, str]:
    """把**上传的输入**放进 artifacts 供下载核对，返回 (相对路径, 大小, hash)。

    与 `publish_artifact` 的区别：**绝不移走原文件**。inputs/ 里的那份还要给
    worker 用、还要供「用相同输入重新处理」，移动它等于把任务弄坏。
    优先硬链接（同一份内容不占两份磁盘），不行再复制。
    """
    src = Path(src)
    final, content_hash, size = _artifact_placement(src, artifacts_dir)
    if not final.exists():
        try:
            os.link(src, final)
        except OSError:
            shutil.copy2(src, final)
    return str(final.relative_to(Path(artifacts_dir))).replace("\\", "/"), size, content_hash


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


def link_or_copy(src: Path, dest: Path) -> Path:
    """把文件放到目标路径（优先硬链接省磁盘），同名已存在则覆盖。

    只用在校验过的文件上（如已发布的 checked CSV 复用成出件任务的 `order.csv`），
    绝不用用户文件名拼路径。
    """
    src, dest = Path(src), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)
    return dest


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
        link_or_copy(path, dest_dir / path.name)
        names.append(path.name)
    return names
