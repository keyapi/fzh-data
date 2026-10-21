---
okf: v0.1
type: Plan
title: 库存历史离线入库 dry-run 实现任务书（v4）
date: 2026-10-21
owner: claude-worker
---

# 库存历史离线入库 dry-run 实现任务书

## 背景

`2026-10-21-stock-daily-diagnosis.md` v3 已给出表结构、封存、稳定 ID、同日多 run、
空仓/未知、发布指针等规则。Codex 三轮复审均要求**可运行入口、固定样本、
内容/完整标志/哈希断言**，而不是继续写设计。

本轮只做**离线实现与 dry-run**：读取现有两天文件，写内存/临时 DuckDB 或临时文件，
**不写 `order_store.duckdb`、不访问通途/EN、不改计划任务、不提交原始数据**。

## 交付物

在 `D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/`：

1. `stock_history_ingest.py`
   - CLI：`--run-dir PATH --source legacy|scheduled|manual|unknown --dry-run --db PATH`
   - `--db :memory:` 或临时文件；`--dry-run` 只打印对账与校验结果，不落库。
   - 读取 `manifest.json` + `warehouse=*.jsonl`，按 v3 规则计算 run_id、哈希、批次完整性。
2. `test_stock_history_ingest.py`
   - 合成小样本（不复制真实数据）；覆盖下方验收。
3. `stock_history_ingest.md`
   - 用法、run_id 规则、legacy 封存豁免、失败恢复、已知限制。

## 必须关闭的复审缺口

1. **Legacy 稳定 run_id + 封存豁免**
   - legacy run_id 由 `snapshot_at` + manifest SHA256 确定性生成：
     `legacy-YYYYMMDDTHHMMSS-<sha8>`；同一输入重复导入得到同一 run_id。
   - legacy 允许无 `.sealed`；在 `stock_run` 记 `sealed=false, source='legacy'`。
   - 输出/记录两天固定 SHA256 基线（manifest 与每个 JSONL），供后续比对。
   - 同日覆盖：legacy 导入只读现有目录；发布用 `stock_publish` 指针，
     **不删除**任何历史 run 记录。
2. **稳定 ID 与别名冲突**
   - 主键 `(snapshot_date, warehouse_id, goods_id)`；`goods_sku` 仅展示。
   - 同一别名在同一天指向多个 `goods_id` → 拒绝该 run 发布。
   - 同一 `goods_id` 多个别名 → 写 `stock_id_history`；数值冲突 → 拒绝发布。
3. **同日多 run 选择**
   - 顺序：`run_complete` > `scope_complete` 且覆盖目标仓集合 > `ended_at`（NULL 最后）> `run_id` 字典序最大。
   - 目标仓集合 = manifest 中请求的仓集合；显式记录 `warehouse_scope`。
   - 反序导入必须得到同一 published run；测试证明，不只声明。
4. **历史主键与回滚**
   - `stock_history` 行带 `run_id`，但唯一性按 `(snapshot_date, warehouse_id, goods_id)`；
     发布时单事务替换该日 published 行，保留 `stock_publish.previous_run_id`。
   - 回滚：`--rollback DATE` 按 previous_run_id 重放，测试证明逐行内容一致。
5. **空仓、未知、跨日**
   - 成功空仓（0 行）→ `complete=true`；缺文件/失败仓 → `unknown`，不写 0。
   - 跨日：按 `snapshot_at` 的 Asia/Shanghai 日期归属；目录日期与 snapshot_at 冲突 → 拒绝并报错。
6. **锁与迁移**
   - `stock_history.lock` 独占；崩溃遗留锁按 PID/mtime 恢复，测试覆盖。
   - `schema_migrations` 表；迁移失败回滚，测试覆盖。
7. **测试商品 / 无 UOM**
   - `goodsSku=TEST-1` → `is_test=true`，默认视图排除。
   - `uom_basis='unknown'`；视图禁止跨 SKU 求和（至少测试断言）。

## 验收（测试必须逐条）

1. 同一 run 重复导入 → 行数/内容不变。
2. 10-20 → 退货仓部分批次 `batch_complete=false`、`scope_complete=false`、
   `run_complete=false`；其余 13 仓 complete；不发布为完整日。
3. 10-21 → 5,314 行、14 仓 complete、`run_complete=true`。
4. 完整→不完整、反序导入 → published 指针仍指向完整 run。
5. 不完整→完整 → 原子切换；旧完整行无残留（逐行内容比对）。
6. 成功空仓 vs 缺文件 → complete vs unknown。
7. 同日 multi-run 平局 → 按 run_id 规则确定，反序一致。
8. 别名/ID 冲突 → 拒绝发布并保留证据。
9. 哈希异常 → 拒绝发布。
10. 跨日/目录日期冲突 → 归属正确或拒绝。
11. 回滚 → 逐行内容与 previous run 一致。
12. 并发锁 → 第二个进程拒绝；崩溃遗留锁恢复。
13. schema 迁移失败 → 回滚。
14. TEST-1 排除；无 UOM 禁止跨 SKU 求和。

## 约束

- 不访问通途/EN；不写 `order_store.duckdb`；不改计划任务；不提交原始 JSONL/CSV。
- 不扩 family、不做预测、不合并 PR。
- 新 commit（不 amend `4b7ec55f` 或后续闸门 commit），推送到 `docs/supply-chain-integration-handoff`。
- 最终报告：commit、测试数、两天 dry-run 的对账输出、残余风险。
