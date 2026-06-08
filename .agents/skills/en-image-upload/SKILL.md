---
name: en-image-upload
description: >
  ERPNext 图片上传工具集。支持三种方式:
  1) upload_item_images.py — 从赛狐图片链接 Excel 更新物料组主图
  2) upload_local_images.py — CLI 批量上传本地图片到 ERPNext
  3) image_upload_app.py — Web 可视化拖拽上传+排序+压缩
  当用户提到"图片链接"、"商品图片"、"上传图片"、"物料图片"、"物料组主图"、
  "图片上传"、"erpnext image"、"item image upload"、"产品图片"、"EN API"、
  "图片URL"、"图片链接Excel"、"拖拽上传"、"图片排序"等时触发。
  不要用于商品分类(category)、采购成本(item-cost)、商品重尺(item-weight)、
  库存(stock-init)或多属性(multi-attr)。
compatibility: >
  需要 pandas, openpyxl, requests, pillow, fastapi, uvicorn。
  从 EN_API/ 目录运行，统一用 uv run python。
  需要设置环境变量 ERP_API_KEY 和 ERP_API_SECRET。
metadata:
  module: EN_API
  scripts: upload_item_images.py, upload_local_images.py, image_upload_app.py
  updated: 2026-06-08
---

# ERPNext 图片上传工具集

三个脚本，三种使用场景：

| 脚本 | 场景 | 启动方式 |
|------|------|---------|
| `upload_item_images.py` | 赛狐 Excel → 更新 Item Group 主图 | `uv run python upload_item_images.py` |
| `upload_local_images.py` | CLI 批量上传本地图片 | `uv run python upload_local_images.py` |
| `image_upload_app.py` | **Web 拖拽上传+排序** | `uv run python image_upload_app.py` |

## 快速启动

```bash
cd EN_API

# Web 可视化（推荐普通同事使用）
uv run python image_upload_app.py

# CLI 批量上传
uv run python upload_local_images.py

# 物料组主图更新
uv run python upload_item_images.py --dry-run
```

## 图片压缩

所有上传方式默认启用客户端压缩（quality 85 + max 1500px），比 ERPNext 内置优化更温和可控。

- CLI: `--no-compress` 禁用 / `--quality 90` 调整 / `--max-size 2000` 调整
- Web: 页面「压缩图片」复选框，默认勾选
- 安全: 压缩后若变大则保留原图

## 环境

默认 **prod** (https://erpnext.vilavi.cn)，开发测试用 `--env test`。

## 参考

- [给人看的 README](../../EN_API/README.md)
- [Agent 详细参考](../../EN_API/AGENT_HANDOFF.md)
