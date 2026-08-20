# SELLFOX_API — Agent 交接说明

> **赛狐 OpenAPI 文档 + 连通性测试**
> **人读文档**: [docs/index.md](docs/index.md)

## 这是什么

赛狐 (Sellfox) 开放平台的 API 文档本地镜像 + 连通性测试脚本。从 Apifox (`sellfoxapi.apifox.cn`) 下载全部 API Markdown 文档，按原始结构组织，方便 Agent 离线查阅和搜索。

**组合商品/EN 套件**不走文档下载脚本，走 `sellfox_combo_ops.py` + Skill `sellfox-combo-create`。操作细节见下文 **「EN 套件 / 赛狐组合商品」**；CLI 表见 [docs/reference/combo-ops.md](docs/reference/combo-ops.md)。

## EN 套件 / 赛狐组合商品

> **同事 Agent 日常维护的唯一操作入口。** Skill 只负责触发与摘要；本章节含默认命令、硬规则、冻结范围与停手条件。
> 背景与配对 API 示例见 [sellfox-combo-sku-create-pairing-workflow.md](../docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md)。

### 接手顺序

1. 读本章节 → 跑 dry-run 拿事实 → 把 JSON 计划给用户。
2. 用户确认范围后 `--apply`。
3. 遇 `mismatch` / `blocked_*` / 文档未写行为 → 停，带 EN/赛狐回读证据报告；可开 Issue/PR，不猜。

工作目录 **`SELLFOX_API`**。命令前缀：

```bash
uv run --project .. python sellfox_combo_ops.py <command>
```

凭证：赛狐代理 Key → 根 `.env` 的 `SELLFOX_PROXY_API_KEY`；EN → `EN_API/.env`（`ERP_API_KEY` / `ERP_API_SECRET`）。EN `--env` 默认 **prod**。

### 默认命令

| 场景 | 命令 | 写入 |
|------|------|------|
| 还没有 EN Bundle | `en-preview --child "SKU:qty"` 然后 `en-create --child "SKU:qty"` | `--apply` 才写 EN |
| 已有 EN Bundle，对账赛狐 | `sync-combos --like "TJ#KS0525%"` 或 `--sku TJ#...` | `--apply` 才写赛狐 |
| 确认计划并落盘 | 同上 + `--apply --report sync_report.json` | 是 |
| 单条赛狐创建（已有 EN 回读 TJ#） | `create --sku --name --child --full-cid 428697-` | `--apply` |
| 只改分类 | `set-category --sku --full-cid 428697-` | `--apply` |
| 查底层 / 查组合 | `check-bottoms` / `check-combo` | 否 |

`sync-combos` **必须**带 `--like` 或 `--sku`。禁止无范围全量拉取。

完整参数与 action 枚举 → [docs/reference/combo-ops.md](docs/reference/combo-ops.md)。

### 硬规则

1. **先 EN，后赛狐。** 赛狐组合 SKU 必须等于 EN 已保存并回读确认的 `TJ#...-NNN`（`name == new_item_code == Item.item_code`）。
2. **EN REST 创建只传 `items`。** 禁止 `new_item_code` / `new_item_code_name` / `name`；禁止先 POST 空单再 PUT；禁止 PUT 改已有套件组成或编号。组成变化 → 新建 Bundle（只传 items，服务端生成编号）。
3. **去重**以完整 `(item_code, qty)` 为准；编号与名称保留 `-001/-002/-003` 后缀。预览 `is_duplicate=true` → 停止，使用 `existing_bundle`。
4. **写操作默认 dry-run。** `--apply` 仅在用户明确授权范围后使用。
5. **赛狐分类 `套件#` 已存在**（`fullCid=428697-`），不要重复建分类。`edit.json` 改分类必须带原 `childSkus`。
6. **`sync-combos --apply` 只执行** `create` 与 `set_category`。`mismatch` / `blocked_en` / `blocked_bottoms` **永不自动改组成**。
7. **已存在组合若组成不一致**，`create` 断言失败退出，不当成功跳过。
8. **已发货订单包裹** `updateMatch.json` 会被拒；如实报告，不绕过。
9. **底层 SKU 缺失** → 停，走 `missing-products` / `multi-attr`，不要继续创建组合。
10. **在线/订单配对**不自动跑；写配对前用户单独确认（见工作流文档）。

### 冻结与跳过（2026-08-20）

| 对象 | 类型 | Agent 行为 |
|------|------|------------|
| KS0443 共 12 个 EN Bundle + 12 个赛狐组合（`TJ#KS0443%`） | **日期冻结**（2026-08-19 已重建并回读） | 不要重跑 `sync-combos --like "TJ#KS0443%"` 除非用户明确授权 |
| `FXLSSF3030` | **长期跳过**（历史非 `TJ#` 海绵套件；上层 Item 已 disabled） | 脚本标 `skip_historical`；**不要**按新规则改名/重建，除非用户另行授权 |
| KS0003 / KS0395 | **已关闭**（2026-08-20 用户确认无问题） | 不要纳入清理或审计待办 |

### 完成关口

1. EN Bundle 回读：`name == new_item_code == Item.item_code`，子表非空，物料组 `套件#`，序号后缀一致。
2. `sync-combos` 报告：`input_en == output_rows`；非 ok 行都在 `unmatched`，不得静默丢弃。
3. 赛狐写入后断言：`isGroup=1`、`fullCid=428697-`（若要求分类）、`childSkus` 与 EN `items` 多重集合一致。
4. 无用户授权的写入、无改动冻结对象、无发明新 API。

### 停手条件

