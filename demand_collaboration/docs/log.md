---
type: Log
title: 运营需求协同变更记录
---

# 变更记录

## 2026-11-12

- 独立复核 `5e669eca`：63 项测试通过、真实 D5 审计数量守恒；记录 P0（行级范围/发布泄露、范围外拒收阻断基准）与 P1/P2。
- 返修：新增 `scope.py` 行级范围与站点私有范围加载；发布/下载收紧；适配器区分范围外与范围内拒收；基准 as_of 单调；补充字段与索引。
- 测试站（`ensh.vilavi.cn`）部署 Page/角色/桥接包（key_test `feature/operator-demand-workbench`，`0e7d6e8`），真实 D5 1,513 行 + 5 个 PL 商品试点范围；浏览器验收运营提交/审核发布/越权 403；修复空 payload 与 sandbox `allow-forms`。
- 沉淀经验：3 篇新 solutions（EN Page/iframe、侧台账行级范围、D5 导入四分法）+ 环境访问文档第三次实例。

## 2026-11-11

- 新增本地界面、SQLite版本台账、提案/独立审批/冲突/撤销/发布、JSON/Parquet、本地D5只读审计与EN Page/RPC桥接。
- 独立复审修正事件null、未知库存、截止日、撤销入口和Host校验。
- 真实D5审计保留236条拒收；未伪装为全量成功，未改生产或现有预测结果。
