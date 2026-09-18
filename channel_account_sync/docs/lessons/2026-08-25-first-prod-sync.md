---
okf: v0.1
type: Lesson
title: 2026-08-25 渠道账号第一次写入生产
timestamp: 2026-08-25
---
# 2026-08-25 渠道账号第一次写入生产

## 什么有效

- 先改 Google 表（拆掉 `AMZFZHSXEUR`），再对 EN。
- Owner 按切变算：已有账号 122 个只要 189 行，不是按月 367 行。
- Canary 先 PUT `AMZFZHSXUS` 加 `林俊彪` @ 2026-07-01，200 后才批量创建。
- `NoExpect` adapter：Frappe 对 `Expect: 100-continue` 回 417。
- GET 父文档拿子表；不要依赖 child DocType list。

## 什么无效 / 未做

- 按每个月插一行 Owner：重复同人，用户否决。
- 建 `AMZFZHSXEUR`：Amazon 没有欧洲聚合站。
- Cursor 自动审批曾挡住试写，本机放行后才成功。
- `Operation Staff Settings` 当时只有 3 行（波兰→波兰分公司，尹天强/宋唯一→北京分公司），本次**没有**补全中文名对照。现网 Owner 仍写中文名且 PUT 成功。

## 写入结果（生产，2026-08-25 12:03）

- Kaufland 区域补 AT/IT/FR
- 新建 Illiosenergy / ILLIOS
- CREATES 18/18，ALIASES 10/10，OWNERS 122/122，失败 0
