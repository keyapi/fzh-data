"""拉取 EN 私有历史 parquet（订单/需求），校验 sha256 后落到本地 FZH_DATA_ROOT。

不拉全量 EN 表：历史快照由运维增量生成后放在 EN private/supply-history/<version>/，
这里只做受控下载。决策回放不需要历史；只有重训预测/复核明细时才需要。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote

import requests

from .download import DEFAULT_BASE, token_headers

DEFAULT_METHOD = "key_test.demand_collaboration.history_download.get"
MANIFEST = Path(__file__).with_name("history_manifest.json")
ORDERS_MANIFEST = Path(__file__).with_name("orders_manifest.json")


def _url(base, method, version, name):
    return (f"{base.rstrip('/')}/api/method/{method}"
            f"?version={quote(version)}&name={quote(name)}")


def load_manifest(path: Path | None = None) -> dict:
    return json.loads(Path(path or MANIFEST).read_text(encoding="utf-8"))


def history_dir(root: Path, version: str) -> Path:
    return Path(root) / "history" / version


def orders_dir(root: Path, version: str) -> Path:
    return Path(root) / "orders" / version


def _status_for(root: Path, manifest: dict, dirname: str) -> dict:
    version = manifest["version"]
    target = (orders_dir if dirname == "orders" else history_dir)(Path(root), version)
    missing, bad = [], []
    for item in manifest["files"]:
        p = target / item["name"]
        if not p.exists():
            missing.append(item["name"])
        elif hashlib.sha256(p.read_bytes()).hexdigest() != item["sha256"]:
            bad.append(item["name"])
    return {"version": version, "as_of": manifest.get("as_of"),
            "dir": str(target), "files": len(manifest["files"]),
            "missing": missing, "sha_mismatch": bad,
            "status": "ok" if not missing and not bad else "incomplete"}


def status(root: Path, manifest: dict | None = None) -> dict:
    manifest = manifest or load_manifest()
    version = manifest["version"]
    target = history_dir(Path(root), version)
    missing, bad = [], []
    for item in manifest["files"]:
        p = target / item["name"]
        if not p.exists():
            missing.append(item["name"])
        elif hashlib.sha256(p.read_bytes()).hexdigest() != item["sha256"]:
            bad.append(item["name"])
    return {"version": version, "as_of": manifest.get("as_of"),
            "dir": str(target), "files": len(manifest["files"]),
            "missing": missing, "sha_mismatch": bad,
            "status": "ok" if not missing and not bad else "incomplete"}


def _sync(manifest: dict, target: Path, version: str, env_file, base: str,
          names: list[str] | None) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    header = token_headers(env_file)
    method = os.environ.get("FZH_HISTORY_METHOD") or DEFAULT_METHOD
    wanted = set(names) if names else None
    downloaded = []
    for item in manifest["files"]:
        if wanted is not None and item["name"] not in wanted:
            continue
        dest = target / item["name"]
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == item["sha256"]:
            continue
        url = _url(base, method, version, item["name"])
        response = requests.get(url, headers=header, timeout=600)
        if response.status_code == 403:
            raise SystemExit("下载被拒（403）：请使用自己的 EN 内部账号 API Key/Secret。")
        if response.status_code != 200:
            raise SystemExit(f"下载失败 {item['name']}: HTTP {response.status_code}")
        if hashlib.sha256(response.content).hexdigest() != item["sha256"]:
            raise SystemExit(f"哈希不一致：{item['name']}")
        dest.write_bytes(response.content)
        downloaded.append(item["name"])
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"version": version, "dir": str(target),
            "downloaded": downloaded, "files": len(manifest["files"])}


def pull_history(root: Path, version: str | None = None, env_file=None,
                 base: str = DEFAULT_BASE, names: list[str] | None = None,
                 manifest: dict | None = None) -> dict:
    manifest = manifest or load_manifest()
    version = version or manifest["version"]
    return _sync(manifest, history_dir(Path(root), version), version,
                 env_file, base, names)


def pull_orders(root: Path, version: str | None = None, env_file=None,
                base: str = DEFAULT_BASE, names: list[str] | None = None,
                manifest: dict | None = None) -> dict:
    """最新订单明细（含历史 GS + EN 增量），供自行分析/预测。"""
    manifest = manifest or load_manifest(ORDERS_MANIFEST)
    version = version or manifest["version"]
    return _sync(manifest, orders_dir(Path(root), version), version,
                 env_file, base, names)


def orders_status(root: Path, manifest: dict | None = None) -> dict:
    return _status_for(Path(root), manifest or load_manifest(ORDERS_MANIFEST), "orders")
