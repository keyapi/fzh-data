---
okf: v0.1
type: Handoff
title: Amazon 在售未配对自动匹配建议 — 子项目交接
tags: [amazon, pairing, matching, ml, sellfox, tongtu, handoff]
timestamp: 2026-08-14
---

# Amazon 在售未配对自动匹配建议

> 本子项目用于解决赛狐 Amazon 在线商品“在售但未配对”的人工审核辅助问题。当前分支是 **证据传播**（`feature/amazon-pairing-evidence`），以 `origin/main` 为底并入 PR 173 远端 `a64e6e0` 后继续；**不往 PR 173 推送**。只出建议工作簿，未调用任何赛狐配对写入接口。

> **先读**：[Amazon 在线商品配对的分层候选与运营确认流程](../docs/solutions/conventions/amazon-online-product-pairing-candidate-workflow.md)。
> 共享知识包（本 Agent / Codex 只读）：[docs/reference/](docs/reference/) 与 [knowledge/](knowledge/)。

## 0. 本分支 vs PR 173

| | PR 173 `feature/amazon-pairing-ltr` | 本分支 `feature/amazon-pairing-evidence` |
|---|---|---|
| 目标 | Gold/Silver 标签 + 四家族 LTR 试点 | 把已配对当活证据传播；可解释，不重训 LTR |
| 高可信门槛 | 只认 Gold A（通途别名唯一且与 EN 一致） | 当前已配对唯一目标（含 Silver）；冲突降级审核 |
| 本轮不做 | — | 不训练 LightGBM / embedding；不写赛狐 |

Codex 可继续占着 LTR worktree。缓存、catalog、模型文件在 gitignore 里，本机可从原 clone / LTR worktree 只读引用。

CLI 的 `--cache-workspace`（旧名 `--main-workspace`）指向**原 clone 目录**里的 gitignore 缓存（`missing_products/out/pairing_cache/`、映射表），**不是**要在 git `main` 上改代码。

## 1. 目标

- 输入：赛狐 Amazon 在线商品（已配对/未配对）、通途最新导出（SKU + SKU别名）、EN 物料/客户物料号、赛狐商品 SKU。
- 输出：给运营人员的配对建议表，尽量可导入赛狐（`import_product_msku_match` 模板），无法唯一确定的进入人工核对。
- 配对对象是**可销售在线商品**，不是 EN 生产主线；有库存半成品不必都有 listing。

## 2. 2026-08-14 快照

| 指标 | PR 173（Gold A） | 证据传播（活证据） |
|------|------|------|
| 当前在售未配对 | 3,557 | 3,557 |
| 高可信精确证据 | 87 | **722** |
| 智能候选审核 | 550 | **766** |
| 特殊对象暂缓 | 434 | **145** |
| 无可靠候选 | 2,486 | **1924** |
| 传播审计 | — | 入 3557 = 唯一 758 + 冲突 453 + 未覆盖 2346 |

3,557 条必须对账：`高可信 + 智能候选 + 特殊暂缓 + 无可靠候选 = 3,557`。不要和 8-11 快照的 4,407 混用。

活证据唯一来源（审计 `unique_by_evidence`）：customer_code 263、live_image 133、near_msku 119、live_asin 97、live_msku 73、live_parent_sku 56、live_parent_asin 17。Gold A 只用于训练清洗，**不是**高可信门槛。高可信 722 少于审计唯一 758，因为 combo 等仍进特殊暂缓。

黄金回归：`knowledge/golden-cases.yaml` + `tests/amazon_pairing/test_evidence.py`。`Danpinse-KS0388-blue-FBA`（Top1 `KS0388-HLRJLGBL-62x68x38-LIGHTBLUE`）/ `CEN665-Leaves-Grey-66-2`（`KS0244-CMGDTH-66x50-GREY`）/ `DanCA1534D9-Blue-153`（`KS0001-HLR-153-DEEPBLUE`）进高可信；`BAI31038N0A62927SX-2pcs-us` 进特殊暂缓。`LongHuxing-Foam-Lbai-100` 进无可靠候选：parent 全家未配对，禁止编造高可信。

## 3. 模型结论（PR 173 试点，本轮未重训）

试点家族为 `KS0001`、`KS0002`、`KS0248`、`KS0007`，按 MSKU/ASIN 连通分组切分，固定 seed 42。最终诚实评估为：

| 指标 | 结果 |
|------|------|
| family Top-1 / Top-2 | 94.79% / 99.51% |
| 原始 Candidate Recall@20 | 32.25% |
| Ranking Top-1 / Top-3 / Top-5 | 41.37% / 55.05% / 64.33% |
| MRR | 52.58% |
| production_ready | `false` |

