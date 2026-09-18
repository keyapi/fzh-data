# gls_track — GLS 单号批量查轨迹（公开无鉴权 REST，免账号）

波兰分公司(GLS 波兰自发货)的 GLS 跟踪码批量查询。**不需要开发者账号、不需要波兰 GLS 登录**：
走 `gls-group.com` 的公开 REST（实证见 `docs/research/2026-09-07-gls-poland-track-feasibility.md`）。

> 定位：最小可用客户端原型。将来 GLS 进 `parcel_track`(PR #215) 时按官方/公开二选一对齐；本模块只出状态/时间线，
> 不做迟发/延误/卡件分类（那在 parcel_track 共享 classify）。

## 怎么跑

```bash
# 通途月度文件直接筛 GLS 行（按 邮寄方式 前缀默认 gls-poland；去重；取目的邮编）
python -m gls_track.cli query --input <通途非FBA订单….xlsx> --out result

# 或 txt：每行 `跟踪号 [目的邮编]`；有邮编才出明细，无邮编只出摘要(状态)
python -m gls_track.cli query --input nos.txt --out result

# 小样本试跑 / 并发 / 断点续跑
python -m gls_track.cli query --input <….xlsx> --out result --limit 20 --workers 4
python -m gls_track.cli query --input <….xlsx> --out result --workers 6   # 整月 ~1200 号约几分钟
python -m gls_track.cli query --input <….xlsx> --out result --resume      # 跳过已查的号

# 整月一条命令：批量查 + 直接出运营异常表（FedEx 风格，8 Sheet）
python -m gls_track.cli monthly --input <当月tongtu.xlsx> --out gls_202608 --workers 4
#   → gls_202608.summary.csv / .timeline.csv / gls_202608_ops.xlsx


并发/限流（2026-09-07 实测 gls-group.com 公开 REST）：接口**无速率头、无公开限流文档**；有界探针
workers 1/4/8 全部 200、无 429/403/验证码，单请求中位 ~0.6s。属消费级接口**无 SLA**，默认 `--workers 4`
保守；不建议无上限并发。已用共享 httpx 连接池 + transport 错误重试 1 次。
```

输出（同一前缀）：`result.summary.csv`（每包裹一行）+ `result.timeline.csv`（每节点一行）。

## 运营异常报表（FedEx 风格）

大批量查完后生成与 FedEx 运营异常表同版式（Amazon 口径 · 营业日）的多 Sheet Excel：

```bash
python -m gls_track.ops_report --summary result.summary.csv --tt <通途非FBA订单….xlsx> --out gls_ops.xlsx
```

判定对标 FedEx（时点映射见 `ops_report.py` docstring）：建标≈数据录入 GLS IT、收件≈交接 GLS、交付=delivered；迟发 / 承运延误 / 卡件 / 漏发未交接 等分类与「总览 / 异常处理 / 漏发未交接 / 迟发 / 承运异常 / 取消·其他 / 全部明细 / 口径说明」Sheet 与 FedEx 表一致。**GLS 口径参数**：`HANDLING_DAYS=3`（与 parcel_track UPS/FedEx 统一）；营业日排除用**波兰 2026 公共假日**（数据录入/交接都在 GLS 波兰；`PL_HOLIDAYS_2026`）；周末天然不计；「Amazon是否判迟」仅对 Amazon/亚马逊 渠道标记。改顶部常量即可重跑（同 FedEx 表用法）。待 PR#215 合入后 gls adapter 改走 parcel_track 共享 classify。

## 端点（实测 2026-09-07）

- 摘要（无邮编，状态/交付时间）：`GET https://gls-group.com/app/service/open/rest/PL/en/rstt029?match={号}&type=&caller=witt002&millis={ms}`
- 明细（需目的邮编 → 全量 history）：`GET …/rstt028/{号}?caller=witt002&millis={ms}&postalCode={邮编}`

有邮编时只调明细一次即可（detail 已含 status + history + arrival）。无邮编退化为摘要（rstt029）。

## 关键时点（对 ops 迟发/延误/卡件口径）

history 中按关键词兜底提取（EN 描述，`gls_track/models.py`）：
- 数据录入 GLS IT ≈ **建标/预报**（"...data was entered into the GLS IT system..."）
- **交接 GLS**（"The parcel was handed over to GLS."；注意排除"not yet handed over"，那是建标文案）
- **交付**（delivered 事件 / arrivalTime）

## 实测样本（2026-08 通途，2026-09-07 跑 25 号）

24/25 查通：DELIVERED 23、INTRANSIT 1；1 个 `1048249357601U`(allegro) 404——**非 GLS 单号**（U 后缀不是 GLS parcel，
将来 route 应按号形态过滤，别把这类行当 GLS）。交付号能回连 `客户引用`(CUSTREF，P8…) 到订单。

> 已知边界：部分包裹先有 DELIVERED 事件后又回退（如返件 `29626350320` 08-10 派送、08-14 回 Strykow 仓），
> GLS 头条状态为 INTRANSIT——**头条状态以 `当前状态`(statusInfo) 为准**，history 留着看回退细节。

## 测试

```bash
python -m pytest gls_track/tests -q    # 离线（httpx MockTransport），无需网络
```

## 凭证

无。可选 env：`GLS_BASE_URL`（换非 PL 实例/国别）、`GLS_HTTP_PROXY`。
