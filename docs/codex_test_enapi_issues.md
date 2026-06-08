# Codex 测试 EN_API 遇阻记录

> 2026-06-08 | 用于给 Claude Desktop 分析 Web UI 启动问题

---

## 1. 当前 repo 状态

最新 3 个 commit 均为 Claude Desktop（keyapi）今天所做：

| Commit | 说明 |
|--------|------|
| 51113e2 | feat(EN_API): 本地图片上传 CLI + Web 可视化工具 |
| dd94af0 | fix(EN_API): 重构缩略图为独立网格布局，修复按钮消失和页面塌缩 |
| c8436e5 | feat(EN_API): 图片压缩 + 响应式网格布局 + 文档更新 |

### 当前脚本

EN_API/ 目录下三个脚本：

| 脚本 | 功能 |
|------|------|
| upload_item_images.py | 赛狐图片链接 Excel → 更新 Item Group 主图 |
| upload_local_images.py | **CLI** 批量上传本地图片到 ERPNext |
| image_upload_app.py | **Web UI** 拖拽上传+排序 (FastAPI + 静态 HTML) |

另外还有 EN_API/static/index.html 前端页面。

---

## 2. CLI 测试结果 (成功)

upload_local_images.py 运行正常，10 张图片全部成功上传到生产环境：

`ash
cd EN_API && uv run python upload_local_images.py
`

输出：out/图片上传链接_20260608_135057.xlsx

---

## 3. Web UI 测试过程 (卡死，未成功)

### 尝试记录

#### 尝试 1: Start-Process 后台启动

`powershell
Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command", "cd D:\Work\赛狐\Cursor\EN_API; uv run python image_upload_app.py --port 8100; pause"
`

- 结果: 进程启动但 3 秒后查不到端口监听
- 可能原因: -WindowStyle Hidden 导致进程被隐藏过早回收

#### 尝试 2: Start-Process 无 Hidden

`powershell
Start-Process powershell -NoExit -ArgumentList "cd D:\Work\赛狐\Cursor\EN_API; uv run python image_upload_app.py"
`

- 结果: 同样看不到端口绑定
- 但 Get-Process 能看到 python 进程存在

#### 尝试 3: Start-Job 后台作业

`powershell
 = Start-Job -ScriptBlock { Set-Location D:\Work\赛狐\Cursor\EN_API; uv run python image_upload_app.py --port 8100 }
Start-Sleep 5
Receive-Job .Id
`

- 结果: 看到 Uvicorn running on http://127.0.0.1:8100 的日志输出
- 但 Get-NetTCPConnection -LocalPort 8100 查不到监听
- 确认: 作业显示 State=Running，但 8100 端口无 TCP 监听

#### 尝试 4: uv cache 损坏

`powershell
uv run python -c "import fastapi"
→ error: Failed to initialize cache at C:\Users\zhang\AppData\Local\uv\cache
             Caused by: 当文件已存在时，无法创建该文件。
`

- 原因推测: 之前的 Remove-Item -Recurse -Force C:\Users\zhang\AppData\Local\uv\cache 后系统重新创建了同名目录而非文件，uv 无法重新创建
- 临时修复: $env:UV_CACHE_DIR = "C:\Users\zhang\AppData\Local\Temp\uv-cache" 后 uv run 正常

#### 尝试 5: 使用 UV_CACHE_DIR 后重试

设置 $env:UV_CACHE_DIR 后，Web UI 能正常打印启动日志，但仍然出现：

`
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8101): 
通常每个套接字地址(协议/网络地址/端口)只允许使用一次。
`

即端口已被占用（之前未清理干净）。

#### 尝试 6: 彻底清理进程后成功启动

`powershell
Get-Process -Name python* | Stop-Process -Force
Start-Sleep 2
 = "C:\Users\zhang\AppData\Local\Temp\uv-cache"
 = Start-Job -ScriptBlock { ... uv run python image_upload_app.py --port 8102 --no-browser }
Start-Sleep 5
Get-NetTCPConnection -LocalPort 8102 → State=Listen  (成功!)
`

端口 8102 显示 **Listen** 状态。

#### 尝试 7: 访问 Web UI 被拒绝

`
Python urllib → ConnectionRefusedError: [WinError 10061]
Node REPL fetch → fetch failed
curl → 无响应
`

尽管 Get-NetTCPConnection 显示端口 8102 在 Listen，所有 HTTP 请求都连接被拒。

### 卡点总结

| # | 卡点 | 说明 |
|---|------|------|
| 1 | **uv cache 损坏** | C:\Users\zhang\AppData\Local\uv\cache 被误创建为目录而非文件，需 $env:UV_CACHE_DIR = "C:\Users\zhang\AppData\Local\Temp\uv-cache" 绕过 |
| 2 | **PowerShell 后台进程难管理** | Start-Process / Start-Job 启动的进程存在但非预期行为，stdout/stderr 难捕获 |
| 3 | **端口 TIME_WAIT** | 多次启动失败导致端口残留（8100 在 TIME_WAIT），新进程无法绑定 |
| 4 | **端口 Listen 但 HTTP 连接被拒** | 最大疑点。Get-NetTCPConnection 显示 8102 在 Listen，但所有 HTTP 客户端都连不上。推测：Background Job 中的 uvicorn 进程可能刚 bind 就被终止（父 PowerShell 进程退出导致子进程死亡），或者端口监听在某些隔离环境下不可达 |

---

## 4. 我犯的错误总结（供 Codex 自省）

1. **没有先读文档和 git log** — 写 upload_local_images.py 之前没看 Claude Desktop 已提交的代码，导致重复造轮子
2. **默认环境错误** — 硬编码了 ase_url = "https://erpnext.vilavi.cn"，没遵循 AGENT_HANDOFF.md 里 _DEFAULT_ENV = "prod" 的约定
3. **不该问"测试还是生产"** — 文档明确说普通用户默认用 prod，不需要问
4. **Web UI 反复尝试陷入死循环** — 应该更早意识到环境问题（uv cache、端口残留）并停下来给用户汇报
