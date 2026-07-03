---
okf: v0.1
type: Research
title: Amazon SP 广告分析代码库审计
description: 现有代码逐文件盘点、数据流分析、差距识别、重构建议
tags: [amazon, advertising, audit, code-review]
created: 2026-07-02
sources:
  - advertise/__init__.py
  - advertise/analyze_campaign.py
  - advertise/analyze_targeting.py
  - advertise/analyze_search_term.py
  - advertise/analyze_placement.py
  - advertise/build_report.py
---

# Amazon SP 广告分析代码库审计

> 审计日期: 2026-07-02
> 审计范围: `advertise/` 下所有 Python 源文件 + 文档 + 实际数据文件
> 目的: 盘点现状、识别可复用与需重写的部分、发现死代码和重复逻辑、为 API 数据源接入做术前检查

---

## 1. 执行摘要

### 1.1 当前覆盖

| 维度 | 状态 |
|------|------|
| SP 报告类型覆盖 | 4 / 10 (仅 Campaign, Targeting, SearchTerm, Placement) |
| Console CSV 输入 | 已支持 (4 映射表) |
| API xlsx 输入 | **未支持** (列名不同, 需新映射表) |
| SP 分析脚本 | 4 (Campaign / Targeting / SearchTerm / Placement) |
| 报告生成器 | 1 (6-sheet Excel) |
| SB 分析 | 0 (数据文件已就绪但无分析) |
| SD 分析 | 0 (数据文件已就绪但无分析) |
| 决策日志持久化 | 未实现 (每次覆盖) |
| 多期对比 | 未实现 |
| TACoS | 未实现 (缺自然销售数据) |

### 1.2 关键发现

1. **列名断裂**: `__init__.py` 的 Console 列名映射与 API xlsx 列名**完全不同**。例如 Console 用 "花费" / API 用 "广告花费"。现有代码无法直接消费 API 数据。
2. **数据源路径错误**: `load_data()` 默认读取 `advertise/数据源/` (空), 实际数据在 `advertise/data/` (46+ 文件)。
3. **`_safe_num()` 重复 4 次**: 4 个分析脚本各有独立副本, 不共享。
4. **`_serialize()` 重复 2 次**: `__init__.py` 的 `save_json()` 和 `analyze_search_term.py` 的 `_serialize()` 功能重叠。
5. **无 API-format 分析能力**: 已通过 API 获取的 AdvertisedProduct / PurchasedProduct / AdGroup / Business 4 种报告无对应分析脚本。
6. **阈值全为行业默认值**: 未按 BJRYECLTD-US 实际数据标定。

---

## 2. 完整文件清单

### 2.1 Python 源文件 (6 个)

| # | 文件 | 行数 | 职责 | 独立可运行 |
|---|------|------|------|-----------|
| 1 | `advertise/__init__.py` | 221 | 数据加载 + 列映射 + 清洗 + JSON 输出 | — (库) |
| 2 | `advertise/analyze_campaign.py` | 146 | 广告活动层 ACOS/ROAS 排行, 预算利用率, 优胜/问题标记 | yes |
| 3 | `advertise/analyze_targeting.py` | 112 | 匹配类型表现, 投放 TOP/BOTTOM, 光环效应 | yes |
| 4 | `advertise/analyze_search_term.py` | 353 | 搜索词聚合 + 5 桶分类 + 语义分类 | yes |
| 5 | `advertise/analyze_placement.py` | 141 | 广告位 4 分类对比 + 出价建议 | yes |
| 6 | `advertise/build_report.py` | 664 | 读取 4 个中间 JSON → 6-sheet Excel + openpyxl 图表 | yes |

### 2.2 API 数据文件 (19 个, 位于 `advertise/data/`)

| # | 文件 | 行 x 列 | 类型 | 分析脚本 |
|---|------|---------|------|----------|
| 1 | `Campaign_2026-06-01_2026-07-01.xlsx` | 206 x 26 | SP Campaign | ❌ API 列名不兼容 |
| 2 | `Campaign_2026-06-29_2026-07-01.xlsx` | (短期) | SP Campaign | ❌ |
| 3 | `Targeting_2026-06-01_2026-07-01.xlsx` | — | SP Targeting | ❌ |
| 4 | `Targeting_2026-06-29_2026-07-01.xlsx` | — | SP Targeting | ❌ |
| 5 | `SearchTerm_2026-06-01_2026-07-01.xlsx` | — | SP SearchTerm | ❌ |
| 6 | `SearchTerm_2026-06-29_2026-07-01.xlsx` | — | SP SearchTerm | ❌ |
| 7 | `Placement_2026-06-01_2026-07-01.xlsx` | — | SP Placement | ❌ |
| 8 | `Placement_2026-06-29_2026-07-01.xlsx` | — | SP Placement | ❌ |
| 9 | `AdGroup_2026-06_JUN2026.xlsx` | 190 x 27 | SP AdGroup | ❌ 无脚本 |
| 10 | `AdvertisedProduct_2026-06_JUN2026.xlsx` | 189 x 30 | SP AdvertisedProduct | ❌ 无脚本 |
| 11 | `PurchasedItem_2026-06_JUN2026.xlsx` | 13 x 16 | SP PurchasedProduct | ❌ 无脚本 |
| 12 | `SP-BusinessReport_2026-06_JUN2026.xlsx` | 160 x 26 | SP Business | ❌ 无脚本 |
| 13-19 | `SB-*`, `SD-*` (共 12 文件) | — | SB / SD | ❌ 无脚本 |

