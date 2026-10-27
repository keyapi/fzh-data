#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB 订单处理 JSON API v1：检查 → 出件，供人与 Agent 共用。"""

from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from web import jobs_service, storage
from web.api_auth import Principal, authenticate_bearer, require_scope
from web.api_errors import ApiError
from web.config import Settings
from web.repository import ARTIFACT_LABELS, NO_STOCK_KEY, Repository

UrlFn = Callable[[str], str]


class NoStockUpdate(BaseModel):
    no_stock: str = ""


def _artifact_view(a: dict, url: UrlFn) -> dict:
    return {
        "id": a["id"],
        "kind": a["kind"],
        "label": ARTIFACT_LABELS.get(a["kind"], a["kind"]),
        "download_name": a["download_name"],
        "size_bytes": a["size_bytes"],
        "content_hash": a["content_hash"],
        "download_url": url(f"/api/v1/artifacts/{a['id']}/download"),
    }


def _job_view(job: dict, repo: Repository, url: UrlFn, deduplicated: bool = False) -> dict:
    data = {
        "id": job["id"],
        "job_type": job["job_type"],
        "status": job["status"],
        "created_by": job["created_by"],
        "created_at": job["created_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "progress_step": job.get("progress_step"),
        "progress_message": job.get("progress_message"),
        "no_stock": job.get("no_stock", ""),
        "no_stock_note": job.get("no_stock_note"),
        "input_packslip": job.get("input_packslip", ""),
        "input_order": job.get("input_order", ""),
        "source_job_id": job.get("source_job_id"),
        "reorder": job.get("reorder_list") or [],
        "report": job.get("report"),
        "error": job.get("error"),
        "artifacts": [_artifact_view(a, url) for a in repo.list_artifacts(job["id"])],
    }
    if deduplicated:
        data["deduplicated"] = True
    return data


def _json_form(raw: str) -> dict[str, str]:
    if not (raw or "").strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(422, "invalid_input", f"reorder_map 不是合法 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ApiError(422, "invalid_input", "reorder_map 必须是 {PO: '-N'} 对象")
    return {str(k): str(v) for k, v in value.items()}


def build_api_router(settings: Settings, repo: Repository, enqueue: Callable[[str], None], url: UrlFn) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["pb"])

    async def principal_dep(request: Request) -> Principal:
        return await authenticate_bearer(request, settings, repo)

    def _idem_lookup(principal: Principal, operation: str, key: str | None, fingerprint: str) -> dict | None:
        if not key:
            return None
        row = repo.lookup_idempotency(principal.identity, operation, key)
        if row is None:
            return None
        if row["request_sha256"] != fingerprint:
            raise ApiError(409, "idempotency_conflict", "同一 Idempotency-Key 使用了不同输入")
        return json.loads(row["response_json"] or "{}")

    def _idem_store(principal: Principal, operation: str, key: str | None,
                    fingerprint: str, job_id: str, body: dict) -> None:
        if not key:
            return
        repo.store_idempotency(
            principal.identity, operation, key, fingerprint, job_id,
            json.dumps(body, ensure_ascii=False), settings.idempotency_ttl_minutes,
        )

    def _created(job_id: str, body: dict) -> JSONResponse:
        return JSONResponse(body, status_code=202, headers={"Location": url(f"/api/v1/jobs/{job_id}")})

    @router.get("/healthz")
    async def api_healthz():
        return {"status": "ok"}

    @router.post("/checks")
    async def create_check_api(
        raw_csv: UploadFile = File(...),
        no_stock: str = Form(""),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: Principal = Depends(principal_dep),
    ):
        require_scope(principal, "check")
        order_hash = jobs_service.hash_upload(raw_csv)
        fingerprint = jobs_service.make_fingerprint("stock_check", no_stock, "", [order_hash])
        replay = _idem_lookup(principal, "checks", idempotency_key, fingerprint)
        if replay:
            return JSONResponse(replay, status_code=200, headers={"Idempotent-Replayed": "true"})
        existing = repo.find_recent_job(fingerprint, settings.dedupe_minutes)
        if existing:
            job = repo.get_job(existing)
            return JSONResponse(_job_view(job, repo, url, deduplicated=True), status_code=200)
        try:
            job_id = jobs_service.create_stock_check_job(
                settings, repo, raw_csv, principal.display_name, no_stock, enqueue,
            )
        except jobs_service.JobServiceError as exc:
            raise ApiError(exc.status_code, exc.code, exc.message, exc.hint) from exc
        body = _job_view(repo.get_job(job_id), repo, url)
        _idem_store(principal, "checks", idempotency_key, fingerprint, job_id, body)
        return _created(job_id, body)

    @router.post("/jobs")
    async def create_job_api(
        order_csv: UploadFile = File(...),
        packslip: UploadFile = File(...),
        no_stock: str = Form(""),
        no_stock_note: str = Form(""),
        reorder: str = Form(""),
        reorder_map: str = Form(""),
        validate_only: bool = Form(False),
        allow_unmatched: bool = Form(False),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: Principal = Depends(principal_dep),
    ):
        require_scope(principal, "fulfill")
        order_hash = jobs_service.hash_upload(order_csv)
        pdf_hash = jobs_service.hash_upload(packslip)
        rmap = _json_form(reorder_map)
        sig = reorder + "|" + json.dumps(rmap, ensure_ascii=False, sort_keys=True)
        fingerprint = jobs_service.make_fingerprint("fulfillment", no_stock, sig, [order_hash, pdf_hash])
        replay = _idem_lookup(principal, "jobs", idempotency_key, fingerprint)
        if replay:
            return JSONResponse(replay, status_code=200, headers={"Idempotent-Replayed": "true"})
        existing = repo.find_recent_job(fingerprint, settings.dedupe_minutes)
        if existing:
            job = repo.get_job(existing)
            return JSONResponse(_job_view(job, repo, url, deduplicated=True), status_code=200)
        try:
            job_id, _ = jobs_service.create_fulfillment_job(
                settings, repo, order_csv, packslip, principal.display_name,
                no_stock, no_stock_note, validate_only, allow_unmatched,
                reorder, rmap, enqueue,
            )
        except jobs_service.JobServiceError as exc:
            raise ApiError(exc.status_code, exc.code, exc.message, exc.hint) from exc
        body = _job_view(repo.get_job(job_id), repo, url)
        _idem_store(principal, "jobs", idempotency_key, fingerprint, job_id, body)
        return _created(job_id, body)

    @router.post("/jobs/{check_job_id}/fulfill")
    async def fulfill_from_check_api(
        check_job_id: str,
        packslip: UploadFile = File(...),
        reorder: str = Form(""),
        reorder_map: str = Form(""),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        principal: Principal = Depends(principal_dep),
    ):
        require_scope(principal, "fulfill")
        checked = jobs_service.checked_artifact(repo, check_job_id)
        if checked is None:
            raise ApiError(409, "conflict_state", "来源任务的 checked CSV 不可用",
                           hint="先等库存预检成功，或重新跑一次。")
        pdf_hash = jobs_service.hash_upload(packslip)
        rmap = _json_form(reorder_map)
        sig = reorder + "|" + json.dumps(rmap, ensure_ascii=False, sort_keys=True)
        fingerprint = jobs_service.make_fingerprint(
            "fulfillment-from-check", "", sig, [pdf_hash, checked["content_hash"]]
        )
        replay = _idem_lookup(principal, "fulfill", idempotency_key, fingerprint)
        if replay:
            return JSONResponse(replay, status_code=200, headers={"Idempotent-Replayed": "true"})
        existing = repo.find_recent_job(fingerprint, settings.dedupe_minutes)
        if existing:
            job = repo.get_job(existing)
            return JSONResponse(_job_view(job, repo, url, deduplicated=True), status_code=200)
        try:
            job_id, _ = jobs_service.create_fulfillment_from_check(
                settings, repo, check_job_id, packslip, principal.display_name,
                reorder, rmap, enqueue,
            )
        except jobs_service.JobServiceError as exc:
            raise ApiError(exc.status_code, exc.code, exc.message, exc.hint) from exc
        body = _job_view(repo.get_job(job_id), repo, url)
        _idem_store(principal, "fulfill", idempotency_key, fingerprint, job_id, body)
        return _created(job_id, body)

    @router.get("/jobs/{job_id}")
    async def get_job_api(job_id: str, principal: Principal = Depends(principal_dep)):
        require_scope(principal, "read")
        job = repo.get_job(job_id)
        if job is None:
            raise ApiError(404, "not_found", "任务不存在")
        return _job_view(job, repo, url)

    @router.get("/jobs/{job_id}/artifacts")
    async def list_artifacts_api(job_id: str, principal: Principal = Depends(principal_dep)):
        require_scope(principal, "read")
        if repo.get_job(job_id) is None:
            raise ApiError(404, "not_found", "任务不存在")
        return {"job_id": job_id,
                "artifacts": [_artifact_view(a, url) for a in repo.list_artifacts(job_id)]}

    @router.get("/artifacts/{artifact_id}/download")
    async def download_api(artifact_id: str, principal: Principal = Depends(principal_dep)):
        require_scope(principal, "read")
        art = repo.get_artifact(artifact_id)
        if art is None:
            raise ApiError(404, "not_found", "产物不存在")
        try:
            path = storage.resolve_artifact_path(settings.artifacts_dir, art["rel_path"])
        except storage.StoredPathError as exc:
            raise ApiError(404, "not_found", str(exc)) from exc
        return FileResponse(path, media_type=art["mime_type"], filename=art["download_name"])

    @router.post("/jobs/{job_id}/retry")
    async def retry_api(job_id: str, principal: Principal = Depends(principal_dep)):
        job = repo.get_job(job_id)
        if job is None:
            raise ApiError(404, "not_found", "任务不存在")
        require_scope(principal, "check" if job["job_type"] == "stock_check" else "fulfill")
        try:
            new_job_id = jobs_service.retry_job(settings, repo, job_id, enqueue)
        except jobs_service.JobServiceError as exc:
            raise ApiError(exc.status_code, exc.code, exc.message, exc.hint) from exc
        body = _job_view(repo.get_job(new_job_id), repo, url)
        return _created(new_job_id, body)

    @router.get("/settings/no-stock")
    async def get_no_stock_api(principal: Principal = Depends(principal_dep)):
        require_scope(principal, "read")
        stored = repo.get_setting(NO_STOCK_KEY)
        return {
            "no_stock": jobs_service.current_no_stock(settings, repo),
            "env_default": ",".join(settings.default_no_stock),
            "updated_at": (stored or {}).get("updated_at", ""),
            "updated_by": (stored or {}).get("updated_by", ""),
        }

    @router.put("/settings/no-stock")
    async def put_no_stock_api(
        payload: NoStockUpdate = Body(...),
        principal: Principal = Depends(principal_dep),
    ):
        require_scope(principal, "check")
        value = ",".join(jobs_service.parse_sku_list(payload.no_stock))
        repo.set_setting(NO_STOCK_KEY, value, principal.display_name)
        return {"no_stock": value, "updated_by": principal.display_name}

    return router