立即停止并报告（附 EN/赛狐回读 JSON）：

- `mismatch` — 赛狐已有组合但组成或 `isGroup` 不同
- `blocked_en` — EN 编码/子表/物料组不合法
- `blocked_bottoms` — 赛狐缺底层 SKU
- 预览重复、权限 40021（代理 token 缓存，见工作流 Proxy 章节）、已发货配对拒绝
- 文档与脚本未覆盖的 API 行为

不要 PUT 修组成、不要临时编号、不要无范围扫描。

### Issue / PR

- 改脚本：`feature/xxx` → PR → 审批，**不直接推 main**。
- Issue 正文必须含：范围（`--like`/`--sku`）、dry-run JSON、`input_en`/`counts`、EN/赛狐回读摘要、停手原因。**不要贴密钥。**

```bash
gh issue create --repo keyapi/fzh-data --title "..." --body "..."
gh pr create --repo keyapi/fzh-data --base main --head feature/xxx
```

### 代码地图

| 文件 | 职责 |
|------|------|
| `sellfox_combo_ops.py` | CLI：`sync-combos`、`en-preview`、`en-create`、`create`、`set-category` |
| `combo_reconcile.py` | 纯对账：`plan_sync`、action 枚举、`HISTORICAL_SKIP_SKUS` |
| `combo_en.py` | EN REST：items-only 创建、预览、拉 Bundle |
| `client.py` | 赛狐代理 API |
| `tests/sellfox_api/test_combo_reconcile.py` | 对账逻辑单测 |

## 快速启动

```bash
# 查看 API 文档
ls docs/api-reference/

# 下载/更新 API 文档
python download_docs.py --all

# 测试 OpenAPI 连通性（需在白名单 IP）
python test_api.py

# 拉取 SP 广告报告 (4 种: Campaign/Targeting/SearchTerm/Placement)
python fetch_ad_reports.py --days 7

# 指定店铺名称拉取
python fetch_ad_reports.py --shop-name "MyStore" --days 30
```

## 凭证

| 项目 | 位置 |
|------|------|
| App ID / Secret | `SELLFOX_API/.env`（优先），`advertise/.env`（备用） |
| API 文档密码 | `.env` 中的 `SELLFOX_API_DOC_KEY` |
| 生产环境 | `https://openapi.sellfox.com/` |
| API 文档 | `https://sellfoxapi.apifox.cn/` |

## 文档地图

| 你需要... | 读这个 |
|----------|--------|
| Agent 接手总览 | 本文件 |
| EN 套件 / 赛狐组合商品（操作入口） | 本文件 **「EN 套件 / 赛狐组合商品」** 章节 |
| EN 套件 CLI / action 表 | [docs/reference/combo-ops.md](docs/reference/combo-ops.md) |
| EN 套件 Skill 触发词 | `.agents/skills/sellfox-combo-create/SKILL.md` |
| 查找具体 API 端点 | `docs/api-reference/` 下按模块浏览 |
| 了解 API 接入过程 + 踩坑 | [docs/lessons/2026-06-25-sellfox-integration-lessons.md](docs/lessons/2026-06-25-sellfox-integration-lessons.md) |
| 了解探索历史 + 架构发现 | [docs/research/2026-06-25-sellfox-api-exploration.md](docs/research/2026-06-25-sellfox-api-exploration.md) |
| 查看 API 文档全文索引 | [docs/api-reference/llms.txt](docs/api-reference/llms.txt) |
| 查看变更记录 | [docs/log.md](docs/log.md) |

## API 模块速查 (419 个端点)

| 模块 | 端点数 | 目录 |
|------|--------|------|
| 商品 | 16 | `docs/api-reference/商品/` |
| 销售 | 8 | `docs/api-reference/销售/` |
| 订单 | 9 | `docs/api-reference/订单/` |
| 广告 | 37 | `docs/api-reference/广告/` |
| FBA | 44 | `docs/api-reference/FBA/` |
| 采购 | 25 | `docs/api-reference/采购/` |
| 仓库 | 46 | `docs/api-reference/仓库/` |
| 数据 | 18 | `docs/api-reference/数据/` |
| 财务 | 68 | `docs/api-reference/财务/` |
| 多平台 | 115 | `docs/api-reference/多平台/` |
| 报告中心 | 10 | `docs/api-reference/报告中心/` |
| Feed | 3 | `docs/api-reference/Feed/` |
| 客服 | 1 | `docs/api-reference/客服/` |
| 工具 | 1 | `docs/api-reference/工具/` |
| 设置 | 4 | `docs/api-reference/设置/` |
| 开发指南 | 14 | `docs/api-reference/开发指南/` |

## 关键架构决策

- **OAuth 2.0 client_credentials**: Token 端点 `/api/oauth/v2/token.json`，唯一不受 IP 白名单限制的端点
- **IP 白名单**: 所有业务端点受服务端 IP 白名单保护（北京办公室 + VPS）
- **响应格式**: `{code: 0, msg: "success", data: {...}, requestId: "..."}`
- **文档源**: Apifox 共享项目，需密码访问，通过浏览器 cookie 认证

## Agent 首次接手检查清单

1. 确认要查的 API 属于哪个模块
2. 进入 `docs/api-reference/<模块>/` 找对应 `.md` 文件
3. 文档内包含 OpenAPI YAML spec（请求参数、返回格式）
4. 如需更新文档: `python download_docs.py --all`

## Selenium 脚本

`SPS_Selenium_Local/` 下有独立的 Selenium 自动化脚本（ERP Web 端登录 + 多属性商品设置），属于不同项目，见该目录。
