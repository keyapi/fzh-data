"""Resolve the private data root and pack manifest without hard-coded analysis paths."""
from __future__ import annotations
import json, os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PACKAGE / "pack_manifest.json"
ENV_ROOT = "FZH_DATA_ROOT"
ENV_MANIFEST = "FZH_PACK_MANIFEST"


def data_root(value=None, create=False):
    root = value or os.environ.get(ENV_ROOT)
    if not root:
        raise SystemExit(f"缺少数据目录：请设置 {ENV_ROOT} 或传 --data-root")
    path = Path(root).expanduser()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        raise SystemExit(f"数据目录不存在：{path}")
    return path


def manifest_path(value=None):
    return Path(value or os.environ.get(ENV_MANIFEST) or DEFAULT_MANIFEST)


def load_manifest(value=None):
    path = manifest_path(value)
    if not path.exists():
        raise SystemExit(f"找不到包清单：{path}")
    return json.loads(path.read_text(encoding="utf-8"))
