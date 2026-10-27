#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建任务的共享服务层：网页表单与 JSON API 都走这里。

只负责「校验上传 → 落盘 → 建 job → 登记输入 → 入队」，真正的处理在 worker。
这样不会出现「页面能做、API 不能做」或两套参数口径。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from web import storage
from web.config import Settings
from web.repository import NO_STOCK_KEY, OrderNumberConflict, Repository, new_id

EnqueueFn = Callable[[str], None]


class JobServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint


def parse_sku_list(raw: str) -> list[str]:
    """与网页一致：逗号/分号/空白分隔，按小写去重。"""
    import re
    seen: set[str] = set()
    out: list[str] = []
    for part in re.split(r"[,，;；\s]+", raw or ""):
        sku = part.strip()
        if not sku or sku.lower() in seen:
            continue
        seen.add(sku.lower())
        out.append(sku)
    return out


def current_no_stock(settings: Settings, repo: Repository) -> str:
    stored = repo.get_setting(NO_STOCK_KEY)
    if stored is not None:
        return stored["value"]
    return ",".join(settings.default_no_stock)


def _save(upload, label: str, suffix: str, dest: Path, settings: Settings) -> tuple[str, str]:
    """返回 (display_name, sha256)。"""
    try:
        display = storage.validate_upload_name(getattr(upload, "filename", ""), label, suffix)
        _size, digest = storage.save_upload_stream(upload.file, dest, settings.max_upload_bytes)
    except ValueError as exc:
        raise JobServiceError(400, "invalid_input", str(exc)) from exc
    except storage.UploadTooLarge as exc:
        raise JobServiceError(413, "payload_too_large", str(exc)) from exc
    return display, digest


def _register_inputs(settings: Settings, repo: Repository, job_id: str, displays: dict[str, str]) -> None:
    for slot, kind, mime in (
        (storage.PACKSLIP_NAME, "input_packslip", "application/pdf"),
        (storage.ORDER_NAME, "input_order", "text/csv"),
    ):
        path = settings.inputs_dir / job_id / slot
        if not path.is_file():
            continue
        try:
            rel_path, size, digest = storage.publish_input_copy(path, settings.artifacts_dir)
            repo.add_artifact(
                job_id=job_id, kind=kind, original_name=slot,
                download_name=displays.get(slot) or slot, rel_path=rel_path,
                content_hash=digest, size_bytes=size, mime_type=mime,
            )
        except Exception:  # noqa: BLE001 - 登记失败不挡任务
            pass


def _fingerprint(kind: str, no_stock: str, reorder_sig: str, hashes: list[str]) -> str:
    h = hashlib.sha256()
    h.update(kind.encode("utf-8"))
    h.update(b"|")
    h.update(no_stock.encode("utf-8"))
    h.update(b"|")
    h.update(reorder_sig.encode("utf-8"))
    for item in hashes:
        h.update(b"|")
        h.update(item.encode("ascii"))
    return h.hexdigest()