排序评估中的 Recall@20 为 100%，是因为训练/评估排序器时注入了正样本。真正决定能否自动化的是 32.25% 的原始 Candidate Recall@20。LTR 只给「智能候选」打分，不能单独把行送进高可信。

## 4. 赛狐配对机制（已核实）

- **Amazon 在线产品配对**是独立机制：
  - 读取：`POST /api/order/api/product/pageList.json`，`match=true/false` 区分配对状态。
  - 写入：`POST /api/order/api/product/matchByMsku.json`、`matchByAsin.json`。
  - 导入模板：`import_product_msku_match`（列 `*MSKU、店铺名称、*商品SKU`）。
- **多平台配对**是另一套机制，Amazon 不走这套。
- `pageList` 支持精确过滤：`searchType`（sku/msku/asin/parentAsin/title/fnsku/commodityName）、`searchContent`、`onlineStatusList`、`match`、`shopIdList`、`marketplaceIdList`；`pageSize` 上限 200。

## 5. 现有入口

| 脚本 | 职责 |
|------|------|
| `python -m amazon_pairing.cli audit-propagation` | 只读：活证据覆盖率（入 N / 唯一 / 冲突 / 未覆盖） |
| `python -m amazon_pairing.cli suggest-active` | 四页只读审核工作簿（高可信=唯一硬证据） |
| `python -m amazon_pairing.cli build-labels` | Gold/Silver/Quarantine 标签审计（训练用） |
| `python -m amazon_pairing.cli snapshot-catalog` | EN 与赛狐普通产品候选快照 |
| `python -m amazon_pairing.cli train-pilot` | 四家族分类器与 LightGBM（本轮不要跑） |
| `python -m amazon_pairing.cli import-feedback <xlsx>` | 校验人工结论 |
| `missing_products/fetch_sellfox_pairing.py` | 拉取 Amazon + 多平台配对缓存 |

建议工作簿仍四页：高可信精确证据、智能候选审核、特殊对象暂缓、无可靠候选。

缓存默认：`--cache-workspace D:\Work\赛狐\Cursor` 下的 `missing_products/out/pairing_cache/`（2026-08-13）。catalog/labels/models 可指向 LTR worktree 的 `amazon_pairing/out/`。

## 6. 已落地分层方案

1. **活证据（本分支）**：同 MSKU 当前已配对（跨店跨站，含 Silver）→ 同 ASIN（默认跨站）→ parentSku/parentAsin 家族唯一 → 近邻 MSKU / EN 客户码（去 `NB/`、去 `-FBA`/`-us`/`-2`）→ 同 mainImage URL。多目标不一致 → 智能候选，不静默丢。
2. **意图分类**：`cover`/`foam` 禁止子串误杀。`with Removable Velvet Cover`、Foam 靠枕成品、KS0244 枕套族走 ordinary。真 `cover only` / `foam only` / 真套件才特殊暂缓。AFN 弱信号走成品先验。
3. **属性**：颜色/面料 + 美国床型/英寸/近寸（97≈100、152≈153）；床型/近寸与 EN `100x22x55` 这类三维尺寸兼容，不算可靠冲突。
4. **严格历史证据 / LTR**：Gold A 仍用于训练清洗。实验模型只在活证据用尽后给普通单品 Top-3；`production_ready=false`。
5. **主动弃权**：穷尽后仍空才进「无可靠候选」。
6. **反馈闭环**：工作簿只允许固定结论枚举。写入赛狐必须用户批准明确店铺/MSKU/赛狐 SKU 范围。

图片感知哈希 / VL / LLM 本轮只留接口说明，不进高可信。

## 7. 下一步

- 先让运营审阅高可信页和黄金 5 条；冲突页人工选一个。
- parent 全家未配对的 listing（如 LongHuxing-Foam 族）需要图片或人工，不能假装高可信。
- 达到候选召回门槛前不讨论自动写入。
- 直到用户明确批准具体店铺、MSKU 和赛狐 SKU 的导入范围前，不得调用 `matchByMsku`、`matchByAsin` 或任何多平台写接口。

## 8. 交接清单

1. 读本文档 + `docs/reference/evidence-sources.md` + `knowledge/golden-cases.yaml`。
2. 代码在 `D:\Work\赛狐\Cursor-amazon-pairing-evidence`（分支 `feature/amazon-pairing-evidence`）。不要 checkout 到已占用 `main` 的原 clone。
3. 日常分析默认用缓存；`--refresh` 前确认赛狐 API 配额。通途 MCP 禁止扫全库（5 次/分钟）。
4. 重跑：`uv run python -m amazon_pairing.cli audit-propagation` 再 `suggest-active`；黄金 MSKU 必须落在正确页。
5. 所有写入赛狐/EN 的动作必须先经用户确认。
