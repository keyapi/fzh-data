# Codex Web UI 测试二次遇阻记录

> 2026-06-08 | 补充上一份文档 | Claude Desktop 修了端口自动切换后 Codex 仍然无法启动

---

## 背景

Claude Desktop 上次分析后修了 3 个问题：
1. _find_free_port() — 端口被占自动切换 8099→8100~8119
2. uv cache 损坏 — 用 uv cache clean 替代 m -rf
3. 确认 Start-Job 有 Windows 隔离问题，不要用

## Codex 第二次测试过程 (仍然失败)

### 测试步骤

| 尝试 | 方式 | 结果 |
|------|------|------|
| 1 | Start-Process powershell -WindowStyle Hidden 后台启动 | 进程存在，端口无监听 |
| 2 | Start-Process powershell -NoExit | 同上 |
| 3 | cmd /c start 新 cmd 窗口 | 窗口一闪而过，无监听 |
| 4 | Start-Process .venv\Scripts\python.exe 直接调用 | python 进程存活但端口无监听 |
| 5 | .bat 批处理 → Start-Process | 同上 |
| 6 | 直接运行 uv run python image_upload_app.py --port 8111 (前台) | 进程超时(不退出)，但 Get-NetTCPConnection 仍查不到端口 |

### 核心现象

前台运行 uv run 不会 crash（进程存活直到 timeout 杀死），但 Get-NetTCPConnection 始终查不到监听。

### 给 Claude 的问题

1. 你在本地启动 image_upload_app.py 时有没有遇到过同样问题？
2. .venv 目录名含中文"赛狐"是否需要处理？
3. 能否加 uvicorn 绑定日志来调试？
4. 能否 webbrowser.open 改为输出 URL 让人手动打开？
5. 能否加 print("Binding port...") 在 uvicorn.run 前排查卡在哪一步？
