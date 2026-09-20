# 文档变更日志

## 2026-09-20

- **补齐索引**：新建 `reference/index.md` 与 `test-guide/index.md`（OKF v0.1 `type: Index`）。`README.md` 中指向这两处的链接（`docs/reference/index.md`、`docs/test-guide/index.md`）**恢复有效** —— 此前因目标文件从未创建，只能退而链接目录本身。
- **修复（链接）**：`carriers/index.md` 中 7 条指向从未创建的 `endpoints*.md` 的链接改为对应承运商的 `overview.md`（端点表实际写在 overview 内，含「端点（国内）」「端点（国际）」两节）。

## 2026-07-20

- EEVEE 密码/邀请码/真实邮箱从 `test-credentials.md` 与 `.env.example` 移除，改为占位符 + 根 `.env`
- 文档化环境变量策略：`VITE_API_KEY` / `VITE_API_BASE_URL` 跨环境同名只换值

## 2026-07-16

- 初始文档创建
- 完成 Vite API 所有接口文档
- 包含: 参考文档、承运商文档、回标标签、Webhook、测试指南
