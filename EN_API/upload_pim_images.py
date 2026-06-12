# -*- coding: utf-8 -*-
"""上传本地图片到 ERPNext 物料组 custom_pim_images 子表。

流程:
  1. 读取 C:/Users/DEV01/Pictures/EN物料组图片 下所有图片
  2. 用文件名 (不含扩展名) 作为 item_group_name 查询物料组
  3. 压缩图片 (借鉴 upload_local_images.py 的压缩逻辑)
  4. 上传到 ERPNext
  5. 通过 PUT 更新物料组的 custom_pim_images 子表
  6. 可选 (--update-image): 同步更新物料组的 image 主图字段

使用:
  uv run python upload_pim_images.py                      # 默认 test
  uv run python upload_pim_images.py --dry-run             # 预览
  uv run python upload_pim_images.py --env prod            # 生产
  uv run python upload_pim_images.py --update-image       # 同步更新主图
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from PIL import Image
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)

# ── .env 加载 ──────────────────────────────────────────
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

# ── 环境配置 ─────────────────────────────────────────
_ENV_URLS: dict[str, str] = {
    "test": "https://ensh.vilavi.cn",
    "prod": "https://erpnext.vilavi.cn",
}
_DEFAULT_ENV = "test"
_ITEM_GROUP = "Item Group"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# ── 默认路径 ─────────────────────────────────────────
_DEFAULT_IMG_DIR = Path("C:/Users/DEV01/Pictures/EN物料组图片")
_DIR_OUT = _DIR / "out"

# ── 文件名→物料组名称映射 ────────────────────────────
# 当图片文件名与 ERPNext 物料组名称不一致时使用
# value 为 str 表示单一物料组，为 list 表示上传到多个物料组
FILENAME_MAPPING: dict[str, str | list[str]] = {
    "半圆宠物辅助爬梯": "半圆宠物爬梯",
    "儿童泡沫攀岩块": "儿童泡沫攀岩块类",
    "单双人地板沙发": ["单双人地板沙发-单人位", "单双人地板沙发-双人位"],
    "可组合扶手沙发组合": "可组合扶手沙发",
    "安全感宠物窝": "安全感靠墙宠物窝",
    "弧形海绵靠枕-涤麻": "弧形海绵靠枕",
    "弧形海绵靠枕-菱形": "弧形海绵靠枕",
    "户外托盘垫-云朵款": ["户外托盘垫-云朵款靠背", "户外托盘垫-云朵款坐垫"],
    "扭结地板沙发": ["扭结地板沙发-沙发", "扭结地板沙发-脚踏"],
    "拼图模块沙发": ["拼图模块沙发-六边形模块", "拼图模块沙发-单人"],
    "曲线沙发": ["曲线沙发座椅", "曲线沙发茶几"],
    "椭圆墩—旧铁皮": "椭圆墩-旧铁皮",
    "大尺寸车载狗窝": "大尺寸车载宠物窝",
    "户外托盘垫印花款": "户外托盘垫印花款类",
}


# ── HTTP 适配器 ──────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


# ── 图片压缩 ────────────────────────────────────────
def compress_image(
    data: bytes,
    max_size: int = 1500,
    quality: int = 85,
) -> bytes:
    """压缩图片: 缩放到 max_size 最大边长, 输出 JPEG 字节。

    条件:
      - 仅当 max(w,h) > max_size 时才缩放
      - PNG/GIF 透明通道 → 填充白色背景
      - 压缩后若变大 → 保留原图
    """
    orig_size = len(data)
    img = Image.open(io.BytesIO(data))
    w, h = img.size

    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # Convert to RGB (handle PNG/GIF alpha)
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    compressed = buf.getvalue()
    # Safety: don't let compression increase file size
    if len(compressed) >= orig_size:
        return data
    return compressed


# ── ERPNext 客户端 ───────────────────────────────────
class ErpnextClient:
    """ERPNext REST API 客户端。"""

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def find_item_group_by_name(self, name: str) -> dict[str, Any] | None:
        """按 item_group_name 查询物料组。"""
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}"
        params = {
            "filters": json.dumps(
                [[_ITEM_GROUP, "item_group_name", "=", name]],
                ensure_ascii=False,
            ),
            "fields": json.dumps(["name", "item_group_name"]),
        }
        try:
            resp = self._request("GET", url, params=params)
            data = resp.json().get("data", [])
            return data[0] if data else None
        except requests.RequestException:
            return None

    def get_item_group_full(self, docname: str) -> dict[str, Any] | None:
        """获取物料组完整数据（含子表）。"""
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}/{docname}"
        try:
            resp = self._request("GET", url)
            return resp.json().get("data")
        except requests.RequestException:
            return None

    def upload_file(
        self, filename: str, file_bytes: bytes,
        doctype: str = "", docname: str = "",
    ) -> str:
        """上传文件到 ERPNext，返回 file_url。"""
        ext = Path(filename).suffix.lower()
        mime = _MIME_MAP.get(ext, "application/octet-stream")
        url = f"{self.base_url}/api/method/upload_file"
        data: dict[str, str] = {"is_private": "0"}
        if doctype:
            data["doctype"] = doctype
        if docname:
            data["docname"] = docname
        resp = self._request("POST", url,
            files={"file": (filename, file_bytes, mime)},
            data=data,
        )
        return resp.json()["message"]["file_url"]

    def update_pim_images(
        self, docname: str, file_url: str, purpose: str = "Main",
    ) -> dict[str, Any]:
        """向物料组的 custom_pim_images 子表追加一条图片记录。"""
        # 1. 获取当前完整文档
        item = self.get_item_group_full(docname)
        if not item:
            raise ValueError(f"物料组 {docname} 不存在")

        # 2. 获取当前子表行，确定 sort_order
        pim_rows = item.get("custom_pim_images") or []
        next_sort = max((r.get("sort_order") or 0 for r in pim_rows), default=0) + 1

        # 3. 追加新行
        new_row = {
            "image_file": file_url,
            "file_url": file_url,
            "purpose": purpose,
            "is_primary": 0 if pim_rows else 1,
            "sort_order": next_sort,
        }
        pim_rows.append(new_row)

        # 4. PUT 更新
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}/{docname}"
        resp = self._request("PUT", url, json={"custom_pim_images": pim_rows})
        return resp.json()

    def set_image_field(self, docname: str, file_url: str) -> dict[str, Any]:
        """更新物料组的 image 主图字段。"""
        url = f"{self.base_url}/api/resource/{_ITEM_GROUP}/{docname}"
        return self._request("PUT", url, json={"image": file_url}).json()

    def _request(
        self, method: str, url: str, *,
        retries: int = 2, retry_delay: float = 3.0,
        **kwargs: Any,
    ) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 60))
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
        raise last_exc  # noqa: TRY201


# ── 主入口 ─────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="上传图片到物料组 custom_pim_images 子表")
    ap.add_argument("--env", "-e", choices=["test", "prod"], default=_DEFAULT_ENV)
    ap.add_argument("--url", "-u", default=None)
    ap.add_argument("--dry-run", "-n", action="store_true", help="预览模式")
    ap.add_argument("--input-dir", "-i", type=Path, default=_DEFAULT_IMG_DIR)
    ap.add_argument("--out-dir", type=Path, default=_DIR_OUT)
    ap.add_argument("--no-compress", action="store_true", help="不压缩")
    ap.add_argument("--max-size", type=int, default=1500, help="最大边长 (默认 1500)")
    ap.add_argument("--quality", type=int, default=85, help="JPEG 质量 (默认 85)")
    ap.add_argument("--update-image", "-m", action="store_true",
                    help="同步更新物料组的 image 主图字段（默认仅写入 custom_pim_images）")
    args = ap.parse_args()

    # 1. 检查图片目录
    img_dir = args.input_dir
    if not img_dir.is_dir():
        print(f"错误: 目录不存在 {img_dir}")
        return 1

    image_files = sorted([
        p for p in img_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    ])
    if not image_files:
        print(f"错误: 目录 {img_dir} 中没有图片文件")
        return 1
    print(f"找到 {len(image_files)} 个图片文件:")
    for f in image_files:
        print(f"  {f.name}")

    # 2. 连接 ERPNext
    env_prefix = "TEST" if args.env == "test" else "PROD"
    api_key = (
        os.getenv("ERP_API_KEY")
        or os.getenv(f"{env_prefix}_ERP_API_KEY")
        or ""
    )
    api_secret = (
        os.getenv("ERP_API_SECRET")
        or os.getenv(f"{env_prefix}_ERP_API_SECRET")
        or ""
    )
    if not api_key or not api_secret:
        print("错误: 请设置环境变量或创建 .env 文件")
        return 1

    base_url = args.url or os.getenv("ERP_URL") or _ENV_URLS[args.env]
    print(f"目标环境: {args.env} ({base_url})")

    client = ErpnextClient(base_url, api_key, api_secret)

    # 3. 逐文件处理
    do_compress = not args.no_compress
    rows: list[dict[str, Any]] = []
    print(f"\n=== {'预览' if args.dry_run else '执行'}阶段 ===")

    for idx, img_path in enumerate(image_files, 1):
        stem = img_path.stem  # filename without extension
        print(f"\n[{idx}/{len(image_files)}] {img_path.name}")

        # a) 确定目标物料组名称（支持映射）
        mapped = FILENAME_MAPPING.get(stem, stem)  # str or list[str]
        target_names: list[str] = [mapped] if isinstance(mapped, str) else mapped
        print(f"  目标物料组: {target_names}")

        # b) 读取 + 压缩（只需做一次）
        raw_bytes = img_path.read_bytes()
        orig_size = len(raw_bytes)
        compressed = raw_bytes
        if do_compress:
            compressed = compress_image(raw_bytes, max_size=args.max_size, quality=args.quality)
            print(f"  压缩: {orig_size/1024:.0f}KB -> {len(compressed)/1024:.0f}KB")

        upload_filename = img_path.name
        if do_compress and compressed is not raw_bytes:
            upload_filename = f"{stem}.jpg"

        # 对每个目标物料组执行操作
        for tname in target_names:
            # a2) 查询物料组
            ig = client.find_item_group_by_name(tname)
            if ig is None:
                rows.append({
                    "文件名": img_path.name,
                    "物料组名称": tname,
                    "物料组ID": "",
                    "原图大小KB": round(orig_size / 1024, 1),
                    "压缩后大小KB": round(len(compressed) / 1024, 1),
                    "file_url": "",
                    "操作": "跳过",
                    "备注": f"未找到物料组: {tname}",
                })
                print(f"  [跳过] 未找到物料组: {tname}")
                continue

            ig_name = ig["name"]
            ig_title = ig["item_group_name"]
            print(f"  匹配物料组: {ig_title} ({ig_name})")

            # a3) 查重
            full_ig = client.get_item_group_full(ig_name)
            existing_pim = full_ig.get("custom_pim_images") or [] if full_ig else []
            already_exists = any(
                (row.get("image_file") or "").endswith(upload_filename)
                or (row.get("file_url") or "").endswith(upload_filename)
                for row in existing_pim
            )

            if args.dry_run:
                update_hint = " + image主图" if args.update_image else ""
                exist_hint = " (已存在, 将跳过)" if already_exists else ""
                rows.append({
                    "文件名": img_path.name,
                    "物料组名称": ig_title,
                    "物料组ID": ig_name,
                    "原图大小KB": round(orig_size / 1024, 1),
                    "压缩后大小KB": round(len(compressed) / 1024, 1),
                    "file_url": "",
                    "操作": "预览",
                    "备注": f"dry-run, 将上传到 custom_pim_images{update_hint}{exist_hint}",
                })
                print(f"  [预览] 将上传到 {ig_name} 的 custom_pim_images{update_hint}{exist_hint}")
                continue

            if already_exists:
                rows.append({
                    "文件名": img_path.name,
                    "物料组名称": ig_title,
                    "物料组ID": ig_name,
                    "原图大小KB": round(orig_size / 1024, 1),
                    "压缩后大小KB": round(len(compressed) / 1024, 1),
                    "file_url": "",
                    "操作": "跳过",
                    "备注": f"custom_pim_images 已存在同名文件: {upload_filename}",
                })
                print(f"  [跳过] 已存在同名文件: {upload_filename}")
                continue

            # c) 上传文件
            try:
                file_url = client.upload_file(
                    upload_filename, compressed,
                    doctype=_ITEM_GROUP, docname=ig_name,
                )
                full_url = f"{base_url}{file_url}"
                print(f"  上传成功: {full_url}")
            except Exception as e:
                rows.append({
                    "文件名": img_path.name,
                    "物料组名称": ig_title,
                    "物料组ID": ig_name,
                    "原图大小KB": round(orig_size / 1024, 1),
                    "压缩后大小KB": round(len(compressed) / 1024, 1),
                    "file_url": "",
                    "操作": "失败",
                    "备注": f"上传失败: {e}",
                })
                print(f"  [失败] 上传失败: {e}")
                continue

            # d) 更新 custom_pim_images
            try:
                client.update_pim_images(ig_name, file_url, purpose="Main")
                print(f"  [OK] 已写入 custom_pim_images")

                # e) 可选: 同步更新 image 主图字段
                image_updated = False
                if args.update_image:
                    try:
                        client.set_image_field(ig_name, file_url)
                        image_updated = True
                        print(f"  [OK] 已更新 image 主图字段")
                    except Exception as e:
                        print(f"  [WARN] image 主图更新失败: {e}")

                op_status = "成功(含主图)" if image_updated else "成功"
                rows.append({
                    "文件名": img_path.name,
                    "物料组名称": ig_title,
                    "物料组ID": ig_name,
                    "原图大小KB": round(orig_size / 1024, 1),
                    "压缩后大小KB": round(len(compressed) / 1024, 1),
                    "file_url": full_url,
                    "操作": op_status,
                    "备注": "含主图更新" if image_updated else "仅子表",
                })
            except Exception as e:
                rows.append({
                    "文件名": img_path.name,
                    "物料组名称": ig_title,
                    "物料组ID": ig_name,
                    "原图大小KB": round(orig_size / 1024, 1),
                    "压缩后大小KB": round(len(compressed) / 1024, 1),
                    "file_url": full_url,
                    "操作": "部分成功",
                    "备注": f"文件已上传但写入子表失败: {e}",
                })
                print(f"  [WARN] 文件已上传但子表更新失败: {e}")

    # 4. 生成报告
    print(f"\n=== 生成报告 ===")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "预览" if args.dry_run else "结果"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"PIM图片上传{tag}_{ts}.xlsx"

    summary = {
        "执行时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "模式": "预览 (dry-run)" if args.dry_run else "实际写入",
        "目标环境": f"{args.env} ({base_url})",
        "更新主图": "是" if args.update_image else "否",
        "图片总数": len(image_files),
        "成功(含主图)": sum(1 for r in rows if r["操作"] == "成功(含主图)"),
        "成功": sum(1 for r in rows if r["操作"] == "成功"),
        "跳过": sum(1 for r in rows if r["操作"] == "跳过"),
        "失败": sum(1 for r in rows if r["操作"] == "失败"),
        "部分成功": sum(1 for r in rows if r["操作"] == "部分成功"),
        "预览": sum(1 for r in rows if r["操作"] == "预览"),
    }

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame([summary]).to_excel(writer, sheet_name="汇总", index=False)
        if rows:
            col_order = ["文件名", "物料组名称", "物料组ID", "原图大小KB",
                        "压缩后大小KB", "file_url", "操作", "备注"]
            df = pd.DataFrame(rows)
            df = df[[c for c in col_order if c in df.columns]]
            df.to_excel(writer, sheet_name="明细", index=False)

    print(f"  报告: {out_path}")
    parts = [f"{k}: {v}" for k, v in summary.items()
             if k in ("成功(含主图)", "成功", "跳过", "失败", "部分成功", "预览") and v > 0]
    print(f"结果: {' / '.join(parts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
