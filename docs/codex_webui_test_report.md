# Codex Web UI 测试全流程报告

> 2026-06-08 | 第三次测试（最终回合）| 全流程通过

---

## 背景

Claude Desktop 3 轮修复后，Codex 最终成功完成 Web UI 全链路 MCP 测试：

### Claude 修复清单

| 轮次 | 修复 | 说明 |
|------|------|------|
| 第1轮 | _find_free_port() 端口自动切换 | 端口被占时找 8100-8119 |
| 第1轮 | uv cache 处理记录到 AGENTS.md | 用 uv cache clean 替代 m -rf |
| 第1轮 | 记录 Start-Job 隔离问题 | Lesson 58 |
| 第2轮 | **log_level 回退 "info"** | 根因！"warning" 导致启动信息静音 |
| 第2轮 | 移除 _find_free_port() | TOCTOU 竞态（先 bind 检测→释放→uvicorn 再 bind） |
| 第2轮 | AGENT_HANDOFF.md 启动验证指引 | curl 200 确认 + 已踩坑清单 |
| 第2轮 | AGENTS.md Lesson 59 | uvicorn log_level 永远不要用 warning |

---

## CLI 测试结果

命令: cd EN_API && uv run python upload_local_images.py

- 10 张图片全部上传成功
- 压缩率: 6091KB → 2497KB（减小 59%）
- 输出: out/图片上传链接_20260608_135057.xlsx

---

## Web UI 测试结果

### 启动方式（已验证可用）

`powershell
cd D:\Work\赛狐\Cursor\EN_API
 = "C:\Users\zhang\AppData\Local\Temp\uv-cache"   # uv cache 损坏时需加
uv run python image_upload_app.py --port 8099 --no-browser
`

启动后验证:
`powershell
netstat -ano | findstr :8099          # 查看监听状态（可靠）
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8099/   # 应返回 200
`

### MCP Playwright 操作步骤

`yaml
步骤1: browser_navigate → http://127.0.0.1:8099/
步骤2: browser_run_code_unsafe → setInputFiles([3张图片]) 到 FilePond 的 input[type="file"]
步骤3: browser_snapshot → 确认 3 张缩略图 + "上传到 ERPNext" 按钮可见
步骤4: browser_run_code_unsafe → click "上传到 ERPNext" 按钮
步骤5: browser_network_request → 查看响应头
步骤6: browser_snapshot → 确认 "全部上传成功！共 3 张图片" + "下载 Excel" 按钮
步骤7: browser_run_code_unsafe → click "下载 Excel"
步骤8: Python pandas → 读取下载的 xlsx，验证 URL
`

### API 响应

`
POST /api/upload-images → HTTP 200
x-upload-result: {"total": 3, "success": 3}
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; 图片上传链接_20260608_141755.xlsx
`

### 验证

3 张图片的完整 URL 均可从下载的 Excel 中获取，格式:
`
https://erpnext.vilavi.cn/files/{filename_hash}.jpg
`

---

## 两次踩坑总结（给 Codex 自省）

### 第一次（写代码）踩坑

1. **没读 git log 和最新文档就动手** — Claude Desktop 已经在并行开发同样的功能
2. **默认环境写错** — 硬编码 ase_url，没遵循 AGENT_HANDOFF.md 的 _DEFAULT_ENV = "prod"
3. **不该问"测试还是生产"** — 文档明确说普通用户不需要知道环境概念

### 第二次（Web UI 测试）踩坑

1. **Get-NetTCPConnection 不可靠** — 后台进程的端口查不到。应该用 
etstat -ano
2. **在同一个卡点上用 5 种方式反复试** — 第 6 次已经发现了核心现象（前台跑不 crash 但查不到端口），之后 5 次都是浪费
3. **没及时停下来给用户汇报** — 应该更早向上反馈，把文档给 Claude 分析，而不是自己死磕

### 第三次（最终测试）

成功。关键改进:
1. 先停、读文档、读 git log，知道什么已存在
2. 
etstat -ano 替代 Get-NetTCPConnection
3. Python requests 直接确认 API 正常，再做 MCP 前端测试

---

## 待处理问题

| 问题 | 建议处理方 |
|------|-----------|
| uv cache 损坏（C:\Users\zhang\AppData\Local\uv\cache），每次需设 UV_CACHE_DIR 绕过 | Claude |
| 测试启动的服务器仍在 8099 运行，需要停下 | 可忽略（Ctrl+C） |
