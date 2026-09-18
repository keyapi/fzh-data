# EN 物料组英文翻译 — Agent 交接

> **脚本**: `translate_item_group_names.py`、`test_tmt_connectivity.py`
> **人读**: [README.md](README.md) · OKF: [docs/](docs/)

## 1. 业务背景

生产 EN Item Group 有自定义字段 **`item_group_translation`**（物料组翻译），存款式级英文名称，供报关等使用。

- **范围**：「产品」子树下 `is_group=0` 叶子 + `is_leaf_group=1` 的 LGKS 叶子组（2026-08 共 **424** 条，不重叠）
- **源文**：`item_group_name`（中文）
- **状态（2026-08-31）**：同事用开源 Google 翻译已写入生产；本仓库 **TMT 管道保留**，供增量/修正/迁入 EN App

`BetterRest`、`BBL` 等**不是品牌**，按普通词翻译。

## 2. 管道

```
GET Item Group (prod, limit_page_length=0)
  → select_targets: 产品子树 + (is_group=0 OR is_leaf_group=1)
  → 可选: 腾讯云 TMT TextTranslate (zh→en, client.call)
  → Excel 报告 (汇总 + 明细)
  → --apply: PUT item_group_translation（跳过已有相同译文）
```

## 3. 命令

```bash
cd EN_API

# 冒烟（3 条样例）
uv run python test_tmt_connectivity.py

# dry-run（默认，不写 EN）
uv run python translate_item_group_names.py --dry-run

# 仅拉中文（无 TMT 密钥）
uv run python translate_item_group_names.py --dry-run --fetch-only

# 写回生产（必须用户确认后）
uv run python translate_item_group_names.py --apply
```

## 4. 环境变量

| 变量 | 用途 |
|------|------|
| `ERP_API_KEY` / `ERP_API_SECRET` 或 `PROD_ERP_API_*` | 生产 EN REST |
| `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY` | 腾讯云 CAM API 密钥 |
| `TENCENT_TMT_REGION` | 默认 `ap-guangzhou` |

**CAM**：专用用户 `tmt-api-translation` + `QcloudTMTFullAccess`。勿把个人子账号主密钥给同事或提交 Git。

## 5. 输出报告

`out/物料组翻译_{fetch|dryrun|apply}_{ts}.xlsx`

| 列 | 含义 |
|----|------|
| 中文 / 英文 | 源文与译文 |
| 节点类型 | KS叶子 / 叶子(非KS) / 叶子组(LGKS) |
| 处理结果 | 成功 / 跳过 / 失败 / 待翻译 |

汇总 sheet：入 N → 成功/跳过/失败/待翻译对账。

## 6. 与报关导出的关系

| 粒度 | 字段/脚本 | 翻译方式 |
|------|-----------|----------|
| 款式（物料组） | `item_group_translation` | 本脚本 / TMT |
| 物料（DN 聚合品名） | `customs_export.py` → 报关 Excel | DeepSeek（`api.vilavi.cn`） |

不要混用：款式英文名 ≠ 含面料尺寸的报关品名。

## 7. 已知坑

1. **TMT SDK**：精简包无 `TextTranslateBatch` 模型类 → 脚本用 `client.call("TextTranslate")` 逐条调
2. **QPS**：间隔 0.25s（5 次/秒限制）；全量约 5 分钟
3. **TMT 质量**：「靠枕」可能译成 pillow / headrest 混用，报关前人工审 Excel
4. **生产写入**：默认 `--dry-run`；`--apply` 前必须用户确认范围

## 8. 延伸阅读

- [docs/reference/item-group-translation-pipeline.md](docs/reference/item-group-translation-pipeline.md)
- [docs/reference/tmt-setup.md](docs/reference/tmt-setup.md)
- [docs/lessons/item-group-translation.md](docs/lessons/item-group-translation.md)
- [AGENT_HANDOFF_报关单据导出.md](AGENT_HANDOFF_报关单据导出.md)
- [docs/solutions/tooling-decisions/en-item-group-tencent-tmt-translation.md](../docs/solutions/tooling-decisions/en-item-group-tencent-tmt-translation.md)
