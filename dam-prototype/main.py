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

# ── ERPNext Client ────────────────────────────────────
from requests.adapters import HTTPAdapter

class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    """Lightweight ERPNext REST API client (pattern from EN_API)."""
    def __init__(self, base_url, api_key, api_secret):
        self.base_url = base_url.rstrip("/")
        self.session = __import__("requests").Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def search_items(self, query: str, limit=20):
        url = f"{self.base_url}/api/method/frappe.client.get_list"
        body = {
            "doctype": "Item",
            "fields": ["item_code", "item_name"],
            "or_filters": [
                ["item_code", "like", f"%{query}%"],
                ["item_name", "like", f"%{query}%"],
            ],
            "limit_page_length": limit,
        }
        resp = self.session.post(url, json=body, timeout=(30, 60))
        resp.raise_for_status()
        data = resp.json().get("message", [])
        return [{"sku": r["item_code"], "name": r["item_name"]} for r in data[:limit]]


ERP_URL = os.getenv("ERP_URL", "")
ERP_API_KEY = os.getenv("ERP_API_KEY", "")
ERP_API_SECRET = os.getenv("ERP_API_SECRET", "")
_erp = ErpnextClient(ERP_URL, ERP_API_KEY, ERP_API_SECRET) if ERP_URL else None

NAS_ROOT = Path(os.getenv("DAM_NAS_ROOT", str(_DIR / "mock_storage")))

# ── Synology NAS Client (adapted from vilavi_pim) ─────

NAS_URL = os.getenv("NAS_URL", "")
NAS_USERNAME = os.getenv("NAS_USERNAME", "")
NAS_PASSWORD = os.getenv("NAS_PASSWORD", "")
NAS_ROOT_FOLDER = os.getenv("NAS_ROOT_FOLDER", "/FZH共享文件夹")


