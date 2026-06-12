# DAM 市场调研摘要

> 调研日期: 2026-06-09 | 方法: 3 个并行 Explore Agent 同时搜索

---

## 1. 开源方案

### Pimcore
- **定位**: 一体化 PIM + DAM + MDM + CMS + 电商
- **技术栈**: PHP/Symfony, MariaDB, Redis, Elasticsearch
- **许可**: 社区版免费 (年收入 <€5M), 企业版 €25K+/年
- **优势**: 最完整的开源 PIM+DAM, 实体无关数据模型, 原生内置 DAM
- **劣势**: PHP 技术栈不匹配, 部署极复杂 (ImageMagick/FFmpeg/Chromium), 无 ERPNext 连接器, 学习曲线陡峭
- **结论**: ❌ 技术栈差距太大

### Akeneo
- **定位**: 专注 PIM（无内置 DAM）
- **技术栈**: PHP/Symfony
- **许可**: 社区版 (限制 2 用户、无图片), 企业版 $40K+/年
- **结论**: ❌ 社区版太受限, 企业版太贵, 无 DAM

### UnoPim
- **技术栈**: Laravel/Vue.js, MIT 许可
- **定位**: 轻量级 PIM
- **结论**: ❌ 太新, 无 DAM, 生态不成熟

---

## 2. 商业 SaaS 方案

| 方案 | 年费 | 优势 | 劣势 |
|------|------|------|------|
| **Salsify** | $180K+ | 最强亚马逊/Wayfair 同步, 最强 AI | 价格远超预算 |
| **Plytix** | €6K-20K | 快速部署, 免费层 | >10K SKU 性能下降 |
| **inriver** | $55K+ | 强 ERP 集成, 数字货架分析 | SAP 导向, 贵 |
| **Sales Layer** | $12K-36K | 快速部署, 强 AI | 品牌知名度低 |
| **Acquia PIM** | $36.5K | 统一 DAM+PIM | Drupal 生态 |
| **AEM Assets** | $20K-50K | 纯 DAM, AI 标注 | 零 PIM 功能 |

**结论**: 全部需要付费许可 + 无 ERPNext 连接器 + 数据锁定第三方。

---

## 3. Frappe/ERPNext 生态

- **无现成 PIM/DAM Frappe App** — 市场空白
- Frappe v16 的 `extend_doctype_class` 可干净扩展 ERPNext Item
- Frappe 内置 File DocType + REST API + 权限系统可作为 DAM 底座
- 团队已有 Frappe REST API 客户端（EN_API 模块验证）

---

## 4. 最终决策

自建 `vilavi_pim` Frappe App，分两步走：
1. 本地原型验证 (FastAPI + Vue 3 + SQLite)
2. 验证通过后迁入 Frappe Pages
