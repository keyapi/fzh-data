# Codex EN_API 测试全记录

> 2026-06-08 | Codex (DeepSeek Flash) 三轮测试 EN_API CLI + Web UI 的完整记录

## 测试环境

- Agent: Codex CLI + DeepSeek Flash
- 项目: fzh-data `main` 分支
- 测试用例: D:\EN上传图片 目录下 10 张图片

## CLI 测试

**命令**: `cd EN_API && uv run python upload_local_images.py`

**结果**: ✅ 10 张全部成功
- 压缩率: 6091KB → 2497KB（减小 59%）
- 输出: `out/图片上传链接_20260608_135057.xlsx`

## Web UI 测试（三轮迭代）

### 第 1 轮：环境踩坑

| 尝试 | 方式 | 结果 |
|------|------|------|
| 1-3 | Start-Process / Start-Job 后台启动 | 进程存活但端口无监听 |
| 4 | 直接调用 `.venv\Scripts\python.exe` | 同上 |
| 5 | cmd /c start 新窗口 | 窗口一闪而过 |

**发现的卡点**:
1. uv cache 损坏 → 设 `$env:UV_CACHE_DIR` 绕过
2. PowerShell Start-Job 隔离 → 端口 Listen 但外部不可达
3. 端口 TIME_WAIT 残留

### 第 2 轮：启动仍然失败

前台运行 `uv run python image_upload_app.py`，进程不 crash 但 `Get-NetTCPConnection` 查不到端口。

**根因**: Claude Desktop 将 `uvicorn.run(log_level="warning")` 静音了启动日志，无法判断服务器是否成功绑定。

### 第 3 轮：成功

Claude Desktop 修复 `log_level="info"` 后：

```powershell
cd D:\Work\赛狐\Cursor\EN_API
uv run python image_upload_app.py --port 8099 --no-browser
netstat -ano | findstr :8099        # 确认监听
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8099/  # → 200
```

**MCP Playwright 全流程**:
1. navigate → http://127.0.0.1:8099/
2. setInputFiles → 3 张图片
3. snapshot → 确认缩略图 + 按钮可见
4. click "上传到 ERPNext"
5. 确认 "全部上传成功！共 3 张图片"
6. click "下载 Excel"
7. pandas 读取 xlsx 验证 URL

**API 响应**:
```
POST /api/upload-images → HTTP 200
X-Upload-Result: {"total": 3, "success": 3}
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
```

## 踩坑总结

### Codex 代码层
1. 没读 git log 和最新文档就动手（Claude Desktop 已在并行开发）
2. 硬编码 `base_url`，没遵循 `_DEFAULT_ENV = "prod"` 约定
3. 不该问"测试还是生产"——文档明确说普通用户不需要知道

### Codex 测试层
1. `Get-NetTCPConnection` 不可靠 → 用 `netstat -ano`
2. 在同一卡点用 5 种方式反复试 → 应更早停下来汇报
3. 没及时把文档交给 Claude 分析，自己死磕

### Claude 代码层
1. `log_level="warning"` 是根因——静音了启动确认信号，导致死循环
2. `_find_free_port()` 有 TOCTOU 竞态
3. 不应与 FilePond 内部布局打架

## Claude 修复清单

| 轮次 | 修复 |
|------|------|
| 第 1 轮 | `_find_free_port()` 端口自动切换 + uv cache 记录 + Start-Job 隔离记录 |
| 第 2 轮 | `log_level` 回退 `"info"` + 移除竞态端口检测 + 启动验证指引 |
| 第 3 轮 | 图片压缩 (Pillow) + CSS Grid 响应式布局 + 文档更新 |
