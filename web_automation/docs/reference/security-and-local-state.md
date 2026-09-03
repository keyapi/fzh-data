---
okf: v0.1
type: Reference
title: 安全边界与本地状态
description: profile/cookie/凭证只在本机，首次人工登录，OCR 可选，写操作范围确认
tags: [security, local-state, cookies, profile, credentials]
---

# 安全边界与本地状态

## 状态只在本机

- 浏览器持久 profile：`web_automation/chrome-profile/`（通途）、`web_automation/sellfox-profile/`（赛狐）。
- cookies、`.env`、downloads/output、截图、debug DOM/JSON、业务 Excel 全部 gitignored（子目录 + 根 .gitignore 双重防线）。
- 凭证只从本地 `.env` / 环境变量读取，不进入代码、不进入 git。

## 登录策略

- **首次登录优先人工**：浏览器打开，人手动登录一次，cookie 持久化到 profile，后续免登录。
- **OCR 是可选便利**：`ddddocr`/`onnxruntime` 属于可选 dependency group；只有用户明确要"全自动识别验证码"时才 `--with-ocr`。
- 系统级缺失（Windows VC++ 运行库等）只报告 `BLOCKED` + 建议，不自动改系统；安装前向用户确认。

## 写操作范围确认

- 其他入库/出库/备货单导入等写操作必须 `--confirm-scope "具体文件/SKU/仓库范围"`。
- dispatcher 没有范围确认时返回 `NEED_USER_CONFIRMATION`（exit 3），不执行。
- 修改库存数量/成本前必须导出库存备份，修改后再导出对照；零库存 SKU 有成本也要导（取消"隐藏0数据"）。
- 默认只用测试/目标商品（如 test001-white），绝不扩大到全量。

## 凭证扫描

提交前执行 AGENTS.md 第 9 条 4 个 regex；任何文档/示例若命中，改成明显占位符，不跳过扫描。
