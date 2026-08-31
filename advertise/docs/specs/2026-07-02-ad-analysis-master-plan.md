---
okf: v0.1
type: Spec
title: Amazon 广告分析系统 — 总体规划 v1.0
description: 基于赛狐 API 数据的完整广告分析系统建设路线图，含优先级、工作量、依赖关系
tags: [amazon, advertising, roadmap, planning, architecture]
created: 2026-07-02
updated: 2026-07-02
sources:
  - advertise/docs/research/sp-report-analysis-value.md
  - advertise/docs/research/existing-codebase-audit.md
  - advertise/docs/research/amazon-ads-best-practices-2026.md
  - advertise/docs/reference/sp-report-column-reference.md
---

# Amazon 广告分析系统 — 总体规划 v1.0

> **面向读者**: 项目负责人、开发者、Agent
> **数据基线**: BJRYECLTD-US (Home & Kitchen / 枕头类目), 2026年6月
> **数据获取**: 赛狐 OpenAPI (SP 8/8, SB 7/7, SD 5/6 — 共 20 种报告)
> **原则**: 先搜再造, 把湖煮干, 每步可验证

---

## 目录

1. [现状全景](#1-现状全景)
2. [各报告分析价值矩阵](#2-各报告分析价值矩阵)
3. [系统架构设计](#3-系统架构设计)
4. [分阶段执行计划](#4-分阶段执行计划)
5. [Phase 1: 基础适配与最缺失补齐](#5-phase-1-基础适配与最缺失补齐)
6. [Phase 2: 完整覆盖与增强](#6-phase-2-完整覆盖与增强)
7. [Phase 3: 跨报告集成与高级分析](#7-phase-3-跨报告集成与高级分析)
8. [Phase 4: 自动化与持续优化](#8-phase-4-自动化与持续优化)
9. [SB/SD 扩展路线图](#9-sbsd-扩展路线图)
10. [风险与依赖](#10-风险与依赖)

---

## 1. 现状全景

### 1.1 数据获取 — 已完成 ✓

| 维度 | 状态 |
|------|------|
| 赛狐 API 认证 | ✓ OAuth 2.0 + HMAC-SHA256 (3 个拉取脚本) |
| SP 报告覆盖 | ✓ 8/8 种 (100%) |
| SB 报告覆盖 | ✓ 7/7 种 (数据几乎为空) |
| SD 报告覆盖 | ✓ 5/6 种 (仅 1 个再营销 campaign) |
| 字段定义 | ✓ SP: 162 字段 (18 来源), SB+SD: 419 字段 (12 来源) |
| 行业基准调研 | ✓ 18+ 来源 (2025-2026 最新数据) |

### 1.2 分析能力 — 部分完成

| 脚本 | 状态 | 输入格式 | 行数 |
|------|:--:|------|------|
| `analyze_campaign.py` | ✓ 已有 | Console CSV | 146 |
| `analyze_targeting.py` | ✓ 已有 | Console CSV | 112 |
| `analyze_search_term.py` | ✓ 已有 | Console CSV | 353 |
| `analyze_placement.py` | ✓ 已有 | Console CSV | 141 |
| `analyze_ad_group.py` | ✗ 缺失 | — | — |
| `analyze_advertised_product.py` | ✗ 缺失 | — | — |
| `analyze_purchased_item.py` | ✗ 缺失 | — | — |
| `analyze_business_report.py` | ✗ 缺失 | — | — |
| `build_report.py` | ✓ 已有 | 4 JSON → Excel | 664 |

### 1.3 关键断裂点

1. **列名体系不兼容**: Console CSV 和 API xlsx 是两套中文列名。`__init__.py` 的 4 个映射仅支持 Console。
2. **数据路径断裂**: `load_data()` → `数据源/` (空) vs 实际数据在 `data/` (46+ 文件)。
3. **重复代码**: `_safe_num()` 重复 4 次, `_serialize()` 重复 2 次。
4. **品牌/竞品配置空白**: `PROTECTED_TERMS` 为空, 竞品列表为通用全球品牌。
5. **阈值未标定**: 所有 ACOS/ROAS 阈值是行业默认值, 未按 BJRYECLTD-US 毛利率调整。

---

## 2. 各报告分析价值矩阵

### 2.1 综合评分 (满分 10)

| # | 报告 | 数据量 | 分析价值 | 实现难度 | ROI 得分 | 已有脚本 |
|---|------|--------|---------|---------|---------|:--:|
| 1 | Campaign | 206 行 | 10/10 | 3/10 | **9.0** | ✓ |
| 2 | Targeting | 492 行 | 9/10 | 4/10 | **8.5** | ✓ |
| 3 | SearchTerm | 790 行 | 10/10 | 6/10 | **8.0** | ✓ |
| 4 | Placement | 457 行 | 8/10 | 3/10 | **8.5** | ✓ |
| 5 | **PurchasedItem** | 13 行 | 9/10 | 2/10 | **9.5** | ✗ |
| 6 | **AdvertisedProduct** | 189 行 | 8/10 | 4/10 | **8.0** | ✗ |
| 7 | **AdGroup** | 190 行 | 6/10 | 2/10 | **8.0** | ✗ |
| 8 | BusinessReport | 160 行 | 3/10 | 2/10 | **5.0** | ✗ |

**PurchasedItem 得分最高**: 仅 13 行数据, 几乎零实现难度, 但能揭示品牌光环效应 (当前 OtherSKU 销售额 $652 vs SameSKU $718)。

### 2.2 每个报告的业务价值

| 报告 | 核心回答的问题 | 典型优化动作 |
|------|-------------|------------|
| Campaign | 账户整体在赚钱还是亏钱? | 预算调配, 暂停浪费的活动 |
| Targeting | 哪种匹配类型最有效? | 关键词出价, 否定投放 |
| SearchTerm | 客户搜什么找到我们? | 收割高产词, 否定浪费词 |
| Placement | 哪个位置效率最高? | 广告位出价系数调整 |
| **PurchasedItem** | 光环效应有多强? Gateway ASIN 是谁? | **阻止误暂停 Gateway ASIN** |
| **AdvertisedProduct** | 每个 ASIN 的广告 ROI? | **暂停低效 ASIN, 加投高效 ASIN** |
| **AdGroup** | 活动内预算被谁垄断? | **拆分/合并广告组** |
| BusinessReport | B2B vs B2C 效率差异? | 企业购出价调整 (当前数据太少) |

### 2.3 行业基准速查 (Home & Garden / 枕头类目)

| 指标 | 健康值 | 可接受 | 危险 |
|------|--------|--------|------|
| ACOS | < 25% | 25-35% | > 35% |
| ROAS | > 4x | 2.5-4x | < 2.5x |
| CTR | > 0.5% | 0.3-0.5% | < 0.3% |
| CVR | > 10% | 5-10% | < 5% |
| TACoS | 10-15% | 15-25% | > 25% |

> 来源: Eightx 2026, Autron 2026, Teikametrics 2025。具体目标需根据 BJRYECLTD-US 产品毛利率标定。

---

## 3. 系统架构设计

### 3.1 目标架构

```
┌─────────────────────────────────────────────────────────┐
│                    数据获取层                              │
│  Sellfox API ──→ fetch_*.py ──→ advertise/data/*.xlsx    │
│  (SP 8 + SB 7 + SD 5 = 20 种报告)                        │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    数据加载层                              │
│  __init__.py (重构)                                       │
│  ├─ Console CSV 列映射 (4 映射, 保留兼容)                │
│  ├─ API xlsx 列映射 (8 SP + 12 SB/SD, 新增)              │
│  ├─ 格式自动检测 (CSV vs xlsx, Console vs API)           │
│  ├─ 路径检测 (数据源/ → data/ → 用户指定)                │
│  └─ utils.py ← _safe_num(), save_json(), money_clean()  │
│  thresholds.py ← 所有可配置阈值 (支持按账户 override)     │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    分析计算层                              │
│  ├─ analyze_campaign.py        ← 已有 ✓                  │
│  ├─ analyze_targeting.py       ← 已有 ✓                  │
│  ├─ analyze_search_term.py     ← 已有 ✓ (最完善)         │
│  ├─ analyze_placement.py       ← 已有 ✓                  │
│  ├─ analyze_ad_group.py        ← Phase 1 新建            │
│  ├─ analyze_advertised_product.py ← Phase 1 新建         │
│  ├─ analyze_purchased_item.py  ← Phase 1 新建 (最高ROI)  │
│  └─ analyze_business_report.py ← Phase 2 新建            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    报告生成层                              │
│  build_report.py (重构)                                   │
│  ├─ 去硬编码 (标题/周期/账户名 → 参数化)                 │
│  ├─ 新增 4 个 Sheet (AdGroup/AdProduct/Purchased/Biz)    │
│  ├─ 支持 CLI 参数: --account, --period, --output         │
│  └─ 跨报告集成分析 (光环效应/TACoS/跨期对比)              │
└─────────────────────────────────────────────────────────┘
```

### 3.2 新文件结构

```
advertise/
├── __init__.py                  ← 重构: 双格式支持
├── utils.py                     ← 新建: 共享工具函数
├── thresholds.py                ← 新建: 集中阈值管理
├── config/
│   └── bjryecltd-us.json        ← 新建: 账户级配置 (品牌词/竞品/毛利率)
├── analyze_campaign.py          ← 微调: API 适配
├── analyze_targeting.py         ← 微调: API 适配
├── analyze_search_term.py       ← 微调: 品牌/竞品配置外置
├── analyze_placement.py         ← 修复: 英文 placement 值支持
├── analyze_ad_group.py          ← 新建: Phase 1
├── analyze_advertised_product.py ← 新建: Phase 1
├── analyze_purchased_item.py    ← 新建: Phase 1 (最高 ROI)
├── analyze_business_report.py   ← 新建: Phase 2
├── build_report.py              ← 重构: 参数化 + 新 Sheet
├── out/                         ← 输出 (JSON + xlsx)
└── data/                        ← 输入 (xlsx from API)
```

---

## 4. 分阶段执行计划

| Phase | 目标 | 工期 | 依赖 |
|-------|------|------|------|
| **Phase 1** | 基础适配 + 最高 ROI 分析补齐 | 1-2 天 | — |
| **Phase 2** | 完整覆盖 + 报告生成器增强 | 1 天 | Phase 1 |
| **Phase 3** | 跨报告集成 + 高级分析 | 1-2 天 | Phase 2 |
| **Phase 4** | 自动化 + 持续优化 | 持续 | Phase 3 |

---

## 5. Phase 1: 基础适配与最高 ROI 补齐

**目标**: 让现有代码能消费 API 数据, 同时补齐投入产出比最高的 3 个分析脚本。

### Step 1.1: 基础设施重构 (1-2 小时)

**文件**: `advertise/utils.py` (新建), `advertise/thresholds.py` (新建), `advertise/__init__.py` (修改)

```
Task 1.1a: 提取 _safe_num() 到 utils.py
  - 从 4 个分析脚本移除内联副本, 统一 import
  - 确认所有调用点行为不变

Task 1.1b: 提取 save_json() 到 utils.py (与 __init__.py 统一)
  - analyze_search_term.py 的 _serialize() → 用 utils.save_json()

Task 1.1c: 新建 thresholds.py
  - 集中所有硬编码阈值
  - HIGH_ACOS_THRESHOLD, LOW_ROAS_THRESHOLD, MIN_ORDERS_HARVEST 等
  - 支持 import 后按账户 override

Task 1.1d: 修复数据源路径
  - load_data() 支持多路径回退: 数据源/ → data/ → 用户指定
  - 扩展文件检测 key 支持 API 命名格式
```

### Step 1.2: API 列名映射层 (1 小时)

**文件**: `advertise/__init__.py` (新增映射常量)

新增 8 个 API xlsx → snake_case 列映射:
- `CAMPAIGN_COLUMN_MAP_API` (26 列)
- `TARGETING_COLUMN_MAP_API` (30 列)
- `SEARCH_TERM_COLUMN_MAP_API` (32 列)
- `PLACEMENT_COLUMN_MAP_API` (26 列)
- `AD_GROUP_COLUMN_MAP_API` (27 列)
- `ADVERTISED_PRODUCT_COLUMN_MAP_API` (30 列)
- `PURCHASED_ITEM_COLUMN_MAP_API` (16 列)
- `BUSINESS_COLUMN_MAP_API` (26 列)

格式检测逻辑:
```python
def detect_format(df):
    # 检测第一行列名, 返回 "console" 或 "api"
    if "店铺" in df.columns:
        return "api"
    return "console"
```

### Step 1.3: 修复 Placement 分析 (30 分钟)

**文件**: `advertise/analyze_placement.py`

新增 API xlsx 格式的 placement 值映射:
```python
PLACEMENT_CATEGORY_API = {
    "Top of Search": "Top of Search",
    "Product Pages": "Product Pages",
    "Rest of Search": "Rest of Search",
    "产品页面": "Product Pages",
    "搜索首页顶部": "Top of Search",
    "搜索结果其他位置": "Rest of Search",
}
```

### Step 1.4: 新建 analyze_purchased_item.py (2 小时, 最高 ROI)

**输入**: `data/PurchasedItem_*.xlsx` (13 行 x 16 列)
**输出**: `out/purchased_item_analysis.json`

**分析内容**:
1. **Blended ACOS 计算** — 花费 / (SameSKU 销售 + OtherSKU 销售) × 100%
2. **广告 ASIN → 购买 ASIN 映射** — 交叉销售关系表
3. **Gateway ASIN 识别** — OtherSKU 销售额 / SameSKU 销售额 > 1.0 的 ASIN
4. **Halo Ratio** — 每个广告 ASIN 的光环效应强度
5. **暂停风险评估** — 如果因 ACOS 高想暂停某 ASIN, 标记其 Gateway 风险

**关键洞察** (基于实际数据):
- 同SKU 销售: ~$718 (SameSKU)
- 其他SKU 销售: ~$652 (OtherSKU)
- **真实总销售额: ~$1,370, 而非广告报告显示的 $718**
- 不看此报告会**低估 47% 的广告驱动销售额**

### Step 1.5: 新建 analyze_advertised_product.py (3 小时)

**输入**: `data/AdvertisedProduct_*.xlsx` (189 行 x 30 列, 8 个唯一 ASIN)
**输出**: `out/advertised_product_analysis.json`

**分析内容**:
1. **ASIN 效率排行** — 按 ACOS/ROAS 排序, 标记优胜/问题
2. **80/20 集中度分析** — 计算花费 Gini 系数
3. **Listing 质量诊断** — 高花费低转化 → Listing 问题; 高曝光低点击 → 主图问题
4. **Gateway ASIN 潜力** — 与 PurchasedItem 报告交叉验证
5. **暂停建议** — 花费 > $100 且 0 订单的 ASIN

### Step 1.6: 新建 analyze_ad_group.py (1.5 小时)

**输入**: `data/AdGroup_*.xlsx` (190 行 x 27 列)
**输出**: `out/ad_group_analysis.json`

**分析内容**:
1. **活动内组份额分析** — 每个组在父活动中的花费/订单占比
2. **组排行** — 前 20 优胜, 后 20 问题
3. **组结构诊断** — 统计每活动广告组数, 建议拆分/合并
4. **跨活动同名组检测** — 防止自我竞争

### Step 1.7: 账户配置 (30 分钟)

**新建**: `advertise/config/bjryecltd-us.json`
```json
{
  "brand": "如森",
  "brand_terms": ["senight", "snight", "如森"],
  "competitor_brands": ["(需补充)", "..."],
  "protected_terms": ["senight pillow", "如森 枕头"],
  "gross_margin": 0.45,
  "target_acos": 0.35,
  "thresholds": {
    "high_acos": 0.40,
    "low_roas": 2.5,
    "min_orders_harvest": 2,
    "min_clicks_negate": 15,
    "max_acos_harvest": 0.30
  }
}
```

### Phase 1 验收标准

- [ ] `__init__.py` 支持 API xlsx 格式 4 种核心报告加载
- [ ] `analyze_placement.py` 正确处理 API 英文 placement 值
- [ ] `utils.py` + `thresholds.py` 已提取, 4 个现有脚本无重复代码
- [ ] `analyze_purchased_item.py` 运行成功, 输出 Blended ACOS + Gateway ASIN
- [ ] `analyze_advertised_product.py` 运行成功, 输出 8 ASIN 效率排行
- [ ] `analyze_ad_group.py` 运行成功, 输出活动内组份额分析
- [ ] `python -m advertise.analyze_campaign` 使用 API 数据成功运行

---

## 6. Phase 2: 完整覆盖 + 报告生成器增强

**目标**: 补齐最后一种报告, 重构报告生成器, 支持 CLI 参数化。

### Step 2.1: 新建 analyze_business_report.py (1 小时)

- 复用 `analyze_placement.py` 框架 (90% 同构)
- 区分 Amazon Business 广告位的特殊列
- 当前数据极少 ($13.40 总花费), 保存模板等数据增长

### Step 2.2: 重构 build_report.py (3 小时)

**移除硬编码**:
- 标题 → CLI 参数 `--title`
- 周期 → 从数据自动推断
- 账户名 → CLI 参数 `--account`
- 阈值 → 从 `thresholds.py` 读取

**新增 Sheet**:
- Sheet 7: 品牌光环 (基于 PurchasedItem) — Blended ACOS, Gateway ASIN, 光环比
- Sheet 8: ASIN 效率 (基于 AdvertisedProduct) — ASIN 排行, 80/20 分布
- Sheet 9: AdGroup 结构 (基于 AdGroup) — 组内预算分配

**CLI 接口**:
```bash
python -m advertise.build_report \
  --account bjryecltd-us \
  --period 2026-06 \
  --output out/BJRYECLTD-US-广告分析报告-202606.xlsx
```

### Phase 2 验收标准

- [ ] `python -m advertise.build_report --account bjryecltd-us --period 2026-06` 成功
- [ ] 输出 Excel 含 9 个 Sheet (原 6 + 新 3)
- [ ] 无硬编码账户名/日期/路径

---

## 7. Phase 3: 跨报告集成 + 高级分析

**目标**: 从单报告分析升级到跨报告集成分析, 添加趋势和对比。

### Step 3.1: 跨报告集成分析 (2 小时)

**新建**: `advertise/analyze_cross.py`

**集成分析**:
1. **搜索词 → 关键词收割清单** (SearchTerm + Targeting)
   - 自动识别应转为精确匹配关键词的高产搜索词
2. **广告活动 × 广告位矩阵** (Campaign + Placement)
   - 每个活动在不同位置的热力图
3. **Gateway ASIN 最终判定** (AdvertisedProduct + PurchasedItem)
   - 综合光环效应和广告效率的 ASIN 分类
4. **真实 ACOS 纠正** (Campaign + PurchasedItem)
   - 为每个活动计算含光环效应的 Blended ACOS

### Step 3.2: 趋势分析与对比 (2 小时)

- **周度对比**: 本周 vs 上周关键指标变化量 (ΔSpend, ΔSales, ΔACOS)
- **月度趋势**: 6 月全月日粒度趋势线 (花费/ACoS/ROAS 时间序列)
- **异常检测**: 简单统计方法 (均值 ± 2σ) 检测异常波动

### Step 3.3: 决策日志 (1 小时)

- `out/decision_log.jsonl` — 追加式记录
- 每条记录: timestamp, analysis_type, key_findings, recommendations
- 基本 diff 对比: 上次运行 vs 本次运行的 5 桶分配变化

### Phase 3 验收标准

- [ ] `analyze_cross.py` 产出完整的 Gateway ASIN 判定 + 收割清单
- [ ] 周度对比报告产出 Δ 指标
- [ ] 决策日志累计记录, 可追溯优化历史

---

## 8. Phase 4: 自动化 + 持续优化

**目标**: 从分析到行动的闭环自动化。

### Step 4.1: 定时拉取 (1 小时)

- Cron/scheduled task: 每周自动拉取 8 种 SP 报告
- 使用 `SELLFOX_API/fetch_ad_reports.py`
- 存储到 `data/{YYYY-MM}/` 按月份组织

### Step 4.2: 否定词生成 (1 小时)

**新建**: `advertise/generate_negatives.py`
- 读取 `search_term_analysis.json`
- 输出 Amazon Bulk Operations 格式的否定词 CSV
- 可直接上传到 Amazon Ads Console

### Step 4.3: 阈值自适应 (2 小时)

- 基于历史数据 (至少 3 个月) 自动调整阈值
- 按季节/趋势修正 ACOS 期望

### Step 4.4: 通知与报告推送 (1 小时)

- 分析完成后生成摘要 Markdown
- 可选: 发送到钉钉/企微 (已有 DingTalk OIDC 基础设施)

---

## 9. SB/SD 扩展路线图

当前 BJRYECLTD-US 的 SB (0 行) 和 SD (1 个 VCPM campaign, 7 行) 数据极少。当数据量增长后:

### SB 特有指标分析

| 指标 | 定义 | 分析价值 |
|------|------|---------|
| NTB (New-to-Brand) | 过去 12 个月未购买过品牌的客户订单 | 衡量品牌扩展能力 |
| VCTR | 点击/可见展示 | 视频创意效率 |
| VTR | 完整观看/可见展示 | 视频内容质量 |
| VCPM | 每千次可见展示成本 | SB 视频的成本基准 |
| DPV | 商品详情页浏览 | 品牌旗舰店引流 |

### SD 特有指标分析

| 指标 | 定义 | 分析价值 |
|------|------|---------|
| ACoTS | 广告花费/总销售额 | SD 广告对整体销售的贡献 |
| ASoTS | 广告销售额/总销售额 | SD 广告的销售占比 |
| 费用类型 | vcpm / cpc | 成本模式选择 |
| 竞价优化 | SD_REACH / SD_CONVERSION | 优化目标跟踪 |

**触发条件**: 当月 SB/SD 花费 > $100 时激活此路线。

---

## 10. 风险与依赖

| 风险 | 影响 | 缓解 |
|------|------|------|
| 赛狐 API 限流 | 大批量拉取可能触发 40019 | 已内置 time.sleep(2), 可配置间隔 |
| IP 白名单变更 | 无法从新 IP 访问 API | 记录当前白名单 IP, 变更时更新 |
| API 字段变更 | 列名映射失效 | 字段参考文档有版本号, 每次拉取后验证 |
| BJRYECLTD-US 毛利率未知 | 阈值标定不准确 | 询问用户或用 Home & Garden 行业默认值 (45%) |
| SB/SD 数据过少 | 分析价值低 | 等数据量增长后激活 Phase SB/SD |

---

## 11. 总结: 四阶段的投入产出

| Phase | 工作量 | 新增能力 | 关键交付物 |
|-------|--------|---------|-----------|
| **Phase 1** | 1-2 天 | API 数据可消费 + 3 新分析脚本 | utils.py, thresholds.py, 3 个新脚本, API 映射 |
| **Phase 2** | 1 天 | 完整覆盖 + 参数化报告 | 重构 build_report.py, 9-sheet Excel |
| **Phase 3** | 1-2 天 | 跨报告集成 + 趋势 | analyze_cross.py, 决策日志 |
| **Phase 4** | 持续 | 自动化 + 闭环 | 定时拉取, 否定词生成, 自适应阈值 |

**即刻开始 Phase 1** — Step 1.1 (基础设施重构) → Step 1.2 (API 映射) → Step 1.4 (PurchasedItem 分析)。

---

## See also

- [SP 报告分析价值评估](../research/sp-report-analysis-value.md)
- [现有代码库审计](../research/existing-codebase-audit.md)
- [Amazon 广告最佳实践 2026](../research/amazon-ads-best-practices-2026.md)
- [SP 报告字段权威参考](../reference/sp-report-column-reference.md)
- [SB/SD 报告字段权威参考](../reference/sb-sd-report-column-reference.md)
- [赛狐 API 接入教训 (16 条)](../../SELLFOX_API/docs/lessons/2026-06-25-sellfox-integration-lessons.md)