### 2.3 文档文件

| # | 文件 | 状态 |
|---|------|------|
| 1 | `advertise/AGENT_HANDOFF.md` | v0.4, 最新 |
| 2 | `advertise/README.md` | v0.2, 略旧于 AGENT_HANDOFF |
| 3 | `advertise/docs/reference/column-mappings.md` | Console 格式 (4 映射) |
| 4 | `advertise/docs/reference/sp-report-column-reference.md` | API 格式, 8 种 SP 报告完整字段定义 |
| 5 | `advertise/docs/reference/data-sources.md` | 数据生态全图 |
| 6 | `advertise/docs/specs/2026-06-16-amazon-advertise-analysis-design.md` | v0.1-v0.2 设计 |
| 7 | `advertise/docs/roadmap.md` | Phase 1-3 已完成, Phase 4+ 待定 |
| 8 | `advertise/docs/lessons/lessons-learned.md` | 13 条教训 |

---

## 3. 逐文件审计

### 3.1 `advertise/__init__.py` — 数据加载模块

**路径**: `D:/Work/赛狐/Cursor/.claude/worktrees/sleepy-taussig-c2529b/advertise/__init__.py`

#### 输入

- **Console CSV 格式** (Amazon 广告后台中文导出)
  - 4 份报告文件, 存放在 `advertise/数据源/` 子目录中
  - 文件名检测关键字: `广告活动`, `投放`, `搜索词`, `广告位` (L118-123)
  - 支持 `.csv` 和 `.xlsx` 两种扩展名 (L150)
  - CSV 编码: UTF-8 (L159)

#### 列名映射 (4 个 dict, L10-115)

| 映射常量 | 目标格式 | 列数 | 报告类型 |
|----------|---------|------|---------|
| `CAMPAIGN_COLUMN_MAP` | 中文 Console → 英文 snake_case | 25 | 广告活动 |
| `TARGETING_COLUMN_MAP` | 中文 Console → 英文 snake_case | 26 | 投放 |
| `SEARCH_TERM_COLUMN_MAP` | 中文 Console → 英文 snake_case | 27 | 搜索词 |
| `PLACEMENT_COLUMN_MAP` | 中文 Console → 英文 snake_case | 18 | 广告位 |

#### Critical: Console vs API 列名差异

Console 和 API 导出的列名**完全不同**。以 Campaign 报告为例:

| 语义 | Console 中文 (已有映射) | API xlsx 中文 (无映射) |
|------|------------------------|----------------------|
| 花费 | `花费` → `spend` | `广告花费` |
| 展示量 | `展示量` → `impressions` | `广告曝光量` |
| 点击量 | `点击量` → `clicks` | `广告点击量` |
| 销售额 | `7天总销售额` → `sales_7d` | `广告销售额` |
| 订单数 | `7天总订单数(#)` → `orders_7d` | `广告订单量` |
| ACOS | `广告投入产出比 (ACOS) 总计` → `acos` | `ACoS` |
| ROAS | `总广告投资回报率 (ROAS)` → `roas` | `ROAS` |
| 状态 | `状态` → `status` | `广告活动运行状态` |
| 活动名称 | `广告活动名称` → `campaign_name` | `广告活动` |
| Portfolio | `广告组合名称` → `portfolio_name` | (无, 改由 portfolioId) |

**结论**: Console 映射和 API 映射是**两套独立的列名体系**。需要新增 4-8 个 API 列名映射常量, 或实现一个适配层。

#### 数据加载路径断裂

```python
# __init__.py L140-141:
if base_path is None:
    base_path = os.path.join(os.path.dirname(__file__), "数据源")
```

`advertise/数据源/` 目录为空 (只有 `.gitkeep` + `README.txt`)。实际数据文件位于 `advertise/data/`。Agent 按照 AGENT_HANDOFF.md 指引走到数据源目录将找不到任何文件。