def hash_upload(upload) -> str:
    """读一遍上传流算 SHA-256，然后把指针复位，交给后面的落盘逻辑。"""
    import hashlib as _hashlib
    h = _hashlib.sha256()
    fh = upload.file
    try:
        fh.seek(0)
    except Exception:  # noqa: BLE001
        pass
    while True:
        chunk = fh.read(1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
    try:
        fh.seek(0)
    except Exception:  # noqa: BLE001
        pass
    return h.hexdigest()


def make_fingerprint(kind: str, no_stock: str, reorder_sig: str, hashes: list[str]) -> str:
    return _fingerprint(kind, no_stock, reorder_sig, hashes)


def parse_reorder_tokens(raw: str) -> tuple[list[str], dict[str, str]]:
    """解析 CLI 兼容的 reorder 文本：`PO`（自动）或 `PO=-2`（显式）。"""
    auto: list[str] = []
    explicit: dict[str, str] = {}
    for part in (raw or "").replace("，", ",").split(","):
        token = part.strip()
        if not token:
            continue
        if "=" in token:
            po, suffix = token.split("=", 1)
            po, suffix = po.strip(), suffix.strip()
            if po:
                explicit[po] = suffix or "-2"
        else:
            auto.append(token)
    return auto, explicit


def prepare_reorder(
    repo: Repository, job_id: str, reorder_raw: str, reorder_map: dict[str, str] | None,
) -> list[str]:
    """把请求里的 reorder 变成显式 token 列表，并在库里预留号码。

    返回形如 `["137924672=-2", "138000001=-3"]`，交给 worker 直接使用。
    """
    auto, explicit = parse_reorder_tokens(reorder_raw)
    for po, suffix in (reorder_map or {}).items():
        if str(po).strip():
            explicit[str(po).strip()] = str(suffix).strip() or "-2"
    bases = list(dict.fromkeys(auto + list(explicit.keys())))
    if not bases:
        return []
    try:
        reserved = repo.reserve_order_numbers(bases, job_id, explicit)
    except OrderNumberConflict as exc:
        raise JobServiceError(409, "reorder_conflict", str(exc),
                              hint="换一个未占用的 -N 后缀，或先查已用订单号。") from exc
    return [f"{po}={suffix}" for po, suffix in reserved.items()]


def create_stock_check_job(
    settings: Settings, repo: Repository, raw_csv, actor: str, no_stock: str,
    enqueue: EnqueueFn, job_id: str | None = None,
) -> str:
    job_id = job_id or new_id("job")
    display, digest = _save(raw_csv, "原始订单 CSV", storage.ORDER_SUFFIX,
                            settings.inputs_dir / job_id / storage.ORDER_NAME, settings)
    repo.create_job(
        job_id=job_id, job_type="stock_check", created_by=actor or "web-user",
        no_stock=",".join(parse_sku_list(no_stock)), no_stock_note=None,
        validate_only=False, allow_unmatched=False, input_packslip="",
        input_order=display, pipeline_version=settings.pipeline_version,
        input_sha256=_fingerprint("stock_check", no_stock, "", [digest]),
    )
    _register_inputs(settings, repo, job_id, {storage.ORDER_NAME: display})
    enqueue(job_id)
    return job_id


def create_fulfillment_job(
    settings: Settings, repo: Repository, order_csv, packslip, actor: str,
    no_stock: str, no_stock_note: str, validate_only: bool, allow_unmatched: bool,
    reorder_raw: str, reorder_map: dict[str, str] | None, enqueue: EnqueueFn,
    job_id: str | None = None,
) -> tuple[str, str]:
    job_id = job_id or new_id("job")
    # 先校验 Packslip：两个文件都错时报的第一个错与旧版页面一致。
    pdf_display, pdf_hash = _save(
        packslip, "Packslip PDF", storage.PACKSLIP_SUFFIX,
        settings.inputs_dir / job_id / storage.PACKSLIP_NAME, settings,
    )
    order_display, order_hash = _save(
        order_csv, "订单 CSV", storage.ORDER_SUFFIX,
        settings.inputs_dir / job_id / storage.ORDER_NAME, settings,
    )
    reorder = prepare_reorder(repo, job_id, reorder_raw, reorder_map)
    reorder_sig = reorder_raw + "|" + json.dumps(reorder_map or {}, ensure_ascii=False, sort_keys=True)
    fingerprint = _fingerprint("fulfillment", no_stock, reorder_sig, [order_hash, pdf_hash])
    repo.create_job(
        job_id=job_id, job_type="fulfillment", created_by=actor or "web-user",
        no_stock=",".join(parse_sku_list(no_stock)), no_stock_note=no_stock_note.strip() or None,
        validate_only=validate_only, allow_unmatched=allow_unmatched,
        input_packslip=pdf_display, input_order=order_display,
        pipeline_version=settings.pipeline_version, input_sha256=fingerprint,
        reorder=reorder,
    )
    _register_inputs(settings, repo, job_id,
                     {storage.PACKSLIP_NAME: pdf_display, storage.ORDER_NAME: order_display})
    enqueue(job_id)
    return job_id, fingerprint


def checked_artifact(repo: Repository, job_id: str) -> dict | None:
    return next((a for a in repo.list_artifacts(job_id) if a["kind"] == "checked_order"), None)


def create_fulfillment_from_check(
    settings: Settings, repo: Repository, check_job_id: str, packslip, actor: str,
    reorder_raw: str, reorder_map: dict[str, str] | None, enqueue: EnqueueFn,
    job_id: str | None = None,
) -> tuple[str, str]:
    source = repo.get_job(check_job_id)
    if source is None or source["job_type"] != "stock_check":
        raise JobServiceError(404, "not_found", "这不是一个库存预检任务")
    checked = checked_artifact(repo, check_job_id) if source["status"] == "succeeded" else None
    if checked is None:
        raise JobServiceError(409, "conflict_state", "来源任务的 checked CSV 不可用",
                              hint="先重新跑一次库存预检。")
    try:
        checked_path = storage.resolve_artifact_path(settings.artifacts_dir, checked["rel_path"])
    except storage.StoredPathError as exc:
        raise JobServiceError(409, "conflict_state", str(exc)) from exc

    job_id = job_id or new_id("job")
    pdf_display, pdf_hash = _save(
        packslip, "Packslip PDF", storage.PACKSLIP_SUFFIX,
        settings.inputs_dir / job_id / storage.PACKSLIP_NAME, settings,
    )
    storage.link_or_copy(checked_path, settings.inputs_dir / job_id / storage.ORDER_NAME)
    reorder = prepare_reorder(repo, job_id, reorder_raw, reorder_map)
    reorder_sig = reorder_raw + "|" + json.dumps(reorder_map or {}, ensure_ascii=False, sort_keys=True)
    fingerprint = _fingerprint("fulfillment-from-check", "", reorder_sig, [pdf_hash, checked["content_hash"]])
    repo.create_job(
        job_id=job_id, job_type="fulfillment", created_by=actor or "web-user",
        no_stock="", no_stock_note=None, validate_only=False, allow_unmatched=False,
        input_packslip=pdf_display, input_order=checked["download_name"],
        pipeline_version=settings.pipeline_version, source_job_id=check_job_id,
        input_sha256=fingerprint, reorder=reorder,
    )
    _register_inputs(settings, repo, job_id,
                     {storage.PACKSLIP_NAME: pdf_display, storage.ORDER_NAME: checked["download_name"]})
    enqueue(job_id)
    return job_id, fingerprint


def retry_job(
    settings: Settings, repo: Repository, old_job_id: str, enqueue: EnqueueFn,
) -> str:
    old = repo.get_job(old_job_id)
    if old is None:
        raise JobServiceError(404, "not_found", "任务不存在")
    src_dir = settings.inputs_dir / old_job_id
    if not src_dir.is_dir():
        raise JobServiceError(409, "conflict_state", "原任务的输入文件已被清理，请重新上传。")
    new_job_id = new_id("job")
    storage.clone_inputs(src_dir, settings.inputs_dir / new_job_id)
    repo.create_job(
        job_id=new_job_id, job_type=old["job_type"] or "fulfillment",
        created_by=old["created_by"], no_stock=old["no_stock"],
        no_stock_note=old["no_stock_note"], validate_only=old["validate_only"],
        allow_unmatched=old["allow_unmatched"], input_packslip=old["input_packslip"],
        input_order=old["input_order"], pipeline_version=settings.pipeline_version,
        source_job_id=old_job_id, reorder=old.get("reorder_list") or [],
        input_sha256=old.get("input_sha256"),
    )
    _register_inputs(settings, repo, new_job_id,
                     {storage.PACKSLIP_NAME: old["input_packslip"],
                      storage.ORDER_NAME: old["input_order"]})
    enqueue(new_job_id)
    return new_job_id
