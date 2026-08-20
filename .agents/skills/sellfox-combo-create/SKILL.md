---
name: sellfox-combo-create
description: >
  EN Product Bundle（套件# / TJ#）与赛狐组合商品的创建、对账、回读断言。
  当用户提到"组合商品"、"组合SKU"、"套件SKU"、"EN套件"、"Product Bundle"、
  "TJ#"、"childSkus"、"sync-combos"、"赛狐创建套件"、"底层商品检测"、
  "套件#分类"或"订单配对错误"时触发。
  不要用于普通多属性 SPU 创建（用 multi-attr），不要用于通途有库存三方主线
  （用 missing-products），不要直接改已发货订单包裹配对（API 会拒绝）。
compatibility: >
  SELLFOX_API/sellfox_combo_ops.py、combo_reconcile.py、combo_en.py；
  代理 Key 在根 .env 的 SELLFOX_PROXY_API_KEY；EN 凭证在 EN_API/.env。
  所有写操作默认 dry-run，--apply 前必须用户确认范围。
metadata:
  module: SELLFOX_API
  scripts: SELLFOX_API/sellfox_combo_ops.py
  updated: 2026-08-19
---

# EN 套件 / 赛狐组合商品

同事 Agent 的默认入口是 **`sync-combos`**，不是手写 REST，也不是 `.codex_tmp/` 一次性脚本。

## Read First

1. `../../SELLFOX_API/docs/reference/combo-ops.md` — CLI、对账动作、报告字段、停手条件。
2. `../../docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md` — 背景、权限、配对 API。
3. `../sellfox-api/SKILL.md` — 代理 Key / 40021 token 缓存。
4. `../missing-products/SKILL.md` 与 `../multi-attr/SKILL.md` — 缺底层 SKU/属性时走那边，不走组合流程。

先跑脚本拿当前事实。不要凭聊天记忆、旧 Excel 或临时编号写 EN/赛狐。

## 自主边界

脚本**能**做：按用户给的范围从 EN 拉 Product Bundle → 校验编码/子表 → 对账赛狐 → 输出 create / ok / set_category / mismatch / blocked 计划 → dry-run → 用户确认后 `--apply` → 回读断言 `isGroup`、分类、`childSkus`。

脚本**不能**做、必须停下报告：

- 无 `--like` / `--sku` 的全量扫描
- PUT 改已有套件组成或编号；空单再补子表；临时 `new_item_code`
- 发现 mismatch 后“修一下组成”
- 自动配对在线商品/订单（只提供文档；写配对前单独确认）
- 清理 `FXLSSF3030`、KS0443 已完成对象、`KS0003/KS0395` 无主子行
- 猜未覆盖的边界或发明新 API 调用

文档没写的边界：停 → 把 EN/赛狐回读证据交给用户 → 用户允许后再开 Issue/PR。

## 硬约束

- **先 EN，后赛狐。** 赛狐组合 SKU = EN 已保存并回读确认的 `TJ#...-NNN`。
- EN REST 创建 **只传 `items`**。禁止 `new_item_code` / `new_item_code_name`，禁止空单 PUT，禁止 PUT 改组成。
- 去重以完整 `(item_code, qty)` 为准；编号和名称保留 `-001/-002/-003`。
- 写操作默认 dry-run；`--apply` 只在用户确认范围后使用。默认 EN 环境是 **prod**。
- 赛狐分类 `套件#` 已存在（`fullCid=428697-`），不要重复建分类。
- `edit.json` 改分类必须带 `childSkus`。
- 已发货包裹 `updateMatch.json` 会被拒；不要绕过。

## 不要动

- KS0443 的 12 个 EN Bundle / 12 个赛狐组合已重建并回读一致，不要重跑。
- `FXLSSF3030` 是历史老套件，脚本会 `skip_historical`，不要按新规则改。
- 4 条 `KS0003/KS0395` 无主子行是历史残留，等用户确认，不要自行删除。

## 日常流程

工作目录：`SELLFOX_API`。命令：`uv run --project .. python sellfox_combo_ops.py ...`

### 1. 用户要新建套件（还没有 EN Bundle）

```bash
uv run --project .. python sellfox_combo_ops.py en-preview --child "KS0525-QQFSB-80x80x65-DEEPGREY:2"
uv run --project .. python sellfox_combo_ops.py en-create --child "KS0525-QQFSB-80x80x65-DEEPGREY:2"
# 用户确认后再 --apply
```

预览 `is_duplicate=true` 时停止，使用已有 `existing_bundle`。`--apply` 后脚本会回读 `name == new_item_code == Item.item_code`。

### 2. 对账并同步赛狐（主路径）

```bash
uv run --project .. python sellfox_combo_ops.py sync-combos --like "TJ#KS0525%"
# 把 JSON 计划给用户。确认后：
uv run --project .. python sellfox_combo_ops.py sync-combos --like "TJ#KS0525%" --apply --report sync_report.json
```

`--apply` 只执行计划里的 `create` 和 `set_category`。`mismatch` / `blocked_en` / `blocked_bottoms` 只出现在报告里，不会自动修。部分失败会继续其余项，最后非零退出并列出 `failed`。

底层 SKU 缺失：停下，走 missing-products / multi-attr，不要继续创建组合。

### 3. 单条赛狐创建（仅当用户给出已回读的 TJ#）

```bash
uv run --project .. python sellfox_combo_ops.py create \
  --sku "TJ#KS0525x2_KS0526x1_KS0527x1-001" \
  --name "套件#...-001" \
  --child "KS0525-QQFSB-80x80x65-DEEPGREY:2" \
  --full-cid "428697-"
```

已存在但 `childSkus`/`isGroup`/分类不一致 → 断言失败退出，不要当成功跳过。

### 4. 配对（不自动跑）

在线商品：`POST /api/order/api/product/matchByMsku.json`。订单包裹：`POST /api/packageShip/updateMatch.json`，已发货则如实报告。详见工作流文档。

## 完成关口

1. EN Bundle 回读：`name == new_item_code == Item.item_code`，子表非空，序号后缀保留。
2. `sync-combos` 报告：`input_en == output_rows`；未匹配项都在 `unmatched`。
3. 写入后断言：`isGroup=1`、`fullCid=428697-`、`childSkus` 与 EN 组成一致。
4. 没有用户授权的写入、没有清理历史残留、没有发明新调用。

## 发现问题怎么提交

仓库规则：`feature/xxx` 分支 → PR → 审批，不直接推 `main`。

```bash
gh issue create --repo keyapi/fzh-data --title "..." --body "..."
gh pr create --repo keyapi/fzh-data --base main --head <branch>
```

Issue 必须带：范围（`--like`/`--sku`）、dry-run JSON、EN/赛狐回读摘要、你停手的原因。不要在 Issue 里贴密钥。