#### 数据清洗逻辑 (L166-188)

- L167-173: 金额列清洗 (`str.replace(r"[$,\s]", "", regex=True)`) — 处理 Console CSV 的 `$1,234.56` 格式
- L176-182: 百分比列归一化 (中位数 > 1 则除以 100) — 处理 Console 的百分比整数问题 (Lesson 2)
- L185-187: 日期列标准化 (`pd.to_datetime`)

API xlsx 数据**不需要**这些清洗: 金额已经是 `float64`, 百分比已经是 `float64` 小数。直接加载即可。

#### `save_json()` (L195-220)

- 输出路径: `advertise/out/` (默认)
- 处理 numpy/pandas 类型的 JSON 序列化

#### 已知局限

- Console-only 列名映射, 不兼容 API 格式 (L10-115)
- 数据源路径默认指向空目录 (L140-141)
- 金额清洗假设 `$` 前缀, API 数据不需要 (L167-173)
- 百分比归一化逻辑对 API 数据可能误操作 (API 数据已是小数, 中位数 < 1, 不会触发除法, 但逻辑冗余)
- `_FILE_PATTERNS` 关键字检测依赖中文文件名 (L118-123), 无法识别 `Campaign_2026-*.xlsx` 等英文命名

---

### 3.2 `advertise/analyze_campaign.py` — 广告活动分析

**路径**: `D:/Work/赛狐/Cursor/.claude/worktrees/sleepy-taussig-c2529b/advertise/analyze_campaign.py`

#### 输入

- 调用 `load_data()` 从 `数据源/` 加载 → 选择 `reports["campaign"]` (L130-131)
- 期望字段: `campaign_name`, `status`, `portfolio_name`, `spend`, `sales_7d`, `orders_7d`, `clicks`, `impressions`, `acos`, `roas`, `ctr`, `cpc`, `budget`

#### 输出

- JSON 到 `advertise/out/campaign_analysis.json` (L135)
- 结构:
  ```python
  {
    "summary": {total_spend, total_sales_7d, total_orders_7d, total_clicks,
                total_impressions, overall_acos, overall_roas, overall_ctr,
                campaign_count},
    "ranking": [{campaign_name, status, portfolio_name, spend, sales_7d,
                 acos, roas, orders_7d, clicks, impressions, ctr, cpc, budget,
                 budget_utilization, flag}],
    "portfolio": [{portfolio_name, spend, sales_7d, ...}],
    "status_distribution": {str(status): count},
    "winners": [...],   // ACOS < 0.15 & sales > 0
    "problems": [...],  // ACOS > 0.50 或 ROAS < 1.0
    "thresholds": {high_acos: 0.50, low_roas: 1.0},
  }
  ```

#### 阈值与配置

| 常量 | 行号 | 值 | 含义 |
|------|------|---|------|
| `HIGH_ACOS_THRESHOLD` | L10 | `0.50` | ACOS > 50% 标记为高风险 |
| `LOW_ROAS_THRESHOLD` | L11 | `1.0` | ROAS < 1.0 标记为问题 |
| (硬编码) | L77 | `0.15` | ACOS < 15% 标记为"优胜" |

#### 已知问题

1. **预算利用率计算 (L64-66)**: 日预算 x 30 近似月预算, 但实际报告期可能不是 30 天
2. **硬编码优胜阈值 (L77)**: `acos < 0.15` 标记"优胜", 未提取为可配置常量
3. **问题标记互斥 (L77-80)**: 一个活动同时满足"优胜"和"问题"时 flag 会被覆盖 (先写"优胜", 后写"高风险/问题"覆盖)
4. **`_safe_num()` 重复** (L14-16): 与其余 3 个分析脚本中的实现完全相同

#### API 兼容性评估

API xlsx 的 Campaign 数据 (206 行 x 26 列) 语义一致, 仅列名不同。需要:
- 新增 `CAMPAIGN_COLUMN_MAP_FROM_API` 映射 (中文 API → snake_case)
- 调整 `load_data()` 或写新的加载函数

---

### 3.3 `advertise/analyze_targeting.py` — 投放层分析

**路径**: `D:/Work/赛狐/Cursor/.claude/worktrees/sleepy-taussig-c2529b/advertise/analyze_targeting.py`

#### 输入

- `reports["targeting"]` DataFrame (L98-99)
- 期望字段: `targeting`, `match_type`, `campaign_name`, `spend`, `sales_7d`, `orders_7d`, `clicks`, `impressions`, `acos`, `roas`, `ctr`, `cpc`, `top_search_is`, `advertised_sku_sales_7d`, `other_sku_sales_7d`, `advertised_sku_units_7d`, `other_sku_units_7d`, `conversion_rate_7d`