class SynologyNAS:
    """Synology FileStation API client (pattern from vilavi_pim)."""
    def __init__(self):
        self.base_url = NAS_URL.rstrip("/") if NAS_URL else ""
        self.username = NAS_USERNAME
        self.password = NAS_PASSWORD
        self.root_folder = NAS_ROOT_FOLDER
        self.sid = None
        if self.base_url:
            self._login()

    def _login(self):
        try:
            resp = __import__("requests").get(
                f"{self.base_url}/webapi/auth.cgi",
                params={
                    "api": "SYNO.API.Auth", "version": "3", "method": "login",
                    "account": self.username, "passwd": self.password,
                    "session": "FileStation", "format": "sid",
                },
                timeout=10, verify=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    self.sid = data["data"]["sid"]
        except Exception as e:
            print(f"[nas] login failed: {e}")

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.sid)

    def get_file_list(self, folder_path: str = "", limit: int = 1000, offset: int = 0) -> list[dict]:
        if not self.sid:
            return []
        try:
            resp = __import__("requests").get(
                f"{self.base_url}/webapi/entry.cgi",
                params={
                    "api": "SYNO.FileStation.List", "version": "2", "method": "list",
                    "folder_path": folder_path or self.root_folder,
                    "offset": offset, "limit": limit,
                    "sort_by": "name", "sort_direction": "asc",
                    "additional": "thumbnail,size,time",
                    "_sid": self.sid,
                },
                timeout=20, verify=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return [
                        {
                            "name": f.get("name"),
                            "path": f.get("path"),
                            "is_dir": f.get("isdir", False),
                            "size": f.get("additional", {}).get("size", 0),
                            "mtime": f.get("additional", {}).get("time", {}).get("mtime", 0),
                            "has_thumbnail": "thumbnail" in f.get("additional", {}),
                        }
                        for f in data["data"]["files"]
                    ]
        except Exception as e:
            print(f"[nas] list error: {e}")
        return []

    def get_thumbnail(self, path: str, size: str = "medium") -> tuple[bytes | None, str | None]:
        if not self.sid:
            return None, None
        try:
            resp = __import__("requests").get(
                f"{self.base_url}/webapi/entry.cgi",
                params={
                    "api": "SYNO.FileStation.Thumb", "version": "2", "method": "get",
                    "path": path, "size": size, "_sid": self.sid,
                },
                timeout=15, verify=False, stream=True,
            )
            if resp.status_code == 200:
                return resp.content, resp.headers.get("Content-Type")
        except Exception as e:
            print(f"[nas] thumbnail error: {e}")
        return None, None


_nas = SynologyNAS() if NAS_URL else None

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

def _file_rel(sp: str) -> str:
    """从 stored_path 提取 files/ 后的相对路径。"""
    s = sp.replace("\\", "/")
    return s.split("/files/", 1)[1] if "/files/" in s else (Path(s).name if s else "")


def _asset_to_dict(a: Asset) -> dict[str, Any]:
    thumb_name = Path(a.thumbnail_path).name if a.thumbnail_path else None
    rel = _file_rel(a.stored_path) if a.stored_path else ""
    return {
        "id": a.id, "filename": a.filename, "asset_type": a.asset_type,
        "file_size": a.file_size, "width": a.width, "height": a.height,
        "content_hash": a.content_hash,
        "thumb_url": f"/thumb/{thumb_name}" if thumb_name else None,
        "file_url": f"/files/{rel}" if rel else None,
        "title": a.title, "alt_text": a.alt_text,
        "tags": [t.name for t in (a.tags or [])],
        "ai_tags": a.ai_metadata.get("tags") if a.ai_metadata else None,
        "ai_tags_confirmed": a.ai_tags_confirmed,
        "style": a.style, "fabric": a.fabric, "size": a.size, "color": a.color,
        "image_role": a.image_role,
        "compliance_status": a.compliance_status,
        "compliance_detail": a.compliance_detail,
        "status": a.status, "version": a.version,
        "linked_skus": [pl.product_sku for pl in (a.product_links or [])],
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

        if "linked_skus" in data:
            new_skus = set(data["linked_skus"])
            existing = {pl.product_sku: pl for pl in a.product_links}
            for sku, pl in list(existing.items()):
                if sku not in new_skus:
                    session.delete(pl)
            for sku in new_skus:
                if sku not in existing:
                    session.add(AssetProductLink(
                        asset_id=a.id, product_sku=sku,
                        match_level="exact", is_primary=False
                    ))

    a.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(a)
    return _asset_to_dict(a)


def _create_asset_from_bytes(data: bytes, filename: str, rel_dir: str = "") -> dict:
    """Create an Asset record from file bytes. Returns _asset_to_dict result.

    If rel_dir is provided, files are stored under files/{rel_dir}/{uuid}{ext}
    preserving the original directory structure.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return None
    content_hash = hashlib.sha256(data).hexdigest()

    # 去重（但保留目录结构：相同内容放不同文件夹时复制文件）
    existing = session.query(Asset).filter_by(content_hash=content_hash).first()
    if existing and not rel_dir:
        return {**_asset_to_dict(existing), "_dedup": True}

    asset_id = str(uuid.uuid4())
    thumb_dir = NAS_ROOT / "thumbnails"
    store_dir = NAS_ROOT / "files"

    # 保留目录结构: files/{rel_dir}/{uuid}{ext}
    if rel_dir:
        rel_dir = rel_dir.replace("\\", "/").strip("/")
        store_subdir = store_dir / rel_dir
        store_subdir.mkdir(parents=True, exist_ok=True)
        stored_path = str(store_subdir / f"{asset_id}{ext}")
    else:
        stored_path = str(store_dir / f"{asset_id}{ext}")

    asset = Asset(
        id=asset_id,
        filename=filename, asset_type=_guess_type(ext),
        file_size=len(data), content_hash=content_hash,
        stored_path=stored_path,
        thumbnail_path=str(thumb_dir / f"{asset_id}.jpg"),
        status="draft",
    )

    Path(asset.stored_path).write_bytes(data)

    # 缩略图
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
    result = _asset_to_dict(asset)

    # AI pipeline — 后台
    if asset.asset_type == "image":
        _stored = asset.stored_path
        _aid = asset.id
        _db = f"sqlite:///{DB_PATH}"
        threading.Thread(target=_run_ai_background, args=(_aid, _stored, _db), daemon=True).start()

    return result


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    """上传文件。支持单文件和文件夹（通过 webkitRelativePath 保留目录结构）。

    前端用 webkitdirectory 或 webkitGetAsEntry 获取文件时，
    FormData 第3参数传入 file.webkitRelativePath，
    后端从 filename 中提取目录路径和文件名，
    在 NAS 上重建 files/{目录}/{uuid}.{ext} 结构。
    """
    results = []
    folders = set()
    for f in files:
        if not f.filename: continue
        # 从 webkitRelativePath 提取目录路径
        fname = f.filename.replace("\\", "/")
        if "/" in fname:
            rel_dir = "/".join(fname.split("/")[:-1])
            base_name = fname.split("/")[-1]
            if rel_dir:
                folders.add(rel_dir)
        else:
            rel_dir = ""
            base_name = fname
        data = await f.read()
        r = _create_asset_from_bytes(data, base_name, rel_dir)
        if r:
            results.append(r)
    return {
        "success": True,
        "assets": results,
        "folders": sorted(folders),
        "total": len(results),
    }


# ── Folder APIs ──────────────────────────────────────

@app.get("/api/folders")
def list_folders():
    """列出所有文件夹（从 stored_path 提取唯一目录），含资产计数。"""
    assets = session.query(Asset.stored_path).filter(
        Asset.stored_path.isnot(None)
    ).all()
    folder_counts: dict[str, int] = {}
    for (sp,) in assets:
        rel = sp.replace("\\", "/")
        # 从路径中提取 files/ 后面的相对目录部分
        marker = "/files/"
        if marker in rel:
            rel = rel.split(marker, 1)[1]
        if "/" in rel:
            # 逐层计入父文件夹
            parts = rel.split("/")[:-1]
            for i in range(len(parts)):
                key = "/".join(parts[:i + 1])
                folder_counts[key] = folder_counts.get(key, 0) + 1
    folders = [{"path": k, "asset_count": v} for k, v in sorted(folder_counts.items())]
    return {"folders": folders}


def _file_rel(sp: str) -> str:
    """从 stored_path 提取 files/ 后的相对目录+文件名。"""
    rel = sp.replace("\\", "/")
    marker = "/files/"
    return rel.split(marker, 1)[1] if marker in rel else rel


@app.get("/api/folders/{path:path}/assets")
def folder_assets(path: str, limit: int = 200):
    """列出某文件夹下的资产。"""
    norm = path.replace("\\", "/").strip("/")
    results = []
    for a in session.query(Asset).filter(
        Asset.stored_path.isnot(None)
    ).all():
        rel = _file_rel(a.stored_path)
        dir_part = "/".join(rel.split("/")[:-1])
        if dir_part == norm:
            results.append(_asset_to_dict(a))
            if len(results) >= limit:
                break
    return {"folder": norm, "assets": results}


@app.get("/api/folders/{path:path}/thumbnail")
def folder_thumbnail(path: str):
    """生成文件夹拼贴缩略图（前 4 张图片拼成 2×2 网格）。"""
    norm = path.replace("\\", "/").strip("/")
    thumbs = []
    for a in session.query(Asset).filter(
        Asset.stored_path.isnot(None), Asset.thumbnail_path.isnot(None)
    ).all():
        rel = _file_rel(a.stored_path)
        dir_part = "/".join(rel.split("/")[:-1])
        if dir_part == norm:
            thumbs.append(a.thumbnail_path)
            if len(thumbs) >= 4:
                break
    if not thumbs:
        return Response(status_code=404)

    cell = 150  # 每格尺寸
    cols = min(len(thumbs), 2)
    rows = (len(thumbs) + 1) // 2
    canvas = PILImage.new("RGB", (cell * 2, cell * 2), (240, 240, 240))

    for idx, tp in enumerate(thumbs):
        try:
            img = PILImage.open(tp)
            img.thumbnail((cell, cell), PILImage.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            row, col = idx // 2, idx % 2
            x, y = col * cell + (cell - img.width) // 2, row * cell + (cell - img.height) // 2
            canvas.paste(img, (x, y))
        except Exception:
            pass

    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=75)
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/jpeg")


# ── NAS Browse APIs ──────────────────────────────────

def _local_browse(path: str) -> list[dict]:
    """本地文件系统浏览（NAS 不可用时的 fallback）。"""
    norm = path.replace("\\", "/").strip("/")
    target = (NAS_ROOT / norm).resolve() if norm else NAS_ROOT.resolve()
    if not str(target).startswith(str(NAS_ROOT.resolve())):
        return []
    if not target.exists():
        return []
    entries = []
    for p in sorted(target.iterdir()):
        name = p.name
        if name.startswith(".") or name.startswith("__MACOSX"):
            continue
        rel = str(p.relative_to(NAS_ROOT)).replace("\\", "/")
        if p.is_dir():
            img_count = 0
            try:
                for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                    img_count += len(list(p.rglob(f"*{ext}")))
            except Exception:
                pass
            entries.append({"type": "directory", "name": name, "path": rel, "image_count": img_count})
        elif p.suffix.lower() in ALLOWED_EXTS:
            entries.append({"type": "file", "name": name, "path": rel, "ext": p.suffix.lower(), "size": p.stat().st_size})
    return entries


@app.get("/api/nas/browse")
def nas_browse(path: str = Query("", description="NAS folder path")):
    """列出 NAS 目录内容。优先使用 Synology NAS API，不可用时回退本地文件系统。"""
    # 1) Real NAS via Synology FileStation API
    if _nas and _nas.available:
        raw = _nas.get_file_list(path, limit=500)
        entries = [
            {
                "type": "directory" if e["is_dir"] else "file",
                "name": e["name"],
                "path": e["path"],
                "image_count": 0 if not e["is_dir"] else -1,  # -1 = unknown (NAS doesn't pre-count)
                "has_thumbnail": e.get("has_thumbnail", False),
            }
            for e in raw
        ]
        return {"path": path or _nas.root_folder, "entries": entries, "source": "nas"}

    # 2) Fallback: local filesystem
    entries = _local_browse(path)
    return {"path": path or "", "entries": entries, "source": "local"}


@app.get("/api/nas/tree")
def nas_tree(path: str = Query("", description="NAS folder path for tree")):
    """返回仅目录列表，含 has_children 标志，用于树状视图。"""
    entries = []
    if _nas and _nas.available:
        raw = _nas.get_file_list(path, limit=500)
        dirs = [e for e in raw if e.get("is_dir")]
        for d in dirs:
            subs = _nas.get_file_list(d["path"], limit=1)
            d["has_children"] = any(s.get("is_dir") for s in subs)
        entries = [
            {"name": e["name"], "path": e["path"], "has_children": e.get("has_children", False)}
            for e in dirs
        ]
    else:
        all_entries = _local_browse(path)
        dirs = [e for e in all_entries if e["type"] == "directory"]
        for d in dirs:
            subs = _local_browse(d["path"])
            d["has_children"] = any(s["type"] == "directory" for s in subs)
        entries = [{"name": d["name"], "path": d["path"], "has_children": d.get("has_children", False)} for d in dirs]
    return {"entries": entries}


@app.get("/api/nas/thumbnail")
def nas_thumbnail(path: str = Query(..., description="File path for thumbnail")):
    """获取 NAS 文件缩略图。优先 Synology NAS，fallback 本地 Pillow 生成。"""
    # Real NAS: use Synology thumbnail API
    if _nas and _nas.available:
        content, content_type = _nas.get_thumbnail(path, size="medium")
        if content:
            return Response(content=content, media_type=content_type or "image/jpeg")
        return Response(status_code=404)

    # Fallback: local Pillow
    norm = path.replace("\\", "/").strip("/")
    target = (NAS_ROOT / norm).resolve()
    if not str(target).startswith(str(NAS_ROOT.resolve())):
        return Response(status_code=403)
    if not target.is_file():
        return Response(status_code=404)
    try:
        img = PILImage.open(target)
        img.thumbnail(THUMB_SIZE, PILImage.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/jpeg")
    except Exception:
        return Response(status_code=415)


@app.post("/api/nas/import")
def nas_import(body: dict):
    """将 NAS 文件导入 DAM。支持真实 NAS 和本地路径。"""
    paths = body.get("paths", [])
    if not paths:
        return {"success": False, "error": "No paths provided", "assets": []}
    results = []
    for rel_path in paths:
        norm = rel_path.replace("\\", "/").strip("/")
        # Real NAS: download file bytes via Synology
        if _nas and _nas.available:
            # Use thumbnail as proxy to get file content (or we'd need a download API)
            # For now, real NAS import requires a separate file download endpoint
            # Fall through to local for now
            target = (NAS_ROOT / norm).resolve()
            if not target.is_file():
                continue
        else:
            target = (NAS_ROOT / norm).resolve()
            if not str(target).startswith(str(NAS_ROOT.resolve())):
                continue
            if not target.is_file():
                continue
        if target.suffix.lower() not in ALLOWED_EXTS:
            continue
        data = target.read_bytes()
        parts = norm.split("/")
        rel_dir = "/".join(parts[:-1]) if len(parts) > 1 else ""
        r = _create_asset_from_bytes(data, target.name, rel_dir)
        if r:
            results.append(r)
    return {"success": True, "assets": results, "total": len(results)}


# ── Tag APIs ──────────────────────────────────────────

@app.get("/api/tags")
def list_tags():
    tags = session.query(Tag).order_by(Tag.usage_count.desc()).all()
    return {"tags": [{"id": t.id, "name": t.name, "category": t.category, "usage_count": t.usage_count} for t in tags]}


# ── Product APIs ──────────────────────────────────────

@app.get("/api/products/search")
def search_products(q: str = Query("", min_length=1)):
    """Search ERPNext Items by item_code or item_name."""
    if not _erp:
        return []
    try:
        return _erp.search_items(q)
    except Exception as e:
        print(f"[erp] search failed: {e}")
        return []


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
            "file_url": f"/files/{_file_rel(a.stored_path)}" if a else None,
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


@app.post("/api/collections/{coll_id}/versions/{v}/restore")
def restore_version(coll_id: str, v: int):
    """Non-destructive restore: snapshots current state, then rebuilds from version snapshot."""
    c = session.query(AssetCollection).filter_by(id=coll_id).first()
    if not c:
        return JSONResponse({"error": "not found"}, 404)

    ver = session.query(AssetCollectionVersion)\
        .filter_by(collection_id=coll_id, version=v).first()
    if not ver:
        return JSONResponse({"error": "version not found"}, 404)

    # Non-destructive: snapshot current state first (Figma pattern)
    current_items = [{"asset_id": ci.asset_id, "position": ci.position, "role": ci.role}
                     for ci in sorted(c.items, key=lambda x: x.position)]
    if current_items:
        session.add(AssetCollectionVersion(
            collection_id=c.id, version=c.version,
            snapshot={"images": current_items},
        ))

    # Wipe current items and rebuild from snapshot
    for old in list(c.items):
        session.delete(old)
    session.flush()
    for img in ver.snapshot.get("images", []):
        session.add(AssetCollectionItem(
            collection_id=c.id,
            asset_id=img["asset_id"],
            position=img["position"],
            role=img.get("role", "alternate"),
        ))

    c.version += 1
    c.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(c)
    return _coll_to_dict(c)


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
