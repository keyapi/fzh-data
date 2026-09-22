---
okf: v0.1
type: Reference
title: Google 表访问 + 「渠道账号」表规范 & 别名规则
description: 用服务账号(gspread)读/写共享谷歌表；「和运营部共享/渠道账号」表结构与 `渠道账号别名` explode+去重规则
resource: tongtool_order_cost/tongtool_order_cost/gsheets.py
tags: [google, gsheet, gspread, service-account, channel-account, reference, alias]
---

# Google 表访问 + 「渠道账号」表规范 & 别名规则

## 访问方式（gspread + 服务账号）
- 凭证：`D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json`（父仓库，gitignored；**勿提交/泄露**）。若用用户 OAuth：`secrets/gsheets-user-oauth.json`。
- 依赖/运行：`pandas`+`gspread`+`google-auth` 在**父仓库 `.venv`**（`D:\Work\赛狐\Cursor\.venv\Scripts\python`；本仓库 worktree 的 uv venv 有时装不稳，用父仓库 venv 更稳）。
- 复用 helper：`tongtool_order_cost/tongtool_order_cost/gsheets.py` → `client()`(service_account_from_dict) + `gsheet2df(gc, gsheet_name, worksheet_name)`（首行=表头）。
- **列移动/插入**：gspread 6.x `insert_cols(values, col)` 的 `values` 语义烦人；推荐用 **Sheets API `moveDimension`**（`google.auth` AuthorizedSession 调 `…/spreadsheets/{id}:batchUpdate`，body `{'requests':[{'moveDimension':{'source':{'sheetId':gid,'dimension':'COLUMNS','startIndex':..,'endIndex':..},'destinationIndex':..}}]}`）。实测在「和运营部共享」把 `赛狐店铺` 列移到 `渠道账号别名` 右侧成功。

## 「和运营部共享」表
- 重点 worksheet：**`渠道账号（20260521起在此维护）`**（gid 763421711，运营部 YB 维护）；另有旧表 `渠道账号(20250708起 改为在此维护,来自:和财务共享)`（别名/账号更全，来自财务）。
- 列：`运营账号编号, 渠道, 渠道账号, 渠道账号别名, 运营分组, 运营人员2026xx..., ...`。
- `渠道账号` = `AMZ + 账号code + 站点`（如 `AMZRosoonUS`、`AMZStruseryPL`）；命名规则见 `channel_account_sync/docs/reference/naming-rules.md`。
- 我新增了一列 **`赛狐店铺`**（值如 `北京如森-Rucener-US`），用于 `赛狐店名↔渠道账号` 交叉，已加在 `渠道账号别名` 右侧。

## `渠道账号别名` 规则（重要，colab cell 1.2/1.2.1）
- 列读入后：`渠道账号` + `渠道账号别名`（把 `，`替换为 `,`）合并 → `str.split(',')` → **explode 成多行**，每行一个**独立的账号标识** → 作为**匹配键**。
- **去重校验**：整个表 explode 后不能有重复别名（`drop_duplicates(subset=['渠道账号别名'], keep='first')`），否则会错把多个渠道账号映射到一起。
- → **别名必须是完整账户标识**（如 `AMZRosoonUS`、`RSUS`、`美国站-DANEEYUS`、`DANEEYUS`、`AMZRUYANGUS`）；**不能**含裸地区(`CA`) 或品牌名(`LELEFIDO`/`Jalnoddsa`) token——那些不是独立账号标识，且裸地区会与所有该地区账号冲突。
- 参考已有行：US/DE 常见 `站名-code` 形式（`美国站-DANEEYUS`），其它地域多为空。

## 用例
```python
import json, gspread
from pathlib import Path
gc = gspread.service_account_from_dict(json.loads(Path(r'D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json').read_text(encoding='utf-8')))
sh = gc.open_by_key('1nbMO-wf-Oj7HIuYlPOtrC7F8QtsEPDE80BmXo8G6O3Y')   # 和运营部共享
ws = sh.worksheet('渠道账号（20260521起在此维护）')
vals = ws.get_all_values(); hdr = vals[0]
```
> 读多 sheet 用 `sh.worksheet(...)`；写单元格 `ws.update_cell(row,col,val)`；追加 `ws.append_row([...])`。
