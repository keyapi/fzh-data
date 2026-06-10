# -*- coding: utf-8 -*-
"""DAM Prototype — FastAPI backend with SQLite + NAS storage.

启动方式:
  uv run python main.py
  uv run python main.py --port 8098
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import os
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image as PILImage
from sqlalchemy.orm import Session

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)

from models import (
    Asset, Tag, AssetProductLink, AssetCollection, AssetCollectionItem,
    AssetCollectionVersion, PlatformPreset,
    init_db, seed_presets,
)


# ── AI Background Pipeline ────────────────────────────

def _run_ai_background(asset_id: str, image_path: str, db_url: str):
    """后台线程: 调用 Qwen-VL 自动标签, 更新 DB."""
    try:
        from ai_pipeline import run_ai_pipeline

        # 在新 event loop 中跑 async pipeline
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(run_ai_pipeline(image_path))
        loop.close()

        # 写回 DB (独立 session)
        sess = init_db(db_url)
        asset = sess.query(Asset).filter_by(id=asset_id).first()
        if asset:
            asset.ai_metadata = result
            asset.ai_tags_confirmed = False
            if not result.get("error"):
                asset.compliance_status = "passed"
                asset.compliance_detail = result.get("compliance", {})
            sess.commit()
        sess.close()
    except Exception as e:
        print(f"[AI pipeline] failed for {asset_id}: {e}")


# ── .env ──────────────────────────────────────────────
def _load_dotenv() -> None:
    env_file = _DIR / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        os.environ.setdefault(k, v)

_load_dotenv()

NAS_ROOT = Path(os.getenv("DAM_NAS_ROOT", str(_DIR / "mock_storage")))
THUMB_SIZE = (300, 300)
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".pdf", ".doc", ".docx"}
DB_PATH = os.getenv("DAM_DB_PATH", str(_DIR / "dam.db"))

NAS_ROOT.mkdir(parents=True, exist_ok=True)
(NAS_ROOT / "thumbnails").mkdir(parents=True, exist_ok=True)
(NAS_ROOT / "files").mkdir(parents=True, exist_ok=True)

# ── DB ────────────────────────────────────────────────
session: Session = init_db(f"sqlite:///{DB_PATH}")
seed_presets(session)

# ── FastAPI ──────────────────────────────────────────
app = FastAPI(title="DAM Prototype", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(_DIR / "static")), name="static")
app.mount("/thumb", StaticFiles(directory=str(NAS_ROOT / "thumbnails")), name="thumb")
app.mount("/files", StaticFiles(directory=str(NAS_ROOT / "files")), name="files")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (_DIR / "static" / "index.html").read_text(encoding="utf-8")


# ── Helpers ──────────────────────────────────────────

def _guess_type(ext: str) -> str:
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}: return "image"
    if ext in {".mp4", ".mov"}: return "video"
    return "document"

def _asset_to_dict(a: Asset) -> dict[str, Any]:
    thumb_name = Path(a.thumbnail_path).name if a.thumbnail_path else None
    file_name = Path(a.stored_path).name
    return {
        "id": a.id, "filename": a.filename, "asset_type": a.asset_type,
        "file_size": a.file_size, "width": a.width, "height": a.height,
        "content_hash": a.content_hash,
        "thumb_url": f"/thumb/{thumb_name}" if thumb_name else None,
        "file_url": f"/files/{file_name}",
        "title": a.title, "alt_text": a.alt_text,
        "tags": [t.name for t in (a.tags or [])],
        "ai_tags": a.ai_metadata.get("tags") if a.ai_metadata else None,
        "ai_tags_confirmed": a.ai_tags_confirmed,
        "style": a.style, "fabric": a.fabric, "size": a.size, "color": a.color,
        "image_role": a.image_role,
        "compliance_status": a.compliance_status,
        "compliance_detail": a.compliance_detail,
        "status": a.status, "version": a.version,
        "linked_sku": a.product_links[0].product_sku if a.product_links else None,
        "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
        "uploaded_by": a.uploaded_by,
    }


# ── Asset APIs ────────────────────────────────────────

@app.get("/api/assets")
def list_assets(
    asset_type: str | None = None, tag: str | None = None,
    status: str | None = None, style: str | None = None,
    search: str | None = None,
    offset: int = 0, limit: int = 50,
):
    q = session.query(Asset)
    if asset_type: q = q.filter(Asset.asset_type == asset_type)
    if status: q = q.filter(Asset.status == status)
    if style: q = q.filter(Asset.style == style)
    if search:
        pattern = f"%{search}%"
        q = q.filter(Asset.filename.ilike(pattern) | Asset.title.ilike(pattern))
    if tag:
        q = q.join(Asset.tags).filter(Tag.name == tag)

    total = q.count()
    assets = q.order_by(Asset.uploaded_at.desc()).offset(offset).limit(limit).all()
    return {"assets": [_asset_to_dict(a) for a in assets], "total": total}


@app.get("/api/assets/{asset_id}")
def get_asset(asset_id: str):
    a = session.query(Asset).filter_by(id=asset_id).first()
    if not a: return JSONResponse({"error": "not found"}, 404)
    return _asset_to_dict(a)


@app.patch("/api/assets/{asset_id}")
async def update_asset(asset_id: str, data: dict):
    a = session.query(Asset).filter_by(id=asset_id).first()
    if not a: return JSONResponse({"error": "not found"}, 404)

    for field in ("title", "alt_text", "style", "fabric", "size", "color", "image_role", "status"):
        if field in data:
            setattr(a, field, data[field])

    if "tags" in data:
        a.tags.clear()
        for tname in data["tags"]:
            tag = session.query(Tag).filter_by(name=tname).first()
            if not tag:
                tag = Tag(name=tname, category="custom")
                session.add(tag)
            a.tags.append(tag)

    if "ai_tags_confirmed" in data and data["ai_tags_confirmed"] and a.ai_metadata:
        for tname in (a.ai_metadata.get("tags") or []):
            tag = session.query(Tag).filter_by(name=tname).first()
            if not tag:
                tag = Tag(name=tname, category="custom")
                session.add(tag)
            if tag not in a.tags:
                a.tags.append(tag)
        a.ai_tags_confirmed = True

    a.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(a)
    return _asset_to_dict(a)


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    results = []
    thumb_dir = NAS_ROOT / "thumbnails"
    store_dir = NAS_ROOT / "files"

    for f in files:
        if not f.filename: continue
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXTS: continue

        data = await f.read()
        content_hash = hashlib.sha256(data).hexdigest()

        # 去重检查
        existing = session.query(Asset).filter_by(content_hash=content_hash).first()
        if existing:
            results.append({**_asset_to_dict(existing), "_dedup": True})
            continue

        asset_id = str(uuid.uuid4())
        asset = Asset(
            id=asset_id,
            filename=f.filename, asset_type=_guess_type(ext),
            file_size=len(data), content_hash=content_hash,
            stored_path=str(store_dir / f"{asset_id}{ext}"),
            thumbnail_path=str(thumb_dir / f"{asset_id}.jpg"),
            status="draft",
        )

        # 保存源文件
        Path(asset.stored_path).write_bytes(data)

        # 生成缩略图
        try:
            img = PILImage.open(io.BytesIO(data))
            img.thumbnail(THUMB_SIZE, PILImage.LANCZOS)
            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
            asset.width, asset.height = img.size
            img.save(asset.thumbnail_path, "JPEG", quality=80)
        except Exception:
            asset.thumbnail_path = None

        session.add(asset)
        session.commit()
        results.append(_asset_to_dict(asset))

        # AI pipeline — 后台线程, 不阻塞上传响应
        if asset.asset_type == "image":
            _stored = asset.stored_path
            _aid = asset.id
            _db = f"sqlite:///{DB_PATH}"
            threading.Thread(target=_run_ai_background, args=(_aid, _stored, _db), daemon=True).start()

    return {"success": True, "assets": results}


# ── Tag APIs ──────────────────────────────────────────

@app.get("/api/tags")
def list_tags():
    tags = session.query(Tag).order_by(Tag.usage_count.desc()).all()
    return {"tags": [{"id": t.id, "name": t.name, "category": t.category, "usage_count": t.usage_count} for t in tags]}


# ── Product APIs ──────────────────────────────────────

@app.get("/api/products/search")
def search_products(q: str = Query("", min_length=1)):
    """Mock ERPNext Item 搜索 — Phase 4 对接真实 API."""
    mock = [
        {"sku": "KS0001", "name": "Memory Foam Pillow - White - Standard"},
        {"sku": "KS0002", "name": "Cooling Gel Pillow - Blue - Queen"},
        {"sku": "KS0003", "name": "PP Cotton Cushion - Gray - 45x45"},
        {"sku": "KS0004", "name": "L-Shape Sofa Cover - Beige - 3-Seater"},
        {"sku": "KS0005", "name": "Floor Pillow - Navy - Round"},
    ]
    ql = q.lower()
    return [p for p in mock if ql in p["sku"].lower() or ql in p["name"].lower()]


@app.get("/api/products/{sku}/assets")
def product_assets(sku: str):
    """查询某产品的所有可用资产 (含继承)."""
    links = session.query(AssetProductLink).filter_by(product_sku=sku).all()
    return {"assets": [_asset_to_dict(link.asset) for link in links]}


# ── Platform Presets ──────────────────────────────────

@app.get("/api/platforms/presets")
def list_presets():
    presets = session.query(PlatformPreset).all()
    return {"presets": [{"code": p.code, "label": p.label, "platform": p.platform,
        "width": p.width, "format": p.format, "quality": p.quality, "colorspace": p.colorspace} for p in presets]}


# ── AssetCollection APIs ──────────────────────────────

def _coll_to_dict(c: AssetCollection) -> dict:
    items = []
    for ci in sorted(c.items or [], key=lambda x: x.position):
        a = session.query(Asset).filter_by(id=ci.asset_id).first()
        sku = None
        if a and a.product_links:
            primary = next((pl for pl in a.product_links if pl.is_primary), None)
            sku = (primary or a.product_links[0]).product_sku
        items.append({
            "asset_id": ci.asset_id, "position": ci.position, "role": ci.role,
            "filename": a.filename if a else "",
            "thumb_url": f"/thumb/{Path(a.thumbnail_path).name}" if (a and a.thumbnail_path) else None,
            "file_url": f"/files/{Path(a.stored_path).name}" if a else None,
            "sku": sku,
        })
    return {
        "id": c.id, "name": c.name, "type": c.type,
        "context": c.context, "version": c.version, "status": c.status,
        "items": items,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "created_by": c.created_by,
    }


@app.get("/api/collections")
def list_collections(type: str | None = None, product_sku: str | None = None):
    q = session.query(AssetCollection)
    if type: q = q.filter(AssetCollection.type == type)
    if product_sku: q = q.filter(AssetCollection.context.contains(product_sku))
    cols = q.order_by(AssetCollection.updated_at.desc()).limit(50).all()
    return {"collections": [_coll_to_dict(c) for c in cols]}


@app.get("/api/collections/{coll_id}")
def get_collection(coll_id: str):
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c: return JSONResponse({"error": "not found"}, 404)
    return _coll_to_dict(c)


@app.post("/api/collections")
def create_collection(data: dict):
    c = AssetCollection(
        name=data.get("name", "Untitled"),
        type=data.get("type", "custom"),
        context=data.get("context", {}),
        version=1, status="draft",
        created_by=data.get("created_by"),
    )
    session.add(c)
    session.commit(); session.refresh(c)
    return _coll_to_dict(c)


@app.put("/api/collections/{coll_id}")
def update_collection(coll_id: str, data: dict):
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c: return JSONResponse({"error": "not found"}, 404)

    # Snapshot current items before changing
    old_items = [{"asset_id": ci.asset_id, "position": ci.position, "role": ci.role}
                 for ci in sorted(c.items, key=lambda x: x.position)]
    if old_items:
        snap = AssetCollectionVersion(
            collection_id=c.id, version=c.version,
            snapshot={"images": old_items},
            created_by=data.get("updated_by"),
        )
        session.add(snap)

    if "name" in data: c.name = data["name"]
    if "type" in data: c.type = data["type"]
    if "context" in data: c.context = data["context"]
    if "status" in data: c.status = data["status"]

    if "images" in data:
        for old in list(c.items): session.delete(old)
        session.flush()
        for img in data["images"]:
            session.add(AssetCollectionItem(
                collection_id=c.id, asset_id=img["asset_id"],
                position=img["position"], role=img.get("role", "alternate"),
            ))

    c.version += 1
    c.updated_at = datetime.now(timezone.utc)
    session.commit(); session.refresh(c)
    return _coll_to_dict(c)


@app.patch("/api/collections/{coll_id}/items")
def update_collection_items(coll_id: str, data: dict):
    """Incremental collection item updates — add, remove, reorder, set_role.

    Body:
      {
        "add": [{"asset_id": "uuid", "position": 3, "role": "alternate"}, ...],
        "remove": ["asset_id_1", "asset_id_2", ...],
        "reorder": [{"asset_id": "uuid", "position": 0}, ...],
        "set_role": [{"asset_id": "uuid", "role": "main"}, ...]
      }
    """
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, 404)

    # Snapshot before mutation
    old_items = [{"asset_id": ci.asset_id, "position": ci.position, "role": ci.role}
                 for ci in sorted(c.items, key=lambda x: x.position)]
    if old_items:
        snap = AssetCollectionVersion(
            collection_id=c.id, version=c.version,
            snapshot={"images": old_items},
            created_by=data.get("updated_by"),
        )
        session.add(snap)

    # Apply removals
    if "remove" in data:
        for aid in data["remove"]:
            for ci in list(c.items):
                if ci.asset_id == aid:
                    session.delete(ci)

    # Apply additions
    if "add" in data:
        for img in data["add"]:
            session.add(AssetCollectionItem(
                collection_id=c.id,
                asset_id=img["asset_id"],
                position=img.get("position", 0),
                role=img.get("role", "alternate"),
            ))

    session.flush()

    # Apply reorder
    if "reorder" in data:
        pos_map = {r["asset_id"]: r["position"] for r in data["reorder"]}
        for ci in c.items:
            if ci.asset_id in pos_map:
                ci.position = pos_map[ci.asset_id]

    # Apply role changes
    if "set_role" in data:
        role_map = {r["asset_id"]: r["role"] for r in data["set_role"]}
        for ci in c.items:
            if ci.asset_id in role_map:
                ci.role = role_map[ci.asset_id]

    c.version += 1
    c.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(c)
    return _coll_to_dict(c)


@app.get("/api/collections/{coll_id}/versions")
def get_collection_versions(coll_id: str):
    vs = session.query(AssetCollectionVersion)\
        .filter_by(collection_id=coll_id)\
        .order_by(AssetCollectionVersion.version.desc()).all()
    return {"versions": [
        {"id": v.id, "version": v.version, "snapshot": v.snapshot,
         "created_at": v.created_at.isoformat() if v.created_at else None}
        for v in vs
    ]}


@app.get("/api/collections/{coll_id}/export")
def export_collection(coll_id: str, platform: str = "amazon"):
    from export import export_collection_to_excel
    try:
        data = export_collection_to_excel(session, coll_id, platform)
        return Response(content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=listing-{platform}-{coll_id[:8]}.xlsx"})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 404)


# ── Health ────────────────────────────────────────────

@app.get("/api/ping")
async def ping():
    from sqlalchemy import text
    session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected", "nas_root": str(NAS_ROOT),
            "asset_count": session.query(Asset).count()}


# ── 启动 ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}")

    print(f"\n  DAM running at http://127.0.0.1:{args.port}\n  DB: {DB_PATH}\n  Storage: {NAS_ROOT}\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
