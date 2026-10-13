---
type: Materials
title: 工单驱动渠道接入助手 · 演示材料
date: 2026-10-13
status: simulation-data
---

# 演示材料（全部模拟）

> 下列机构、终端、地址、端口、规则与结果均为模拟；不接真实银行、不接 ERPNext、不发外网请求。
> 来源：`bank_tasks.py`（工单/知识）与 `bank_ops.py:initial_bank()`（初始数据）。工单可从前台「交付材料」下载。

## 1. 初始数据（`initial_bank()`）

终端（1 条）：

| id | terminal_code | tenant | max_concurrency | protocol | sign | callback_mode | endpoint | environment |
|---|---|---|---|---|---|---|---|---|
| TERM-DEMO-001 | DEMO-001 | DEMO-BANK | 8 | HTTPS | HMAC-SHA256 | SYNC | https://192.0.2.10:8443/demo | test |

参数（3 条，均属 TERM-DEMO-001）：

| id | name | value | value_type |
|---|---|---|---|
| PARAM-DEMO-001 | timeout_seconds | 30 | number |
| PARAM-DEMO-002 | retry_count | 2 | number |
| PARAM-DEMO-003 | api_secret | DEMO_SECRET（前台遮蔽 ••••••） | secret |

固定 IP（2 条，主用 + 备用）：

| id | front_address:port | client_address | client_port | 说明 |
|---|---|---|---|---|
| IP-DEMO-001 | 192.0.2.10:8443 | 198.51.100.10 | 8080 | **主用**，本任务目标 |
| IP-DEMO-002 | 192.0.2.11:8443 | 203.0.113.10 | 8080 | **备用链路，不得修改** |

## 2. 版本化知识（`DOCUMENTS`）

| id | version | status | 内容要点 |
|---|---|---|---|
| CHANNEL-ASYNC | 2.0 | active | 标准异步档：并发 12、异步回调、超时 60、重试 1、须启用幂等；保守异步档：并发 4、异步回调、超时 45、重试 0、须启用幂等 |
| CHANNEL-TEMPLATE | 1.0 | **superseded** | 旧栏位：并发 8、同步回调、超时 30、重试 2。**仅用于解释冲突，不能作为目标来源** |
| CHANNEL-VERIFY | 1.0 | active | 保存后独立读回三页，核对未触及备用链路与敏感占位，再运行模拟回调契约 |

档位常量：`PROFILES = {'standard': (12, 60, 1), 'conservative': (4, 45, 0)}`。

## 3. 三份工单

### WO-DEMO-001 · 标准档（主演示，缺端口）

原文（可在前台展开/下载）：

> 渠道测试接入工单 WO-DEMO-001（模拟）。渠道：星河对公服务；终端代码 DEMO-001；租户 DEMO-BANK / TENANT-DEMO-01；本次申请按「标准异步回调」接入档完成测试环境接入。工单采用接入模板1.0，旧模板栏：新增终端、最大并发8、同步回调、超时30秒、重试2次。目标前置192.0.2.10:8443，客户端198.51.100.10，实际监听端口待渠道补充。接入地址 https://192.0.2.10:8443/demo，签名HMAC-SHA256，编码UTF-8。请沿用既有终端身份，不创建重复代码；按当前生效规范校准模板项，补齐必备注册参数。只办理这份工单涉及的测试记录，不调整备用链路。

配夹具：`callback_receiver=accept`；唯一缺项 `client_port`（讲者补答 9443）。

### WO-DEMO-002 · 保守档（端口已填）

同终端、同前置与目标客户端，工单明确「保守异步」，客户端端口已填 `8443`；同样夹带模板 1.0 默认栏。
**模型应无需追问**，形成与 001 不同的实际值（4/45/0/8443），证明目标来自工单所选档位而非固定脚本。

### WO-DEMO-003 · 验收失败与恢复

业务同 001，端口已给 `9443`。配模拟联调夹具 `callback_receiver=reject`（由后台固定，模型不可修改）。
整组保存与独立读回可成功，**模拟回调契约测试返回失败**；页面显示「已保存，模拟验收未通过」，恢复按钮生成整组逆向方案，确认后回到执行前状态并删除本任务新增的幂等参数。

## 4. 默认主线预期结果（001）

确认前：数据库完全不变（`version=1`）。
确认后（`version=2`）：

| 页 | 记录 | 变更 |
|---|---|---|
| 终端 | TERM-DEMO-001 | max_concurrency 8→12；callback_mode SYNC→ASYNC |
| 参数 | PARAM-DEMO-001 | value 30→60 |
| 参数 | PARAM-DEMO-002 | value 2→1 |
| 参数 | 新增（后台生成 ID） | name=idempotency_enabled，value=true，value_type=text |
| 固定 IP | IP-DEMO-001 | client_port 8080→9443 |

**未触及（后台验收断言）**：IP-DEMO-002（备用链路）、PARAM-DEMO-003（`api_secret` 占位）、柜面限额、联调配置、所有生产配置。

## 5. 模拟标识一览

- 终端/参数/IP：均属 `DEMO-` 前缀的模拟记录，环境 `test`。
- 地址：`192.0.2.0/24`、`198.51.100.0/24`、`203.0.113.0/24` 均为文档保留网段（不可路由）。
- 敏感项：`api_secret` 只允许 `DEMO_` 开头的固定占位，前台一律遮蔽。
- 登录：`operator/reader/reviewer` + 公开口令 `demo2026`，是模拟身份，非银行 SSO。
- 验收：本地确定性模拟契约，非真实网络连通性、非压测、非生产认证。