#### 输出

- JSON 到 `advertise/out/targeting_analysis.json` (L102)

#### 硬编码逻辑

- L52: `spend > 1` 判定为"有花费但零销售"的底线
- L52: `sales_7d.fillna(0) == 0` 零销售判定
- L49: top_targets 固定取前 20
- L53: bottom_targets 固定取前 20

#### 已知局限

- **无关键词 vs 商品投放分类**: 投放报告混合了关键词投放和商品投放 (ASIN targeting), 但代码不做区分
- **`top_search_is` (搜索结果顶部展示份额)** 仅在 L45 被列为可用列, 但分析中**未使用** (只是被包含在排序结果中)
- **零转化阈值 (L52)**: `spend > 1` 是 hardcoded, 未提取为常量

---

### 3.4 `advertise/analyze_search_term.py` — 搜索词分析 (最复杂)

**路径**: `D:/Work/赛狐/Cursor/.claude/worktrees/sleepy-taussig-c2529b/advertise/analyze_search_term.py`

#### 输入

- `reports["search_term"]` DataFrame (L330-331)
- 核心字段: `search_term` (必须), 其余可选的 `spend`, `sales_7d`, `orders_7d`, `clicks`, `impressions`, 等

#### 数据流

```
原始 df (～5,000 rows, multi-campaign same search_term spread)
  → Step 0: 数值化 + 日期范围检查 (L131-141)
  → Step 1: GROUP BY search_term 聚合 (L164)
  → Step 2: 计算统一指标 CTR/CPC/ACoS/ROAS/CVR (L168-180)
  → Step 3: 语义分类 (brand/competitor/junk/category/long-tail) (L183)
  → Step 4: 5 桶分类 (L189-235)
  → Step 5: 分类统计 (L260-273)
  → 序列化输出 JSON
```

#### 5 桶分类优先级顺序 (L189-235)

```
Protect > Harvest > Negate > Ignore > Monitor (default)
```

注意: Protect 优先级最高 (不会被其他桶覆盖), 但 `PROTECTED_TERMS` 当前为空集 (L45)。

#### 阈值配置 (全部可配置常量, L24-38)

| 常量 | 值 | 用途 |
|------|---|------|
| `MIN_ORDERS_HARVEST` | `2` | Harvest: 最少订单数 |
| `MAX_ACOS_HARVEST` | `0.30` | Harvest: 最大 ACOS |
| `MIN_CLICKS_NEGATE` | `15` | Negate: 最少点击量 |
| `MIN_SPEND_NEGATE` | `2.0` | Negate: 最低花费 |
| `MAX_CLICKS_MONITOR` | `15` | Monitor: 点击量上限 |
| `MAX_SPEND_IGNORE` | `1.0` | Ignore: 花费上限 |
| `MAX_CLICKS_IGNORE` | `5` | Ignore: 点击量上限 |
| `ATTRIBUTION_WINDOW_DAYS` | `7` | SP 归因窗口 |
| `MIN_REPORT_DAYS` | `14` | 最小报告天数 |

#### 语义分类规则

| 分类 | 方法 | 状态 |
|------|------|------|
| `BRAND_TERMS` (L48) | 包含 "senight", "snight", "如森" | 3 个词 |
| `COMPETITOR_BRANDS` (L49-55) | 包含 Tempur, Sealy, Simmons, Purple, Casper 等 | 35 个品牌, 通用家居品牌 (非 BJRYECLTD-US 特化) |
| `JUNK_ROOTS` (L56-70) | 包含 cheap, free, used, pet, car 等不相关词根 | 约 60 个词根 |
| `CATEGORY_ROOTS` (L71-80) | 包含 pillow, cushion, mattress, memory foam 等 | 约 50 个品类词根 |
| 长尾词 (L104) | `len(words) >= 4` | 启发式 |
| 其他 | 默认 | — |

#### 已知问题

1. **`PROTECTED_TERMS` 为空** (L45): 品牌词保护未配置, 所有词都走正常分类
2. **竞品词列表过于通用** (L49-55): 包含大量全球品牌 (Tempur/Sealy/Purple/Casper 等), 未针对 BJRYECLTD-US 调整
3. **`_serialize()` 与 `save_json()` 重叠** (L109-124): `__init__.py` 的 `save_json()` 已处理 numpy 序列化, 这里又实现了一次
4. **分类规则基于英文字符串包含**, 可能产生误伤: 例如搜索 "sealy pillow" 会被匹配为品类词 (因为 "pillow" 在 CATEGORY_ROOTS 中) 而非竞品词 (因为 sealy 先匹配)
5. **`classify_term_category()` 匹配顺序是决定性的**: 品牌 > 竞品 > 不相关 > 品类 > 长尾 > 其他。这意味着包含竞品品牌名的品类词 (如 "tempur pillow") 会被分类为竞品词而非品类词
6. **报告期检查 (L141)**: `max_date - min_date + 1` 假设连续日期, 不处理日期空缺

