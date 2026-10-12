---
type: Research
title: 六个精确 BOM 候选的 FBA 空 goodsSku 匹配门槛验证
date: 2026-10-12
module: sellfox_settlement
tags: [amazon, fba, sku-mapping, read-only, technical-validation]
---

# 确认入口过滤，保持成本 hold

输入是上一轮274个实际发货缺物料映射组件中的6个精确 BOM 候选。本轮仅精准只读查询4个当前 ERP Item 和6个当前 Tongtool Order，10个 REST GET 全部200；读取现有8月通途FBA快照及订单 raw_data 的商品标识，不新增通途全月或全量查询。不回填 ERP 物料、不执行重新匹配、不改生产源代码或历史成本。

| 验证证据 | 数量 |
|---|---:|
| 目标 FBA 组件 | 6 |
| 当前 Item 客户表 ref_code 与平台 SKU 完全相等 | 6 |
| 8月通途快照订单＋原生账号＋平台 SKU 精确对应 | 6 |
| 对应上游 goodsSku 为空 | 6 |
| 当前订单 raw_data 同商品 goodsSku 为空 | 6 |
| 当前订单目标组件唯一匹配 | 6 |
| 当前订单通途 SKU／ERP 物料都为空、状态未匹配 | 6 |

这里只确认这4个 Item 的客户码存在；没有扫描全局 Item Customer Detail，不能宣称 ref_code 在全系统唯一，也不据此自动确认商品财务归属。

## 可复现生产匹配分支

生产 `OrderSyncService._process_fba_order_items()` 取 `tongtool_sku = item.get('goodsSku') or ''`，只有 `if tongtool_sku` 才调用 `_find_erp_item_by_tongtool_sku(tongtool_sku, platform_sku)`。

查找函数本身选择 `tongtool_sku if tongtool_sku else platform_sku`，按 `Item Customer Detail.ref_code` 查找，并使用 `LIMIT 1`。因此虽然查找函数支持平台 SKU fallback，初始 FBA 处理入口在 goodsSku 空时不会调用它。后续重新匹配分支允许通途 SKU 或平台 SKU，但本轮未执行重新匹配。

将真实6个上游商品字段传给私有生产 AST 离线重放，查找调用计数为0，输出均保持未匹配及空 ERP 物料。汇率获取以明确的纯本地 adapter 隔离，本验证只证明 SKU 匹配门槛，不验证成交费换汇。当前生产源文件整体已变化；只读 SSH 获取当前源 hash 和源码后，对上述两个方法作 AST 对比，均与已重放快照完全一致。因此本次门槛结论仍适用于2026-10-12观察到的生产版本。

现有证据支持“上游未提供通途 goodsSku，初始 FBA 导入入口阻断平台客户码 fallback”。当前 EN 订单也尚未匹配；没有凭历史快照断言某次同步的修改时间或谁进行了漏更新。历史映射生效时点、全局客户码唯一性、以及改进匹配入口的生产部署仍需独立验证。

## 私有证据与复跑

报告及真实订单／SKU只在仓库外：

- `cost/diagnosis20261012/exact_candidate_current_master_evidence.json`：当前观察时间、限定 Item 客户码、目标订单组件、上游商品字段、源 hash 和分支重放。
- `cost/diagnosis20261012/probe_exact_candidates.py`：从主仓库 EN_API/.env 加载凭证，精准 GET；不打印凭证或原始整份订单。
- `cost/diagnosis20261012/replay_mapping_gate.py`：真实输入的纯本地生产 AST 重放。
- `cost/diagnosis20261012/order_sync_current_20261012.py`：当前只读源快照，仅为私有比对，不提交仓库。

本轮没有变更 ledger、测试、runner 或工作簿。6个精确候选仍是技术匹配候选，未生成申报成本；原23组历史产品差异 hold 不变。
