---
okf: v0.1
type: Log
title: dingtalk_oa_approval 变更日志
---

# 变更日志

## 2026-09-11（跨月剔除补上生成端 + 修键不对称 + NAS 账号出声）

- **新增** `late_submission_keys.py`：读 Google 表「钉钉账期提交时间不对挪动记录」→ 按 `--period` 生成 `--exclude-keys` 文件。此前只有消费端（`filter_export_by_period.py`），从表里导出键这一步是手工的。
- **修** 唯一键金额不对称：表里存的 `…|eBay（US）|0.0` 对不上导出侧算的 `…|0`（`str()` 取决于 dtype），那笔会被静默漏剔除。新增 `ding_xlsx.norm_amount()` / `build_key()`，两端同源；`unique_key()` 改为调它，并让销售额为空时回落应收账款。
- 实测（2026-09-08 登记的 2026-07 批次）：`--period 2026-08` → 42 个剔除键（43 行含 1 条重复键，会在输出里点名），早交的 2 行因剔除列为空自动保留。
- 新增 `tests/test_late_submission_keys.py`（11 项）；模块测试 16 → 27。
- 文档：`reference/late-submission-registry.md` 补「唯一键必须两端同源」与命令；handoff / 惯例文档同步。
- **修** NAS 账号解析（`nas_admin.nas_credentials`）出错时不再沉默：账号取 `NAS_ADMIN_USER` → `NAS_SSH_USER` → `NAS_USERNAME`。最后那个通常是只做 API 的账号（`NAS_API/.env` 当前就是 `fzh.test`），权限**有时就够用**，所以仍允许回退，但会 `warnings.warn` 提示——它可能看不见「财务部」共享，那时在 .env 加 `NAS_ADMIN_USER=<管理员账号>` 即可，不用改代码。原问题是**静默**：选错账号却看起来"连上了"。
- 新增 `scripts/check_secrets.py`：扫**整个工作区**的明文凭证（含未 `git add` 的脚本），补上 AGENTS.md 第 9 条只看 `git diff` 的盲区——`nas_product_visuals/nas_cmd.py` 就是那样漏过的。

## 2026-09-11（226/227 拼图：env、账期月过滤、NAS 归档）

- NAS 管理员账号不再写进模块明文，改读 `NAS_API/.env` 的 `NAS_ADMIN_USER`（或 `NAS_SSH_USER` / `NAS_USERNAME`）。
- `ding_xlsx.py` 入库：读导出、展开销售账户、21 位审批编号文本、迟交唯一键。`export_period_excels.py` / `fill_aug_from_oa.py` / `july_amz_by_account.py` 不再依赖仓库外 `patch_july_2026.py`。
- 新增 `filter_export_by_period.py`（发起时间导出 → 按账期月切定稿）和 `archive_aflow_to_nas.py`（浏览器附件 dry-run 后进账期桶）。
- `AMZRosoonIT` 7/8：SYX 于 2026-09-10 已补交；下一任走 API + 7 月桶，不用 `--only-departed`。
- 手册 `research/browser-admin-download.md` 改为 API + aflow + 过滤 + NAS 一条流水线，指向 `dingtalk.aflow.receipt.export` / `.attachments`。

## 2026-09-10（补齐 7 月对话里未落地的部分）