#### API 兼容性

搜索词 API 数据语义一致, 但列名不同。需要新映射。

---

### 3.5 `advertise/analyze_placement.py` — 广告位分析

**路径**: `D:/Work/赛狐/Cursor/.claude/worktrees/sleepy-taussig-c2529b/advertise/analyze_placement.py`

#### 输入

- `reports["placement"]` DataFrame (L128-129)
- 核心字段: `placement` (中文广告位名称)

#### 广告位分类逻辑 (L14-36)

```python
PLACEMENT_CATEGORY = {
    "亚马逊站内的搜索结果顶部": "Top of Search",
    "亚马逊站内的商品页面": "Product Pages",
    "亚马逊站内搜索结果的其余位置": "Rest of Search",
    "亚马逊站外": "站外",
}
```

**Critical**: 这些是 **Console 导出的中文值**。API xlsx Placement 报告的 placement 列值不同 —
API 格式的 Placement 值是英文的: `"Top of Search"`, `"Product Pages"`, `"Rest of Search"`, 不会被 `classify_placement()` 正确映射。
结果: 所有 API placement 值都会被归类为 "其他"。

#### 出价调整建议逻辑 (L97-107)

| 条件 | 建议 |
|------|------|
| ACOS < 0.20 AND CVR > 0.05 | 建议提高出价 10-20% |
| ACOS > 0.40 | 建议降低出价 15-30% 或暂停 |
| CVR < 0.02 AND spend > $100 | 检查广告位素材相关性 |
| 其他 | 维持当前出价, 继续观察 |

这些阈值 (0.20/0.05/0.40/0.02/100) 全部 hardcoded, 未提取为常量。

#### 已知局限

- 不处理 Amazon Business placement 分类 (API 数据中 business placement 是独立的 `Product Pages (Amazon Business)` 行)
- placement 分类依赖精确中文匹配, 对 API 英文值失效

---

### 3.6 `advertise/build_report.py` — Excel 报告生成器

**路径**: `D:/Work/赛狐/Cursor/.claude/worktrees/sleepy-taussig-c2529b/advertise/build_report.py`

#### 输入

- 4 个 JSON 文件 (L120-123):
  - `out/campaign_analysis.json`
  - `out/targeting_analysis.json`
  - `out/search_term_analysis.json`
  - `out/placement_analysis.json`

#### 输出

- `out/如森US-广告分析报告.xlsx`, 6 个 Sheet (L129-151):
  1. **总览** — 关键数字卡片 + 数据一致性校验 + 核心发现
  2. **广告活动** — 排行表 + ACOS vs ROAS 散点图
  3. **投放表现** — 匹配类型 + 光环效应 + 零转化投放
  4. **搜索词洞察** — 5 桶分类概览 + Harvest/Negate/Monitor 清单 + 搜索词分类饼图
  5. **广告位效率** — 四位对比 + CPC/CTR/CVR/ACOS 柱状图 + 出价建议
  6. **行动建议** — 按优先级排序的操作清单 + 周优化节奏

#### 硬编码内容

| 项 | 行号 | 值 |
|----|------|---|
| 报告标题 | L179 | `Amazon 广告分析报告 — 如森US 近30天` |
| 数据周期 | L180 | `2026-05-17 ~ 2026-06-15 \| 账户: A2.如森跨境电商` |
| 行业对比阈值 | L232-237 | ACOS < 25% 健康, 25-35% 可接受, >35% 偏高; ROAS > 3x 良好 |
| 周优化节奏 | L648-652 | 周一到周五的 4 条建议 |
| 文件命名 | L154 | `如森US-广告分析报告` |
| 图表散点上限 | L296 | `ranking[:37]` — 硬编码上限 |
| 搜索词 TOP50 | L437 | `monitors[:50]` — 观察列表截断 |

#### 已知问题

1. **硬编码标题/周期/账户名 (L179-180)**: 每次运行前需手动修改
2. **图表数据范围硬编码 (L296)**: `ranking[:37]` 假设最多 37 个活动
3. **`build_report.py` 有 `@unplugged` 问题**: L554 出现 `"词组否���谨慎"` — 最后一个字符被截断 (编码问题)
4. **文件占用处理 (L156-163)**: 简单的命名序号递增, 不处理跨进程锁

---

## 4. 数据流全景

### 4.1 当前数据流 (Console CSV)

