"""Download split private pack from EN File with the caller's EN API token."""
from __future__ import annotations
import hashlib, json, os, shutil, tempfile, uuid, zipfile
from pathlib import Path
from urllib.parse import quote

import requests

DEFAULT_ENV = None
DEFAULT_BASE = "https://erpnext.vilavi.cn"


def _env(path):
    values = {}
    p = Path(path or os.environ.get("EN_API_ENV") or DEFAULT_ENV) if (path or os.environ.get("EN_API_ENV") or DEFAULT_ENV) else None
    if p and p.exists():
        for raw in p.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def token_headers(env_file=None):
    env = _env(env_file)
    key = os.environ.get("ERP_API_KEY") or env.get("ERP_API_KEY")
    secret = os.environ.get("ERP_API_SECRET") or env.get("ERP_API_SECRET")
    if not key or not secret:
        raise SystemExit("缺少 EN API Key/Secret（ERP_API_KEY / ERP_API_SECRET）")
    return {"Authorization": f"token {key}:{secret}"}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def pull(manifest, root, env_file=None, base=DEFAULT_BASE):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    header = token_headers(env_file)
    chunks = []
    for part in manifest["parts"]:
        url = base.rstrip("/") + part["file_url"]
        response = requests.get(url, headers=header, timeout=300)
        if response.status_code != 200:
            raise SystemExit(f"下载失败 {part['name']}: HTTP {response.status_code}")
        if _sha(response.content) != part["sha256"]:
            raise SystemExit(f"分卷哈希不一致：{part['name']}")
        chunks.append(response.content)
    combined = b"".join(chunks)
    if _sha(combined) != manifest["combined_sha256"]:
        raise SystemExit("合并哈希不一致，拒绝解压")
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
        handle.write(combined)
        temp = Path(handle.name)
    staging = root / (".staging-" + uuid.uuid4().hex)
    try:
        with zipfile.ZipFile(temp) as archive:
            archive.extractall(staging)
        for item in manifest["files"]:
            path = staging / item["path"]
            if not path.exists() or _sha(path.read_bytes()) != item["sha256"]:
                raise SystemExit(f"包文件校验失败：{item['path']}")
        target = root / "data"
        backup = root / "data.prev"
        moved = False
        if target.exists():
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
            moved = True
        try:
            (staging / "data").rename(target)
        except Exception:
            if moved and backup.exists() and not target.exists():
                backup.rename(target)
            raise
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        temp.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
    return root