- **新增** `reference/late-submission-registry.md`：迟交挪动登记表（Google 表「和财务部共享」→「钉钉账期提交时间不对挪动记录」）、唯一键 `审批编号|账期日期|销售账户|销售额`、`后续账期须剔除` 列、2026-07 批次 43 行/27 单、每月剔除流程。这是算 8/9 月时避免同一笔重复核算的机制。
- **新增** `research/2026-09-09-attachment-fetch-and-drm-audit.md`：附件拉取 441 单 / 284 成功 / 157 失败（205 次 `userNotExist`）、DRM 两月桶 230 文件构成、187/43/117 三方对照、combined 228+21、钉钉 20 QPS 与耗时；明确「钉钉附件 API 不能当离职人员漏交证据」。
- **补充** `research/2026-09-10-july-amazon-period-reconcile.md`：7 月定稿怎么来的（文件 1 129 行 / 文件 2 396 行；方法 1 = 172 行，方法 2 = 170 行 = 6 月 3 + 7 月 167，采用方法 2；方法 2 审批编号已被 Excel 收成数字，不可按编号对账）。
- **补充** `reference/oa-attachment-api.md`：应用与权限选型（`qyapi_aflow` 用不上、列实例接口仅支持企业内部应用、建议 OA 单独用内部应用）。
- **补充** 惯例文档 `docs/solutions/conventions/amazon-period-file-reconcile.md`：Amazon 结算周期基线（14 天一期、自然月 2 期、0 打款不当漏交、7 天提交制度沿革）+ 跨月剔除规则。
- **隐私**：清掉本模块新引入的字面值 —— 去掉真实钉钉显示名（改为占位符）、`paths.py` 不再内置本机 NAS 同步盘默认路径（改 `LOCAL_NAS_PERIOD_ROOT` 必填）。

## 2026-09-10

- 惯例与交接：Amazon 账期按账号对 NAS/钉钉/赛狐结算组；店名经别名（Rucener↔Rosoon，Novelledo↔YTHD）；人名公开叙述用拼音首字母。见 `docs/research/2026-09-10-july-amazon-period-reconcile.md`、`docs/solutions/conventions/amazon-period-file-reconcile.md`。
- 7 月赛狐 `groupPage` 95 组。按别名后：有 NAS 或核算 73；打款 0 两侧无 21；有打款两侧无 1（`AMZRosoonIT` 7/8，缺钉钉，现任 SYX）。「或」不是「钉钉且附件都齐」。
- `AMZRosoonSE` 7/18：审批 `202607231544000528489` 已附 txt，标准 API `userNotExist`，NAS 7 月桶无对应文件。
- 匹配脚本：`sellfox_amz_settlements.py` `BRAND_ALIASES`；`july_amz_by_account.py`。核算金额以 Excel 为准；离职 txt 以 NAS 全员扫描为准。
- 木已成舟：发起日≤2026-07-03 已进 6 月的（如 Daneey-ES 7/1）不再改归 7 月。Amazon 只认 `.txt`。审批编号当文本。不写本地 NAS 同步盘。
- 下一步：浏览器经 `web_automation` dispatch 进钉钉管理后台补 Excel/离职附件，见 `docs/research/browser-admin-download.md`。能力名 `dingtalk.aflow.receipt.export` / `.attachments`（PR 227）。
- 隐私：公开叙述用人名拼音首字母；NAS 真名映射改到 gitignore 的 `person_folders.local.json`；缓存/NAS 根路径走 `paths.py` 环境变量，不再写本机人名目录。

## 2026-09-10（归档与 NAS 操作）

- 账期月口径回读：迟交 Amazon txt 进对应月桶；跨月单才拆文件名；新月桶未开则该月文件暂留上一桶。
- 人名夹 = 提交人。同一账号可在多夹（助手/离职/换人）。钉钉英文名/错别字映射见 gitignore 的 `person_folders.local.json`。
- 离职下载：标准 Grant `userNotExist`；专享接口见 research。综合 DRM 已归档，不改同步盘。

## 2026-09-09

- NAS 补入：独立站 csv、PKO pdf、Johna-US 7 月 txt 等；钉钉英文名/错别字与财务文件夹不一致会造成假缺口，映射见 `person_folders.local.json`。
- 8 月桶内文件名属 7 月账期的已移到 7 月对应提交人夹，避免两月重复计算。桶里已有同茎 csv 则不再加 zip。
- 财务 NAS：`NAS_API/.env` 管理员账号可见财务部账期资料根。综合副本排除部分 PDF / 审批中 csv。
- 离职下载调研：标准 Grant 按发起人授权；官方出路 OA 高级版 `.../premium/.../urls/download`。
- 下载过滤：只保留完成/审批中且结果≠拒绝；跳过图片控件。离职发起人附件接口 `userNotExist`，对照 DRM 已归档（不写 NAS 同步盘）。
- 初始化子项目：只读拉取销售收款确认单附件、`fileId__原名` 防重名、对照账期桶、NAS FileStation 只读探测。