```
Amazon Ads Console (浏览器导出)
    │
    ▼
advertise/数据源/*.csv|*.xlsx  (中文列名, $前缀金额, %整数)
    │
    ▼
__init__.py.load_data()
    ├─ _detect_report() — 文件名关键词识别
    ├─ rename(CMAP)           — 中文 → 英文
    ├─ money clean            — $删除
    ├─ pct normalize          — /100
    ├─ date parse             — pd.to_datetime
    │
    ▼
{report_type: DataFrame} dict → 4个分析函数
    │
    ▼
out/*.json (中间产物)
    │
    ▼
build_report.py → out/如森US-广告分析报告.xlsx (6 sheets)
```

### 4.2 API 数据流 (未连接)

```
赛狐 API / Sellfox API
    │
    ▼
advertise/data/*.xlsx  (API中文列名, float64金额, float64百分比, 日期已格式)
    │
    (gap: no loader for API format)
    │
    (gap: no column map for API format)
    │
    (gap: no analysis scripts for AdvertisedProduct/PurchasedProduct/AdGroup/Business)
```

### 4.3 数据流断裂点

| 断裂点 | 位置 | 修复方案 |
|--------|------|---------|
| 数据源路径 | `__init__.py:140` | 支持 `advertise/data/` 路径或可配置 |
| Console 列名映射 | `__init__.py:10-115` | 新增 API 列名映射常量 |
| 文件名识别 | `__init__.py:118-123` | 扩展关键字列表支持 API 文件命名 |
| 金钱/百分比清洗 | `__init__.py:167-182` | API 数据不需要, 添加格式检测 |
| Placement 分类 | `analyze_placement.py:14-36` | 新增英文值映射 |
| 4 份报告不足 | 全局 | 新增 AdvertisedProduct / PurchasedProduct / AdGroup / Business 分析 |

---

## 5. 代码质量审计

### 5.1 重复代码

| 模式 | 出现次数 | 文件 | 建议 |
|------|---------|------|------|
| `_safe_num()` | 4 | `analyze_campaign.py:14-16`, `analyze_targeting.py:8-10`, `analyze_search_term.py:83-84`, `analyze_placement.py:8-10` | 提取到 `__init__.py` 或新建 `advertise/utils.py` |
| `_serialize()` vs `save_json()` | 2 | `analyze_search_term.py:109-124` vs `__init__.py:195-220` | 统一用 `save_json()` |
| numpy 值四舍五入循环 | ~10 | 所有 4 个分析脚本 | 提取工具函数 |

### 5.2 硬编码值分布

| 文件 | 硬编码数量 | 示例 |
|------|-----------|------|
| `analyze_campaign.py` | 3 | HIGH_ACOS=0.50, LOW_ROAS=1.0, winner ACOS=0.15 |
| `analyze_targeting.py` | 2 | min_spend=1, top_n=20 |
| `analyze_search_term.py` | 9 | 全部已提取为常量 (好评) |
| `analyze_placement.py` | 10+ | ACOS阈值(0.20/0.40), CVR阈值(0.02/0.05), spend阈值(100), 出价调整幅度(10-20%/15-30%) |
| `build_report.py` | 15+ | 标题, 周期, 行业基准, 操作文本, 截断限制 |

### 5.3 死代码路径

1. `analyze_campaign.py:69`: `budget_utilization` 使用 `df["budget"] * 30` 做近似, 但从 API 报告期计算更准确
2. `analyze_search_term.py:38`: `MAX_CLICKS_MONITOR = 15` — 定义了但未在分类逻辑中使用 (Monitor 是 else 分支, 不需要上限检查)
3. `analyze_campaign.py:127`: `targeting_type` 在 Campaign 列映射中定义但 `analyze()` 函数中未使用

---

## 6. 阈值标定建议 (BJRYECLTD-US)

所有阈值当前都是行业默认值, 需要根据 BJRYECLTD-US 实际数据标定:

| 阈值 | 当前值 | 标定问题 |
|------|--------|---------|
| `HIGH_ACOS_THRESHOLD` | 0.50 | 需要知道 BJRYECLTD-US 毛利率。如果毛利率 40%, 则 ACOS 40% 即盈亏平衡 |
| `MAX_ACOS_HARVEST` | 0.30 | 应设为 `毛利率 - 5%` (留缓冲) |
| `MIN_ORDERS_HARVEST` | 2 | 需看实际订单分布。如果高单价产品 (如 $100+ 床垫), 1 单可能就足够信号 |
| `MIN_CLICKS_NEGATE` | 15 | 需看产品的平均 CPC。$0.3 CPC 时 15 点击 = $4.50, 可能太保守; $1.5 CPC 时 15 点击 = $22.50, 合适 |
| `MIN_SPEND_NEGATE` | 2.0 | 取决于 AOV (平均客单价) |
| `COMPETITOR_BRANDS` | 35 全球品牌 | 需替换为 BJRYECLTD-US 已知竞品 (如有优麦云/卖家精灵竞品数据更好) |
| `BRAND_TERMS` | 3 个 (senight/snight/如森) | 确认品牌词拼写 (是否是 senight?) 并补全 |
| `PROTECTED_TERMS` | 空 | 必须填充 — 品牌词 + 高转化战略词 |
| Placement 出价建议 | ACOS < 0.20 / > 0.40 | 需根据毛利率调整 |

