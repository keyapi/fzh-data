# -*- coding: utf-8 -*-
"""Synology FileStation API client — shared module.

Wraps N4S4/synology-api (PyPI: synology-api) for project convenience.
https://github.com/N4S4/synology-api

Usage:
    from NAS_API.synology import SynologyNAS, get_nas

    nas = SynologyNAS(base_url=..., username=..., password=...)
    # or auto-configure from env:
    nas = get_nas()
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from synology_api.filestation import FileStation

_DIR = Path(__file__).resolve().parent


def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


def _parse_nas_url(url: str) -> tuple[str, str, bool]:
    """Parse NAS URL into (host, port, secure)."""
    url = url.strip().rstrip("/")
    secure = url.startswith("https://")
    host = url.replace("https://", "").replace("http://", "")
    if ":" in host:
        host, port = host.split(":", 1)
    else:
        port = "5001" if secure else "5000"
    return host, port, secure


class SynologyNAS:
    """Synology FileStation API client — wraps N4S4/synology-api FileStation.

    Methods (backward-compatible with original raw-requests version):
        get_file_list(folder_path, limit, offset) -> list[dict]
        get_thumbnail(path, size) -> (bytes | None, mime_type | None)
        download_file(path) -> bytes | None
        create_folder(folder_path, name, force_parent) -> dict
        delete_folder(path) -> dict
        folder_exists(folder_path, name) -> bool

    Plus new:
        create_subfolders(folder_path, names) -> list of results
    """

    def __init__(
        self,
        base_url: str = "",
        username: str = "",
        password: str = "",
        root_folder: str = "/FZH共享文件夹",
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.username = username
        self.password = password
        self.root_folder = root_folder
        self._fl: FileStation | None = None
        if self.base_url and self.username:
            try:
                host, port, secure = _parse_nas_url(self.base_url)
                self._fl = FileStation(
                    ip_address=host,
                    port=port,
                    username=self.username,
                    password=self.password,
                    secure=secure,
                    cert_verify=False,
                    dsm_version=7,
                    debug=False,
                )
            except Exception as e:
                print(f"[nas] init failed: {e}")

    @property
    def available(self) -> bool:
        return self._fl is not None

    # ── Read ──────────────────────────────────────────

    def get_file_list(
        self, folder_path: str = "", limit: int = 1000, offset: int = 0
    ) -> list[dict]:
        if not self._fl:
            return []
        try:
            resp = self._fl.get_file_list(
                folder_path=folder_path or self.root_folder,
                limit=limit,
                offset=offset,
                sort_by="name",
                sort_direction="asc",
                additional="thumbnail,size,time",
            )
            if resp.get("success"):
                return [
                    {
                        "name": f.get("name"),
                        "path": f.get("path"),
                        "is_dir": f.get("isdir", False),
                        "size": f.get("additional", {}).get("size", 0),
                        "mtime": f.get("additional", {}).get("time", {}).get(
                            "mtime", 0
                        ),
                        "has_thumbnail": "thumbnail" in f.get("additional", {}),
                    }
                    for f in resp["data"]["files"]
                ]
        except Exception as e:
            print(f"[nas] list error: {e}")
        return []

    def get_thumbnail(
        self, path: str, size: str = "medium"
    ) -> tuple[bytes | None, str | None]:
        if not self._fl:
            return None, None
        try:
            resp = self._fl.get_thumbnail(path=path, size=size)
            if isinstance(resp, dict) and resp.get("success") and "data" in resp:
                return resp["data"], "image/jpeg"
        except Exception as e:
            print(f"[nas] thumbnail error: {e}")
        return None, None

    def download_file(self, path: str) -> bytes | None:
        if not self._fl:
            return None
        try:
            resp = self._fl.get_file(path=path, mode="download")
            if isinstance(resp, dict) and resp.get("success") and "data" in resp:
                return resp["data"]
        except Exception as e:
            print(f"[nas] download error: {e}")
        return None

    # ── Write ─────────────────────────────────────────

    def create_folder(
        self, folder_path: str, name: str, force_parent: bool = True
    ) -> dict:
        if not self._fl:
            return {"success": False, "error_code": -1, "error_msg": "not connected"}
        try:
            resp = self._fl.create_folder(folder_path, name, force_parent=force_parent)
            if resp.get("success"):
                return {"success": True, "error_code": 0, "error_msg": ""}
            err = resp.get("error", {})
            return {
                "success": False,
                "error_code": err.get("code", -1),
                "error_msg": f"code={err.get('code')}",
            }
        except Exception as e:
            return {"success": False, "error_code": -1, "error_msg": str(e)}

    def create_subfolders(
        self, folder_path: str, names: list[str]
    ) -> list[dict]:
        """Batch create multiple sub-folders under a parent folder.
        Uses Synology API bulk creation when possible.
        """
        results = []
        for name in names:
            result = self.create_folder(folder_path, name)
            result["name"] = name
            results.append(result)
        return results

    def delete_folder(self, path: str) -> dict:
        if not self._fl:
            return {"success": False, "error_code": -1, "error_msg": "not connected"}
        try:
            self._fl.delete_blocking_function(path)
            return {"success": True, "error_code": 0, "error_msg": ""}
        except Exception as e:
            return {"success": False, "error_code": -1, "error_msg": str(e)}

    def folder_exists(self, folder_path: str, name: str) -> bool:
        items = self.get_file_list(folder_path, limit=5000)
        for item in items:
            if item.get("is_dir") and item.get("name") == name:
                return True
        return False


def get_nas(env_paths: list[Path] | None = None) -> SynologyNAS:
    """Factory: create SynologyNAS from environment variables."""
    if env_paths is None:
        env_paths = [
            _DIR / ".env",
            _DIR.parent / ".env",
            _DIR.parent / "dam-prototype" / ".env",
        ]
    _load_dotenv(env_paths)
    return SynologyNAS(
        base_url=os.getenv("NAS_URL", ""),
        username=os.getenv("NAS_USERNAME", ""),
        password=os.getenv("NAS_PASSWORD", ""),
        root_folder=os.getenv("NAS_ROOT_FOLDER", "/FZH共享文件夹"),
    )
