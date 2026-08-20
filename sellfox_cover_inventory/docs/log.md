---
okf: v0.1
type: Log
title: 赛狐皮壳共享库存代理 — 变更日志
---

# 变更日志

## 2026-08-20

- **初始化**: 建立 OKF bundle、Agent Handoff、运行说明及单 SKU 只读审计脚本。
- **冻结阶段结论**: 通途并行期使用 `KS` 普通商品库存池 + `PK# -> KS x1` 组合商品代理；加工商品留到通途退役后的独立迁移评估。
- **审计硬化**: FBA/退货/不良仓 blocked；DANEEY 主仓 `cautions`；赛狐 `POLAND` 对应通途 covers（成品仓名才 caution）；`isGroup` 接受 `true`；加工商品计数用 `totalSize`。missing-products 路由改为禁止有库存 `PK#` 普通商品，组合代理走本模块。