---

## 7. 缺失分析与重构建议

### 7.1 急需新增的分析脚本

| 优先级 | 报告 | 数据已就绪 | 分析方向 |
|--------|------|-----------|---------|
| P0 | 列名映射层 | — | 统一 Console + API 双格式输入 |
| P0 | Advertised Product | 189 行 x 30 列 | ASIN 级盈利能力, 单品 ACOS, SKU 贡献排名 |
| P1 | Ad Group | 190 行 x 27 列 | 广告组表现, 自动/手动广告组效率对比 |
| P1 | Business Report | 160 行 x 26 列 | B2B 广告位效率, 企业客户转化特点 |
| P2 | Purchased Product | 13 行 x 16 列 | 品牌光环明细, 广告 ASIN → 购买 ASIN 流向 |

### 7.2 建议的重构目标

1. **统一列名映射层**: 新建 `advertise/column_maps.py`, 包含 Console 和 API 两套映射, 加格式自动检测
2. **提取共享工具**: 新建 `advertise/utils.py`, 提取 `_safe_num()`, numpy 序列化, 货币清洗, 百分比归一化
3. **数据源容错**: `load_data()` 支持多路径回退 (`数据源/` → `data/` → 用户指定)
4. **阈值集中管理**: 新建 `advertise/thresholds.py`, 所有阈值集中配置, 支持按账号 override
5. **动态品牌词管理**: `PROTECTED_TERMS`, `BRAND_TERMS`, `COMPETITOR_BRANDS` 移到外部配置文件 (JSON/YAML)
6. **决策日志持久化**: `out/decision_log.jsonl` 追加式记录, 每次分析不覆盖

### 7.3 API 列名映射快速方案

当前 `__init__.py` 的映射对应 Console 中文列名, API 中文列名不同。参考文档 `sp-report-column-reference.md` 已有 API 格式的完整列名清单 (赛狐中文名 vs API 字段名)。

需要新增的映射表 (以 API xlsx 为输入):

```
CAMPAIGN_COLUMN_MAP_FROM_API:
  "广告花费" → spend, "广告曝光量" → impressions, "广告点击量" → clicks,
  "广告销售额" → sales_7d, "广告订单量" → orders_7d, "ACoS" → acos, ... (26列)

TARGETING_COLUMN_MAP_FROM_API:
  "投放" → targeting, "匹配类型" → match_type, ... (30列)

SEARCH_TERM_COLUMN_MAP_FROM_API:
  "用户搜索词" → search_term, ... (32列)

PLACEMENT_COLUMN_MAP_FROM_API:
  "广告位" → placement, ... (26列)

ADVERTISED_PRODUCT_COLUMN_MAP_FROM_API:
  "asin" → asin, "sku" → sku, ... (30列)

PURCHASED_ITEM_COLUMN_MAP_FROM_API:
  "ASIN" → advertised_asin, "SKU" → advertised_sku, "其他ASIN" → purchased_asin, ... (16列)

AD_GROUP_COLUMN_MAP_FROM_API:
  "广告组" → ad_group_name, ... (27列)

BUSINESS_COLUMN_MAP_FROM_API:
  "广告位" → placement, ... (26列)
```

### 7.4 Column-mappings.md vs sp-report-column-reference.md 关系

| 维度 | `column-mappings.md` | `sp-report-column-reference.md` |
|------|---------------------|-------------------------------|
| 数据格式 | **Console** 中文导出 | **API** 中文导出 (赛狐) |
| 报告数 | 4 (Campaign/Targeting/SearchTerm/Placement) | 8 (含 AdvertisedProduct/PurchasedProduct/AdGroup/Business) |
| 列映射 | 中文 → 英文 snake_case (代码用) | 中文 → 官方 API 字段名 + 数据类型 + 来源 |
| 来源标注 | 无 (推断自数据文件) | 21 个来源 (含 8 个 Amazon 官方 URL) |
| 验证状态 | 以实际数据文件验证 | 以 Amazon 官方文档逐列验证 (Lesson 13) |
| 代码同步 | 与 `__init__.py` 同步 | 与代码无关 (纯文档参考) |

