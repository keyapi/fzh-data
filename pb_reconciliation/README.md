# pb_reconciliation — Pottery Barn 对账月度更新

每月把 PB 付款和对账数据整理成给财务的对账表，并生成给中间人 TM 的 5% 佣金结算表。

- `reconcile_pb.py`：给财务对账表（追加付款、补录发票、截止判定、双开票映射、不重不漏校验、颜色标记、Notes 区块更新）。
- `tm_commission.py`：TM 佣金表（从给财务表过滤账期付款 + 按天截止发票，英文 Notes、5% 佣金、付款总额硬校验）。

**入口**：[AGENT_HANDOFF.md](AGENT_HANDOFF.md)（完整交接，Agent/人通用）→ [docs/](docs/)（OKF 文档）

**快速上手**：
```bash
python reconcile_pb.py --dry-run   # 给财务表报告（只读）
python reconcile_pb.py --write     # 生成时间戳新文件
python tm_commission.py --dry-run  # TM 佣金报告（只读）
python tm_commission.py --write    # 生成 To Tracy Miller 账期文件
```

数据文件在 `D:\Work\美国\Tracy Miller\PB orders\`（仓库外）。每次使用前改脚本顶部常量（当月邮件批次、发票文件夹、双开票映射、UPS 备注、账期）。
