---
module: EN_API
date: 2026-08-31
problem_type: tooling_decision
component: tooling
severity: low
applies_when:
  - "需要批量把 EN 物料组中文名翻译成英文写入 item_group_translation"
  - "报关或对外文档需要款式级英文品名"
  - "DeepSeek 额度不足或不想用大模型翻译短品名"
tags:
  - en-api
  - erpnext
  - item-group
  - tmt
  - translation
  - customs
---

# EN 物料组英文翻译 — 腾讯云 TMT 管道

## Context

生产 EN（`erpnext.vilavi.cn`）在「产品」子树下为叶子物料组新增自定义字段 **`item_group_translation`**（标签：物料组翻译），用于报关等场景的英文款式名。2026-08 需对约 424 条节点批量中译英。

同期讨论过：腾讯混元 ChatTranslations（一次性 100 万 tokens 免费包）、DeepSeek（`customs_export.py` 已用于物料级报关品名）、开源 Google 翻译。同事最终用**开源 Google 翻译**先填入了生产；本仓库仍保留 **腾讯云 TMT** 脚本，供后续维护、增量更新和迁入 EN App。

## Guidance

### 范围（脚本 `select_targets`）

| 类型 | 数量（2026-08 生产） | 判定 |
|------|---------------------|------|
| `is_group=0` 叶子 | 410 | 含 398 个 `KS****` 款式 + 12 个非 KS 叶子 |
| `is_leaf_group=1` 叶子组 | 14 | `LGKS****`，与上集不重叠 |
| **合计** | **424** | 均在「产品」子树下 |

源文本：`item_group_name`（无则用 `name`）。目标字段：`item_group_translation`。

**命名约定**：`BetterRest`、`BBL` 等按普通中文词翻译，**不是**品牌保留。

### 推荐翻译通道

| 通道 | 适用 | 说明 |
|------|------|------|
| **腾讯云 TMT** | 款式级批量、可脚本化 | 每月 500 万字符免费；本批约 3000 字 |
| 开源 Google 翻译 | 同事已用于首批填生产 | 无云账号成本；质量/稳定性自担 |
| DeepSeek | 物料级报关品名（含面料/尺寸） | 见 `customs_export.py`，与款式级分开 |
| 混元 ChatTranslations | 有术语库/领域 Field 时 | 一次性 token 包，本场景性价比不如 TMT |

### API 密钥（CAM）

- 使用专用 CAM 用户 **`tmt-api-translation`** + 策略 **`QcloudTMTFullAccess`**
- **不要**用个人登录子账号（如 `fzh`）的主密钥给同事或 EN App
- 环境变量：`TENCENT_SECRET_ID`、`TENCENT_SECRET_KEY`、`TENCENT_TMT_REGION=ap-guangzhou`
- APPID 仅账号标识，脚本不需要

### 脚本用法

```bash
cd EN_API
uv run python translate_item_group_names.py --dry-run          # 默认：拉取 + TMT + Excel，不写 EN
uv run python translate_item_group_names.py --dry-run --fetch-only  # 无 TMT 密钥时仅中文名单
uv run python translate_item_group_names.py --apply            # 写回生产（需用户确认）
uv run python test_tmt_connectivity.py                         # 连通性冒烟
```

报告输出：`EN_API/out/物料组翻译_{fetch|dryrun|apply}_{timestamp}.xlsx`（汇总 + 明细）。

### SDK 坑（Lesson 56 级）

`pyproject.toml` 含 `tencentcloud-sdk-python` 与 `tencentcloud-sdk-python-tmt`，但当前精简包 **`TmtClient` 仅暴露 `ImageTranslateLLM`**，无 `TextTranslateBatchRequest`。脚本通过 `client.call("TextTranslate", {...})` 逐条调用（约 424 条 × 0.25s QPS 间隔 ≈ 5 分钟）。

## Why This Matters

- **款式级 vs 物料级**：`item_group_translation` 是款式中文名 → 英文；报关导出里的 DeepSeek 翻译是 DN 聚合物料名（去色后整段），粒度不同，应分开维护。
- **可复现**：TMT 管道有 dry-run Excel、入出对账、只写空字段逻辑，适合 Agent/同事后续增量。
- **安全**：专用 CAM 用户可轮换密钥而不影响控制台登录子账号。

## When to Apply

- 新增 KS/LGKS 叶子物料组需要英文款式名
- 批量修正 `item_group_translation`（先 `--dry-run` 审 Excel）
- 将翻译迁入 EN App（Settings 存 SecretKey，服务端调用 TMT；可与 DeepSeek 并行按场景分流）

## Examples

**TMT dry-run 样例（2026-08-28）**

| 中文 | 英文（TMT） |
|------|-------------|
| 三角靠枕 | Triangle pillow |
| BetterRest靠卧枕 | （机器译，非品牌保留） |
| 可组合扶手沙发 (LGKS0220) | （见 dry-run Excel） |

**凭证模板**（`EN_API/.env.example`）

```env
TENCENT_SECRET_ID=AKIDxxxxxxxx
TENCENT_SECRET_KEY=xxxxxxxx
TENCENT_TMT_REGION=ap-guangzhou
```

## Related

- `EN_API/AGENT_HANDOFF_物料组翻译.md` — Agent 入口
- `EN_API/docs/` — OKF 参考与教训
- `EN_API/customs_export.py` — 报关物料级 DeepSeek 翻译（另一粒度）
- `.claude/skills/item-group-translation/SKILL.md` — 触发词
