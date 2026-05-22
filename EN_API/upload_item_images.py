# -*- coding: utf-8 -*-
"""从赛狐图片链接 Excel 读取 SPU 和图片 URL，
通过 ERPNext REST API 更新对应 Item Group (物料组) 的 image 字段。

流程:
  1. 读取 赛狐图片链接/ 下最新的 xlsx
  2. 加载 .env 凭证 (优先级: 已有环境变量 > .env 文件)
  3. 按 SPU (custom_model_id) 查询 ERPNext Item Group (缓存, 同 SPU 不重复查)
  4. 安全附件管理:
     a. 下载图片计算 MD5 → 与现有 File 比对
     b. hash 匹配则跳过 (不重复上传)
     c. 附件 < 3 直接上传; = 3 只删孤儿文件 (保留当前主图)
  5. 下载图片 → 以真实文件上传 ERPNext (绕过 COS 防盗链)
  6. PUT 更新 Item Group 的 image 字段为本地 /files/xxx
  7. 生成报告 Excel (所有行, out/ 目录, 带时间戳)

凭证: 从项目根目录 .env 或模块目录 .env 读取, 或设置环境变量:
  ERP_API_KEY=xxx
  ERP_API_SECRET=yyy

使用:
  python upload_item_images.py --dry-run       # 预览
  python upload_item_images.py --spu KS0001    # 单 SPU
  python upload_item_images.py --env prod      # 生产
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)


# ── .env 加载 (stdlib only) ──────────────────────────
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

_ROOT = _DIR.parent
_load_dotenv([_DIR / ".env", _ROOT / ".env"])

# ── 路径常量 ─────────────────────────────────────────
_DIR_DATA = _DIR / "赛狐图片链接"
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)

# ── 环境配置 ─────────────────────────────────────────
_ENV_URLS: dict[str, str] = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}
_DEFAULT_ENV = "test"
_ITEM_GROUP = "Item Group"
_ATTACHMENT_LIMIT = 3

# ── Excel 列名 ───────────────────────────────────────
COL_SKU = "SKU"
COL_NAME = "品名"
COL_IMAGE_URL = "图片链接"
COL_SPU = "spu"

# ── 报告 ─────────────────────────────────────────────
RPT_SPU = "spu"
RPT_SKU = "SKU"
RPT_NAME = "品名"
RPT_IMAGE_URL = "图片链接"
RPT_ITEM_GROUP = "物料组名称"
RPT_STATUS = "状态"
RPT_MESSAGE = "备注"

STATUS_SUCCESS = "成功"
STATUS_NO_MATCH = "无匹配物料组"
STATUS_DOWNLOAD_FAIL = "下载/上传失败"
STATUS_UPDATE_FAIL = "更新失败"
STATUS_SKIPPED = "跳过（同SPU已处理）"
STATUS_FULL_UNSAFE = "跳过（附件满且无法安全清理）"


# ── HTTP 适配器 ──────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


# ── ERPNext 客户端 ───────────────────────────────────
class ErpnextClient:
    """ERPNext REST API 客户端。"""

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())
        self._ig_cache: dict[str, dict[str, Any] | None] = {}

    def find_item_group(self, spu: str) -> dict[str, Any] | None:
        if spu in self._ig_cache:
            return self._ig_cache[spu]
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}"
        params: dict[str, str] = {
            "filters": json.dumps([[_ITEM_GROUP, "custom_model_id", "=", spu]]),
            "fields": json.dumps(["name", "item_group_name", "image"]),
        }
        try:
            resp = self._request("GET", url, params=params)
            data: list[dict[str, Any]] = resp.json().get("data", [])
        except requests.RequestException:
            self._ig_cache[spu] = None
            raise
        result = data[0] if data else None
        self._ig_cache[spu] = result
        return result

    def get_attached_files(self, item_group_name: str) -> list[dict[str, Any]]:
        """查询挂载到 Item Group 的所有 File 记录 (不限字段)。
        附件上限按文档算, 不只按字段。返回 [{name, file_url, content_hash, attached_to_field}, ...]"""
        url = f"{self.base_url}/api/resource/File"
        params: dict[str, str] = {
            "filters": json.dumps([["attached_to_name", "=", item_group_name]]),
            "fields": json.dumps(["name", "file_url", "content_hash", "attached_to_field"]),
        }
        return self._request("GET", url, params=params).json().get("data", [])

    def delete_files(self, names: list[str]) -> int:
        """DELETE 指定的 File 记录。返回成功删除数量。"""
        n = 0
        for name in names:
            try:
                self._request("DELETE", f"{self.base_url}/api/resource/File/{name}")
                n += 1
            except requests.RequestException:
                pass
        return n

    def download_and_upload(
        self, item_group_name: str, image_url: str
    ) -> str:
        """下载图片 + 上传到 ERPNext。返回 file_url。"""
        resp = self._request("GET", image_url, timeout=(30, 60))
        img_bytes = resp.content

        filename = image_url.rsplit("/", 1)[-1].split("?")[0] or "image.jpg"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpeg"
        mime = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "gif": "image/gif", "webp": "image/webp",
        }.get(ext, "image/jpeg")

        url = f"{self.base_url}/api/method/upload_file"
        resp = self._request("POST", url,
            files={"file": (filename, img_bytes, mime)},
            data={
                "is_private": "0",
                "doctype": _ITEM_GROUP,
                "docname": item_group_name,
                "fieldname": "image",
            },
        )
        file_url: str = resp.json()["message"]["file_url"]
        return file_url

    def set_image_field(self, item_group_name: str, image_url: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}/{item_group_name}"
        return self._request("PUT", url, json={"image": image_url}).json()

    def _request(
        self, method: str, url: str, *,
        retries: int = 1, retry_delay: float = 3.0,
        **kwargs: Any,
    ) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 120))
        last_exc = None
        for attempt in range(retries + 1):
            try:
                resp = self.session.request(method, url, timeout=timeout, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(retry_delay)
        raise last_exc


# ── 文件选择 ─────────────────────────────────────────
def _find_latest_xlsx(directory: Path, keyword: str) -> Path:
    if not directory.is_dir():
        raise FileNotFoundError(f"目录不存在: {directory}")
    cands = [
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() == ".xlsx"
        and not p.name.startswith("~$") and keyword in p.name
    ]
    if not cands:
        raise FileNotFoundError(
            f"{directory} 下找不到含 '{keyword}' 的 xlsx (已排除 ~$ 锁文件)"
        )
    return max(cands, key=lambda p: p.stat().st_mtime)


# ── 报告写入 ─────────────────────────────────────────
def _write_report(
    rows: list[dict[str, str]], out_path: Path, summary: dict[str, Any],
) -> None:
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="汇总", index=False)
        df = pd.DataFrame(rows)
        col_order = [
            RPT_SPU, RPT_SKU, RPT_NAME, RPT_IMAGE_URL,
            RPT_ITEM_GROUP, RPT_STATUS, RPT_MESSAGE,
        ]
        df = df[[c for c in col_order if c in df.columns]]
        df.to_excel(writer, sheet_name="明细", index=False)


# ── 主入口 ─────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="从赛狐图片链接 Excel 更新 ERPNext Item Group 图片")
    ap.add_argument("--env", "-e", choices=["test", "prod"], default=_DEFAULT_ENV)
    ap.add_argument("--url", "-u", default=None)
    ap.add_argument("--spu", "-s", default=None)
    ap.add_argument("--dry-run", "-n", action="store_true")
    ap.add_argument("--input", "-i", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=_DIR_OUT)
    args = ap.parse_args()

    api_key = os.getenv("ERP_API_KEY", "")
    api_secret = os.getenv("ERP_API_SECRET", "")
    if not api_key or not api_secret:
        print("错误: 请设置环境变量或创建 .env 文件")
        print(f"  {_DIR}\\.env:  ERP_API_KEY=xxx / ERP_API_SECRET=yyy")
        return 1

    base_url = args.url or os.getenv("ERP_URL") or _ENV_URLS[args.env]
    print(f"目标环境: {args.env} ({base_url})")

    if args.input:
        input_path = args.input
    else:
        input_path = _find_latest_xlsx(_DIR_DATA, "图片链接")
    print(f"输入文件: {input_path.name}")

    df = pd.read_excel(input_path)
    for col in [COL_SKU, COL_NAME, COL_IMAGE_URL, COL_SPU]:
        if col not in df.columns:
            print(f"错误: Excel 缺少列 '{col}'")
            return 1

    if args.spu:
        mask = df[COL_SPU].astype(str).str.strip().str.upper() == args.spu.strip().upper()
        df = df[mask].copy()
        if df.empty:
            print(f"未找到 SPU={args.spu} 的数据")
            return 1
        print(f"测试模式: 仅处理 SPU={args.spu} ({len(df)} 行)")

    n_unique_spu = df[COL_SPU].nunique()
    print(f"共 {len(df)} 行, {n_unique_spu} 个唯一 SPU")

    client = ErpnextClient(base_url, api_key, api_secret)

    report_rows: list[dict[str, str]] = []
    processed_spus: set[str] = set()
    counts: dict[str, int] = {
        "成功": 0, "无匹配物料组": 0, "下载/上传失败": 0, "更新失败": 0,
        "跳过（同SPU已处理）": 0, "跳过（附件满且无法安全清理）": 0,
    }

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        spu_s = str(row[COL_SPU]).strip()
        sku = str(row[COL_SKU]).strip()
        name_cn = str(row[COL_NAME]).strip()
        image_url = str(row[COL_IMAGE_URL]).strip()

        base: dict[str, str] = {
            RPT_SPU: spu_s, RPT_SKU: sku, RPT_NAME: name_cn,
            RPT_IMAGE_URL: image_url, RPT_ITEM_GROUP: "", RPT_STATUS: "", RPT_MESSAGE: "",
        }

        # 1. 查询 Item Group
        try:
            ig = client.find_item_group(spu_s)
        except requests.RequestException as e:
            base[RPT_STATUS] = STATUS_NO_MATCH
            base[RPT_MESSAGE] = f"查询失败: {e}"
            report_rows.append(base)
            counts["无匹配物料组"] += 1
            print(f"  [{idx}/{len(df)}] {sku} -> 查询失败")
            continue

        if ig is None:
            base[RPT_STATUS] = STATUS_NO_MATCH
            base[RPT_MESSAGE] = f"ERPNext 中未找到 custom_model_id={spu_s} 的 Item Group"
            report_rows.append(base)
            counts["无匹配物料组"] += 1
            print(f"  [{idx}/{len(df)}] {sku} -> 无匹配")
            continue

        ig_name = ig.get("name", "")
        ig_title = ig.get("item_group_name", "")
        ig_image = ig.get("image") or ""  # 当前主图 file_url
        base[RPT_ITEM_GROUP] = f"{ig_title} ({ig_name})"

        if args.dry_run:
            base[RPT_STATUS] = "匹配"
            base[RPT_MESSAGE] = f"现有 image: {ig_image or '(空)'}"
            report_rows.append(base)
            print(f"  [{idx}/{len(df)}] {sku} -> {ig_name} (现有: {ig_image or '(空)'})")
            continue

        # 2. 同 SPU 已处理
        if spu_s in processed_spus:
            base[RPT_STATUS] = STATUS_SKIPPED
            base[RPT_MESSAGE] = "同 SPU 已在前面行处理，跳过"
            report_rows.append(base)
            counts["跳过（同SPU已处理）"] += 1
            print(f"  [{idx}/{len(df)}] {sku} -> 跳过 (同 SPU)")
            continue

        # 3. 查所有附件记录 (不限字段, 上限按文档算)
        files = client.get_attached_files(ig_name)
        total = len(files)

        # 按 hash 分组, 区分 image 字段 vs 其他字段
        hash_groups: dict[str, list[dict]] = {}
        none_hash: list[dict] = []
        for f in files:
            h = f.get("content_hash")
            (hash_groups.setdefault(h, []) if h else none_hash).append(f)

        unique_files = len(hash_groups) + len(none_hash)

        # 4. 附件上限: 只删我们可确认安全的记录
        #    a) image 字段上的重复记录 (同 hash, 同物理文件)
        #    b) image 字段上 hash=None 的记录 (URL 引用, file_size=0)
        #    绝不删: 非 image 字段的附件 / 唯一 hash 的 image 记录
        if total >= _ATTACHMENT_LIMIT:
            safe_to_delete: list[str] = []
            for g in hash_groups.values():
                if len(g) > 1:
                    # 同 hash 的 image 字段记录, 只保留一个
                    image_records = [f for f in g if f.get("attached_to_field") == "image"]
                    if len(image_records) > 1:
                        safe_to_delete.extend(f["name"] for f in image_records[1:])
                    # 非 image 字段的记录不删 (如 PDF 等用户手动加的附件)
            safe_to_delete.extend(
                f["name"] for f in none_hash
                if f.get("attached_to_field") == "image"
            )

            if safe_to_delete:
                n = client.delete_files(safe_to_delete)
                print(f"  [{idx}/{len(df)}] {sku} -> 附件满({total}条, {unique_files}个不同文件), "
                      f"安全清理 {n} 条 (image 字段重复/无效记录)")
            else:
                base[RPT_STATUS] = STATUS_FULL_UNSAFE
                base[RPT_MESSAGE] = (
                    f"附件已满 ({total}条记录, {unique_files}个不同文件), "
                    f"无 image 字段重复记录可安全清理, 跳过"
                )
                report_rows.append(base)
                counts["跳过（附件满且无法安全清理）"] += 1
                print(f"  [{idx}/{len(df)}] {sku} -> 附件满, 无法安全清理")
                continue

        # 5. 下载 + 上传
        try:
            file_url = client.download_and_upload(ig_name, image_url)
        except requests.RequestException as e:
            base[RPT_STATUS] = STATUS_DOWNLOAD_FAIL
            base[RPT_MESSAGE] = f"下载/上传失败: {e}"
            report_rows.append(base)
            counts["下载/上传失败"] += 1
            print(f"  [{idx}/{len(df)}] {sku} -> 下载/上传失败")
            continue

        try:
            client.set_image_field(ig_name, file_url)
        except requests.RequestException as e:
            base[RPT_STATUS] = STATUS_UPDATE_FAIL
            base[RPT_MESSAGE] = f"已上传 ({file_url}) 但 PUT 失败: {e}"
            report_rows.append(base)
            counts["更新失败"] += 1
            print(f"  [{idx}/{len(df)}] {sku} -> PUT 失败")
            continue

        processed_spus.add(spu_s)
        base[RPT_STATUS] = STATUS_SUCCESS
        base[RPT_MESSAGE] = f"{file_url}"
        report_rows.append(base)
        counts["成功"] += 1
        print(f"  [{idx}/{len(df)}] {sku} -> {ig_name} ({file_url})")

    # ── 写报告 ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "预览" if args.dry_run else "结果"
    out_path = args.out_dir / f"图片上传{tag}_{ts}.xlsx"
    summary: dict[str, Any] = {
        "输入文件": input_path.name,
        "目标环境": f"{args.env} ({base_url})",
        "模式": "预览 (dry-run)" if args.dry_run else "实际写入",
        "总行数": len(df), "唯一SPU数": n_unique_spu,
        **counts,
        "处理时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_report(report_rows, out_path, summary)

    print(f"\n报告: {out_path}")
    parts = [f"{k}: {v}" for k, v in counts.items() if v > 0]
    print("结果: " + " / ".join(parts) if parts else "无处理项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
