# channel_account_sync — Agent 交接

> **CLI**: `fetch_sources.py` · `compare.py` · `apply.py`
> **人读**: [README.md](README.md)
> **Skill**: `.agents/skills/channel-account-sync/SKILL.md`
> **已解决问题**: [docs/solutions/workflow-issues/en-channel-account-gsheet-sync.md](../docs/solutions/workflow-issues/en-channel-account-gsheet-sync.md)

## 业务背景

Google 表「和运营部共享」工作表「渠道账号（20260521起在此维护）」是运营维护的店铺清单（渠道、账号、别名、运营分组、按月运营人员）。生产 EN `Channel Account`（app `vilavi_pim`）是系统主数据。2026-08 对照时 EN 大约从 2 月起很少更新。

**表是事实源。** 写 EN 前先确认范围；默认 dry-run。

Spreadsheet: `https://docs.google.com/spreadsheets/d/1nbMO-wf-Oj7HIuYlPOtrC7F8QtsEPDE80BmXo8G6O3Y/edit?gid=763421711`

## 管道

```
fetch_sources.py          # 表 + EN 父文档（含子表）→ out/*.json
  → compare.py            # 变化折叠计划 → out/channel_account_plan.json
  → apply.py              # 默认 dry-run；--apply 才写生产
       探路 canary → Kaufland 区域 → Illios channel
       → 新建账号 → 补别名 → 已有账号追加负责人
```

```powershell
uv run python channel_account_sync/fetch_sources.py
uv run python channel_account_sync/compare.py
uv run python channel_account_sync/apply.py
uv run python channel_account_sync/apply.py --apply
```

worktree 里跑：凭证在父仓库。`EN_API/.env` 用 `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET`（没有则 `ERP_*`）。Google SA：`secrets/gsheets-service-account.json` 或 `GSPREAD_SERVICE_ACCOUNT_FILE`。

## 铁律

- Amazon **禁止** EUR/EU 账号。欧洲九国：`DE ES FR IT UK PL NL BE SE`。旧名 `AMZFZHSXEUR` 只挂在 `AMZFZHSXDE` 别名。
- 负责人：**人变了才加行**，`from_date` 用该段第一个月的 `YYYY-MM-01`。
- `owners.user` 写中文名（含 `&`、`待分配`）。开卖后空月 → `待分配`。
- 不建表行 `null`。不把 `WFDANEEYUS` 与 `WFDaneeyUS` 合并。
- Illios：channel `Illiosenergy` / code `ILLIOS` / 账号 `ILLIOSPL`。
- 子表 list API 403：只 GET/PUT 父 `Channel Account`。
- REST 去掉 `Expect` 头，否则生产 417。
- `--apply` 前先 canary。Cursor 可能拦截生产 PUT，需要本机批准。
- 不要提交 `out/` 里的账号 JSON。

## EN 命名

`Channel Account.name` = `{channel_code}{account_code}{region}`；`allow_empty_account_code=1` 时没有中间段。autoname 是 `account_id`。

例：`AMZFZHSXDE` = AMZ + FZHSX + DE；`KFLAT` = KFL + 空 + AT；`ILLIOSPL` = ILLIOS + 空 + PL；`WFEU` = WF + 空 + EU（Wayfair 可以 EU）。

## 2026-08-25 已写入生产

见解决方案文档「Examples」。**未做**：`Operation Staff Settings` 补中文名+分公司。若用户再提运营人员主数据，另开一轮，不要 silently 全量改 Single。

## 关键模块

| 文件 | 作用 |
|------|------|
| `names.py` | Illios 映射、别名解析、Amazon EUR 拒绝、拆 name |
| `owners.py` | 月列折叠、待分配、相对 EN 最新行的增量 |
| `plan.py` | 表+EN dump → 计划 |
| `rest.py` | NoExpect session |
| `fetch_sources.py` | 只读拉取 |
| `compare.py` | 出计划 |
| `apply.py` | dry-run / `--apply` |

## 禁止

- 不要直接 push main
- 不要把 SA JSON / EN token 写进文档
- 不要用系统 python；一律 `uv run python`
- 不要把 `.codex_tmp/channel_account_*.json` 提交进 git
