---
okf: v0.1
type: Reference
title: ups_track 批量查询运行手册 + 2026-09-03 真实单验证
description: 批量 UPS 跟踪号查询用法/输出三件套/生产只读验证记录（5 个真实 PB 单全部吻合）
updated: 2026-09-03
---

# ups_track 批量查询运行手册（含真实单验证记录）

> 需求形态：**一堆 UPS 跟踪码 → 批量查询跟踪节点信息 → 每号汇总 + 完整节点时间线**。
> 本文档 = 用法 + 2026-09-03 在生产(prod)跑 5 个真实 PB 跟踪号的记录。Track 查询为**只读**、不产生计费，可放心跑，但仍建议小并发、必要时限速。

## 一、用法

前置：凭证在本机 `.env`（见 [ups-developer-account-setup.md](ups-developer-account-setup.md)），加载后运行：

```bash
cd <repo> && set -a && . ./.env && set +a
python -m ups_track.cli query \
  --input <清单.csv> --env prod --out <输出前缀> \
  --workers 4 --retries 1          # 生产更谨慎：--workers 2 --delay 0.3
```

输入清单（`tracking.txt` 或 `tracking.csv`）：

```csv
tracking,发票号            # 首行可为表头；首列跟踪号，其余列原样透传为备注
1ZC0019E0301406005,INV...1362
```

输出三件套（同一前缀）：

| 文件 | 内容 |
|------|------|
| `<前缀>.summary.csv` | 每号一行：备注/已交付/当前状态/交付日期城市州/建标/实际发货/最近节点/错误 |
| `<前缀>.timeline.csv` | 每号**每个节点一行**：时间/状态类型码/描述/城市州邮编 |
| `<前缀>.raw.json` | 每号原始响应（留档 + `--resume` 依据） |

## 二、2026-09-03 生产实跑记录（5 个真实 PB 单）

输入取自 PB 对账 2026-08-14 核查那批真实 UPS 号（见 `pb_reconciliation/docs/reference/ups-delivery-check.md`），
用 `--env prod --workers 2 --delay 0.2 --retries 1` 跑：

```bash
python -m ups_track.cli query --input ups_real5.csv --env prod --out ups_batch_result --workers 2 --delay 0.2
```

结果：**5/5 成功，均 DELIVERED，0 失败、0 查无此号**；明细 58 个节点逐行输出。

汇总列（交付/建标/实际发货）与人工核查逐条一致：

| 跟踪号 | 发票 | 建标(Label) | 实际发货(WeHaveYourPackage) | 交付(Delivered) | 交付地 |
|---|---|---|---|---|---|
| 1ZC0019E0301406005 | INV…1362 | 2026-06-09 | 2026-07-30 | 2026-08-04 | West Roxbury MA |
| 1ZC0019E0314557560 | INV…1507 | 2026-07-02 | 2026-07-20 | 2026-07-23 | Blue Ash OH |
| 1ZC0019E0318578736 | INV…1521 | 2026-07-06 | 2026-07-20 | 2026-07-23 | Maspeth NY |
| 1ZC0019E0327032370 | INV…1528 | 2026-07-06 | 2026-07-20 | 2026-07-23 | East Aurora NY |
| 1ZC0019E0329334504 | INV…1535 | 2026-07-06 | 2026-07-20 | 2026-07-23 | Valencia CA |

> 结论：OAuth + Tracking 在 prod 可用；事件词表（Label Created / "We Have Your Package"/Arrived / Delivered）提取与真实数据吻合。

## 三、时间线形态示例（timeline.csv）

```
跟踪号,备注,节点时间,状态类型,状态码,描述,城市,州,邮编
1ZC0019E0301406005,发票号=INV…,2026-06-09 03:40:36,M,MP,Shipper created a label…, , ,
1ZC0019E0301406005,发票号=INV…,2026-07-30 22:01:16,I,OR,Arrived at Facility,Stafford,TX,
1ZC0019E0301406005,发票号=INV…,2026-07-31 04:40:00,I,DP,Departed from Facility,Stafford,TX,
…（每节点一行，直到 Delivered）…
```

## 四、注意事项（生产）

- Track 只读、免费；但**新一批大批量清单上线前**先抽 1~2 个号核对。
- UPS 限流阈值未知 → 大批量用 `--workers 2~4`；遇 429 自动退避重试（`--retries`）。
- 单号失败不中断（summary 的"错误"列 + 结尾计数），可用 `--resume` 续跑失败号。
- 国内网络连 onlinetools.ups.com 不通时设 `UPS_HTTP_PROXY`。
- 凭证只在本机 `.env`，**勿提交/外发**；批量输出若含业务单号，注意数据保管范围。

## 五、2026-09-03 实跑记录 #2：X34（34 件 / 39 个 Pack 级跟踪号）

源文件（**含客户信息，勿提交仓库**，仅本机）：`D:\下载\shipment x34 20260831_0357_845701.csv`

解析要点（`Pack Level Carrier Tracking ID` 列，位于表头第 43 列，索引 42）：
- 该 CSV 为单表：1 表头 + 34 行（对应 34 个发货单/件）。
- **34 行均有 Pack 级跟踪号**；29 行 Pack=Carrier 同号，**5 行是多包件**，其 Pack Level 单元格内含**多个跟踪号**（空格/换行分隔）——需按 1Z 号切分（正则 `1Z[A-Z0-9]{16}`），因此**去重后共 39 个唯一 UPS 号**（5 件多包各 +1）。

执行（prod 只读）：

```bash
python - <<'PY'   # 解析源文件 → x34_in.csv（tracking,备注=ASN|收件人|城市 州）
# …见会话脚本思路：csv 读入→col42 按 1Z 切分→去重→写清单
PY
python -m ups_track.cli query --input x34_in.csv --env prod --out x34_result --workers 2 --delay 0.25 --retries 1
```

结果与核对：

| 项 | 值 |
|---|---|
| 查询数 | **39/39 成功**；0 失败、0 查无此号 |
| 状态 | **3 已交付**（09/02：Orland Park IL / Dallas TX / Houston TX，交付城市与收件城市一致）+ **36 在途**（Ship 09/01，正常） |
| 核对方法 | 合并源文件 ASN/收件城市 → 检查：失败、查无此号、已交付但城市与收件城市不符；结果无真异常（仅交付城市大写不带州的提示，属同一城市） |
| 产物 | `x34_result.summary.csv / .timeline.csv / .raw.json` + `x34_check.csv`（核对表，含 跟踪号/ASN/状态/交付/三时点/期望收件城市/异常列） |

> 结论：**含多包（同单多个跟踪号）的批量场景可用同一命令处理**；逐件核对表可直接对回源文件。