**结论**: `sp-report-column-reference.md` 是更权威的字段定义文档, 应用作 API 格式列名映射的源码。`column-mappings.md` 覆盖的是 Console 格式的旧映射, 应更新或合并。

---

## 8. 附录: 文件内容速查表

### 8.1 Console CSV Campaign 报告列 (有映射)

`__init__.py` L10-36 的 `CAMPAIGN_COLUMN_MAP`:
```
开始日期 → start_date, 结束日期 → end_date, 广告组合名称 → portfolio_name,
广告活动类型 → campaign_type, 广告活动名称 → campaign_name, 零售商 → retailer,
国家/地区 → country, 状态 → status, 货币 → currency, 预算 → budget,
定位类型 → targeting_type, 竞价策略 → bidding_strategy, 展示量 → impressions,
去年曝光量 → impressions_dedup, 点击量 → clicks, 去年点击量 → clicks_dedup,
点击率 (CTR) → ctr, 花费 → spend, 去年支出 → spend_dedup,
单次点击成本 (CPC) → cpc, 去年每次点击成本(CPC) → cpc_dedup,
7天总订单数(#) → orders_7d, 广告投入产出比 (ACOS) 总计 → acos,
总广告投资回报率 (ROAS) → roas, 7天总销售额 → sales_7d
```

### 8.2 API xlsx Campaign 报告列 (无映射, 需新增)

实际从 `data/Campaign_2026-06-01_2026-07-01.xlsx` 读取 (26 列):
```
店铺, 日期, 广告活动, 定位类型, 广告花费, 广告曝光量, 广告点击量,
CPC, 广告点击率, 广告转化率, ACoS, ROAS, 广告订单量, 本广告产品订单量,
其他产品广告订单量, 广告销售额, 本广告产品销售额, 其他产品广告销售额,
广告销量, 本广告产品销量, 其他产品广告销量, 广告活动开始时间,
广告活动结束时间, 广告活动运行状态, 广告组合ID, 广告活动ID
```

### 8.3 SB / SD 数据文件

`advertise/data/` 中已存在 12 个 SB/SD 文件, 均无分析脚本:

- SB: Campaign, AdGroup, AdProduct, Placement, Targeting, SearchTerm, PurchasedItem (7 文件)
- SD: Campaign, AdGroup, AdProduct, Targeting, PurchasedItem (5 文件)

这些是 Amazon Sponsored Brands 和 Sponsored Display 的数据。SB 支持视频广告 (creativeType: video), 归因窗口不同 (14 天)。这是未来扩展方向, 但当前优先级低于 SP 的补齐。

---

## 9. 总结: "是什么/缺什么/要改什么"

### 是什么

已有 4 个高质量 SP 分析脚本 (Campaign/Targeting/SearchTerm/Placement), 一个 6-sheet Excel 报告生成器, 和一套 Console CSV 数据加载基础设施。搜索词分析的 5 桶分类设计对行业标准 (Trellis/WisePPC) 的照做得很好。

### 缺什么

1. **API 格式数据加载** — 已通过 Sellfox API 获取 19 个数据文件, 但无代码可加载
2. **4 种 SP 报告分析** — AdvertisedProduct, PurchasedProduct, AdGroup, Business 都有数据但无脚本
3. **SB/SD 分析** — 12 个数据文件闲置
4. **品牌词/竞品词配置** — PROTECTED_TERMS 为空, 竞品列表不对
5. **决策日志持久化** — 每次覆盖
6. **多期对比** — 环比/同比

### 要改什么

1. **`__init__.py`**: 新增 API 列名映射, 修复数据源路径, 格式自动检测
2. **提取共享工具**: `_safe_num()` 等去重
3. **新建 4 个分析脚本**: `analyze_advertised_product.py`, `analyze_purchased_product.py`, `analyze_ad_group.py`, `analyze_business.py`
4. **阈值标定**: 所有 ACOS/ROAS 阈值需按 BJRYECLTD-US 毛利率重新设定
5. **`build_report.py`**: 去硬编码 (标题/周期/账户名), 加新 Sheet
6. **品牌/竞品/战略词外置**: JSON 配置文件, 每次分析前更新

## See also

- [数据源全图](../reference/data-sources.md) — SP 报告类型完整性
- [字段权威参考](../reference/sp-report-column-reference.md) — API 格式列定义
- [列名映射](../reference/column-mappings.md) — Console 格式列映射
- [设计文档](../specs/2026-06-16-amazon-advertise-analysis-design.md) — 架构决策
- [经验教训](../lessons/lessons-learned.md) — 13 条历史踩坑
- [路线图](../roadmap.md) — Phase 4+ 规划
