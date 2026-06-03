---
name: en-image-upload
description: >
  ERPNext 物料组主图上传。从赛狐导出的图片链接 Excel 读取 SPU 和图片 URL,
  通过 ERPNext REST API 创建 File 记录并更新 Item Group 的 image 字段。
  当用户提到"图片链接"、"商品图片"、"上传图片"、"物料图片"、"物料组主图"、
  "图片上传"、"erpnext image"、"item image upload"、"产品图片"、"EN API"等时触发。
  不要用于商品分类(category)、采购成本(item-cost)、商品重尺(item-weight)、
  库存(stock-init)或多属性(multi-attr)。
compatibility: >
  需要 pandas, openpyxl, requests。从 EN_API/ 目录运行。
  需要设置环境变量 ERP_API_KEY 和 ERP_API_SECRET。
metadata:
  module: EN_API
  script: upload_item_images.py
  updated: 2026-05-22
---

# ERPNext 物料组主图上传

从赛狐图片链接 Excel 读取 SPU + 图片 URL, 通过 ERPNext REST API 更新 Item Group 的 image 字段。

## 快速启动

```bash
# 凭证: 复制 .env.example → .env 填入真实值, 或设置环境变量
cp EN_API/.env.example EN_API/.env

# 预览模式 (只查不写)
cd EN_API && python upload_item_images.py --dry-run

# 测试单个 SPU
python upload_item_images.py --spu KS0001

# 批量上传
python upload_item_images.py
```

## 管道概要

Excel (SKU/spu/图片链接) → 逐行处理 (SPU 缓存) → GET Item Group → 下载图片 → 真实文件上传 → PUT image 字段 → 报告(所有行)。

**两部更新缺一不可**: 下载 + upload_file (真实文件) 创建 File 记录 + PUT image 更新字段值。

## 硬约束

- 凭证通过 `.env` 文件或 `ERP_API_KEY` + `ERP_API_SECRET` 环境变量设置
- 默认 test 环境 (https://ensh.vilavi.cn), 须显式 `--env prod` 才写生产
- 更新 Item Group (物料组) 而非 Item (物料)
- SPU 对应 Item Group 的 `custom_model_id` 自定义字段

## 输出

`out/图片上传结果_{timestamp}.xlsx` — 汇总 sheet + 明细 sheet

## 参考

- [给人看的 README](../../EN_API/README.md)
- [Agent 详细参考](../../EN_API/AGENT_HANDOFF.md) — API 端点、两步更新原理、nginx 417 处理
