---
okf: v0.1
type: Log
module: drive_folder_ops
created: 2026-11-03
updated: 2026-11-03
---

# drive_folder_ops — 变更日志

- **新增**: 本模块与 `drive_folder_ops/drive_folder_ops.py`。背景：mxdeals1023@gmail.com 的「FZH运营知识中心」需要让 Agent 写 Markdown 知识文档；该文件夹已共享给现有服务账号，不需要新凭证或用户 OAuth。
- **核实**: 根文件夹 ID `1RGSCHVGlCFQz7cAdMtdL66VU45758ntp`，属主 mxdeals1023，SA 角色 `writer`。目录结构：6 个业务子文件夹（运营2/3/4部、00_候选与修正、30_已审核知识、90_归档）+ 1 个 Markdown，0 个表格。
- **实测**: `smoke-test --apply` 结果 `md_create/sheet_create/sheet_rw/doc_create/cleanup` 全部 OK；`write` 的创建 → 回读 → 覆盖 → 备份 → 清理也通过。服务账号在本文件夹可以新建 Markdown（存储配额未拦），但其他文件夹仍可能被拦，工具保留明确报错。
- **环境**: 本机 IPv6 到 Google 不通，`www.googleapis.com` 偶发 SSL EOF；模块强制 IPv4、指数退避，并在失败后切换 `content.googleapis.com`。
- **文档**: 新增 `google_drive_permissions/docs/reference/share-folder-with-service-account.md`，说明「共享给机器人即可，无需新凭证」；`google_drive_permissions` 与 `secrets/README.md` 增加交叉引用。
