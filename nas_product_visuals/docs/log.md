---
okf: v0.1
type: Log
title: 变更 + 调试日志
description: NAS ACL 权限修复脚本 fix_design_permissions.sh 的完整变更记录和调试过程
tags: [nas, synology, bash, acl, inotify, debug, lessons-learned]
---

# 变更 + 调试日志

## 2026-06-24 — fix_design_permissions.sh 完整调试

### 最终结论

v1.0 完成。4 个设计稿文件夹各只有 1 条 deny ACE，inotify 监控正常运行。

### 最终部署状态

| 项 | 值 |
|----|-----|
| NAS IP (局域网) | `192.168.1.5:31022` |
| NAS 域名 | `fzh.myds.me:31022` |
| SSH 用户 | `fzh.nas` |
| DSM 任务用户 | `root` |
| 脚本路径 | `/volume1/技术部/fix_design_permissions.sh` |
| DSM 命令 | `flock -xn /volume1/技术部/.fix_design.lock -c '/bin/bash /volume1/技术部/fix_design_permissions.sh'` |
| 测试 BASE_PATH | `/volume1/技术部` |
| 生产 BASE_PATH | `/volume1/产品信息` |

### 原始 Bug 清单

#### Bug 1: BASE_PATH 指向生产而非测试 (无影响)

同事原脚本 `BASE_PATH="/volume1/产品信息"`。当前测试阶段改为 `/volume1/技术部`，上线后改回。

#### Bug 2: inotifywait 不在 PATH

`/usr/local/bin` 不在 fzh.nas 和 root 的 PATH (`/usr/bin:/bin:/usr/sbin:/sbin`)。
`command -v inotifywait` 永远失败。改为绝对路径 `/usr/local/bin/inotifywait`。

#### Bug 3: 管道 subshell 导致计数器恒为 0

`find | while read` 管道右侧在 subshell，`((count++))` 不可传递。
改为进程替换 `while ... done < <(find ... -print0)`。

#### Bug 4: maxdepth 4 限制可能不够

用户文件夹下可能存在更深嵌套。移除 `-maxdepth`。

### 调试过程中发现的深层 Bug

#### Bug 5 (CRITICAL): POSIX locale 导致 echo 破坏 UTF-8

**发现过程**:
1. 反复测试发现删除重建设计稿文件夹后始终有 N 条重复 deny
2. 加详细日志发现 `fix_one` 的 deny 检查 (`grep "视觉需求（读取）"`) 永远返回"没找到"
3. 对比测试: `synoacltool -get > file; grep file` 正常 vs `echo "$acl" | grep` 失败
4. 定位到 `echo` 内置命令在 `LC_CTYPE=POSIX` 下破坏多字节 UTF-8 字符

**根因**: 群晖默认 locale 为 POSIX，bash `echo` 内置命令在此 locale 下对含全角括号 `（）`(U+FF08/U+FF09) 的字符串进行字节截断。

**修复**: 不使用 `echo "$var" | grep`，改为直接管道:
```bash
# ❌ 错误 (POSIX locale 下 echo 破坏 UTF-8)
acl=$(synoacltool -get "$dir")
echo "$acl" | grep "$TARGET_GROUP" | grep -q "deny"

# ✅ 正确 (直接管道, 不经 echo)
synoacltool -get "$dir" 2>/dev/null | grep -F "视觉需求" | grep -q "deny"
```

**检查方法** (新对话验证):
```bash
# 如果这个返回空, 说明 echo 在破坏中文字符
acl=$(synoacltool -get /path/to/dir)
echo "$acl" | grep -F "视" | wc -l  # POSIX locale 下可能为 0
# 正确做法
synoacltool -get /path/to/dir | grep -F "视" | wc -l  # 一定 > 0
```

#### Bug 6 (CRITICAL): grep 正则模式在 POSIX locale 下无法匹配全角括号

**根因**: `grep "视觉需求（读取）"` 中的全角括号 `（）` 在 POSIX locale 下被正则引擎视为非法多字节序列。

**修复**: 使用 `grep -F` (固定字符串匹配) + 部分字符串 `"视觉需求"` (不包含括号):
```bash
# ❌ 错误
grep "视觉需求（读取）"   # POSIX locale 下正则匹配失败

# ✅ 正确
grep -F "视觉需求"        # -F 固定字符串, 不解析正则, 不依赖 locale
```

#### Bug 7 (CRITICAL): synoacltool -del 无法删除 deny ACE

**根因**: `synoacltool -del <path> <index>` 对 deny 类型的 ACE 返回 `(synoacltool.c, 672) Access deny`，即使 root 身份。

**影响**: 无法事后清理重复 deny。一旦产生重复，只能通过 DSM 网页端 File Station → 属性 → 权限 → 手动删除。

**策略**: 必须在事前 100% 阻止重复创建。

#### Bug 8: BTRFS 跨删除 ACL 缓存

**根因**: 群晖使用 BTRFS 文件系统。删除文件夹再重建同名文件夹时，BTRFS 扩展属性 (xattr) 会异步恢复旧文件夹的 ACL 条目。

**时间窗口**: 约 1-3 秒。在此窗口内读取 ACL 可能看到旧 deny 还未恢复的状态。

**修复**: `fix_one()` 在 `synoacltool -get` 前 `sleep 2`，等待 BTRFS ACL 完全沉降。

### 调试过程自身的问题

#### 问题 A: 测试脚本命名混乱导致进程残留

**现象**: 调试期间创建了多个临时测试脚本 (`/tmp/fix_debug.sh`, `/tmp/fix_test.sh`, `/tmp/fix_phase1.sh`)，用完后未清理。

**影响**: 使用 `ps aux | grep fix_design` 排查时搜不到这些名字。旧脚本进程 (root 身份，fzh.nas 用 sudo 也杀不掉) 运行 5+ 小时未被发现，每次新建文件夹时多个实例并发添加 deny 导致重复。

**ps 的陷阱**: 群晖 `ps aux` 输出中，中文路径被截断为 `?????????`，无法通过路径识别脚本身份:
```
root  2608  bash /volume1/?????????/fix_debug.sh   ← 中文路径被掩盖
```

**教训**:
1. 临时脚本**命名必须统一前缀** (如 `fix_tmp_xxx.sh`)
2. **用完立即删除**
3. 排查进程时**不能只搜脚本名**，还要搜 `inotifywait` 并检查父进程
4. 查看进程树: `ps -o pid,ppid,cmd` 比 `ps aux` 更清晰

#### 问题 B: ps 排查搜错关键字

**过程**:
1. 搜 `fix_design` → 返回 0 → 误判为"没有进程在跑"
2. 实际在跑的是 `fix_debug`、`fix_test` 等临时名
3. 搜 `inotifywait` → 找到 PID 2643 → 但 `ps` 中文路径显示为 `???` → 未能识别是哪个脚本的

**正确排查方法**:
```bash
# 1. 列出所有 inotifywait 进程
ps aux | grep inotifywait
# 2. 检查父进程
ps -o pid,ppid,cmd -p <inotifywait_pid>
# 3. 查看父进程的脚本内容
cat /proc/<ppid>/cmdline | tr '\0' ' '
# 4. 用多个关键字交叉搜索
ps aux | grep -E "fix_|design|inotify"
```

#### 问题 C: 锁机制选型反复失败

| 尝试 | 方案 | 失败原因 |
|------|------|---------|
| 1 | `/var/run/xxx.pid` | `/var/run` 目录不可写 |
| 2 | `/tmp/xxx.lock` + `mkdir` 原子锁 | 怀疑 DSM 进程隔离 (未证实，但不放心) |
| 3 | 嵌入式 `flock` + `exec {FD}<>` | sudo 进程树隔离导致无效 |
| 4 | **外挂式 `flock -xn`** ✅ | DSM 命令里直接写，不嵌入脚本 |

**最终方案**: 不在脚本内部做锁，在 DSM 计划任务命令中用 `flock` 包装:
```
flock -xn /volume1/技术部/.fix_design.lock -c '/bin/bash /volume1/技术部/fix_design_permissions.sh'
```

### 项目基础设施问题

#### 问题 D: NAS SSH 凭据查找困难

每次新对话 agent 尝试连接 NAS 时找不到密码，需要用户手动告知。

**根因**:
1. 项目没有 NAS SSH 凭据文件（.env 仅存 FileStation API 凭据）
2. `docs/superpowers/reference/2026-06-11-nas-synology-api-reference.md` 只记录了 `fzh.test` API 用户，未记录 SSH 用户 `fzh.nas`
3. `nas_product_visuals/AGENT_HANDOFF.md` 有 SSH 用户和地址，但密码不在任何文档中 (正确做法)

**解决**: 见本文档"连接信息"章节 (AGENT_HANDOFF 已更新)。

#### 问题 E: paramiko 重复安装

每次新对话 agent 尝试 `import paramiko` → 失败 → `uv add paramiko` → 修改 `pyproject.toml` 和 `uv.lock`。

**根因**:
1. `paramiko` **已在** `pyproject.toml` 第 18 行: `"paramiko>=5.0.0"`
2. 但新 worktree 或新 `uv sync` 后，`.venv` 不一定包含它
3. agent 没有先运行 `uv sync`，直接 `uv add paramiko`，导致重复添加

**正确做法**:
```bash
# ❌ 不要直接 uv add paramiko (它已经在 pyproject.toml 里)
uv add paramiko

# ✅ 先 sync 安装已有依赖
uv sync
python -c "import paramiko"  # 应该能导入
```

### NAS ACL 关键知识

#### synoacltool ACE 格式
```
[user|group]:name:[allow|deny]:permissions:inherit_mode
permissions: rwxpdDaARWcCo (13 位, 对应 DSM 界面的"完全控制")
inherit_mode: fd-- (文件+目录均传播), ---n (不传播)
```

#### ACL 优先级
显式 deny (level:0) > 显式 allow > 继承 deny > 继承 allow

#### Archive 标志
- `is_inherit` = 从父目录继承 ACL (非显式设置)
- `has_ACL` = 存在显式 ACE
- `is_support_ACL` = 文件系统支持 ACL

#### ACL 示例
```
/volume1/技术部/  Archive: has_ACL
  [2] group:视觉需求（读取）:allow:r-x---a-R-c--:fd-- (level:0)  ← 显式, 向下传播

子文件夹/设计稿/  Archive: is_inherit,has_ACL
  [0] group:视觉需求（读取）:deny:rwxpdDaARWcCo:fd-- (level:0)   ← 显式 DENY (优先)
  [4] group:视觉需求（读取）:allow:r-x---a-R-c--:fd-- (level:3)  ← 继承 (被 [0] 覆盖)
```

### 修复后脚本的关键设计决策

1. **`set -euo pipefail` 改为不加** — 管道无害错误也会杀脚本
2. **`fix_one` 直接管道** — `synoacltool | grep -F | grep -q deny`，绕过 echo
3. **`sleep 2`** — 等 BTRFS ACL 在删除重建后恢复完毕
4. **`while true` 外循环** — inotifywait 退出后自动重启
5. **补漏扫描** — 重启后快速 find 覆盖间隔期新建的文件夹
6. **`flock -xn` 外挂** — 不在脚本内部做锁
7. **`grep -F` 固定字符串** — 不依赖 locale

## 连接信息

NAS SSH (TODO: 新对话时需向用户询问密码):
- 域名: `fzh.myds.me:31022` (外网) / `192.168.1.5:31022` (局域网)
- 用户: `fzh.nas`
- DSM 网页: `fzh.myds.me:31022` (或 `192.168.1.5:31022`)

本地环境:
- Python 连接: `paramiko` (已包含在 `pyproject.toml`)
- 依赖安装: `uv sync`
- 编码处理: 所有 `print()` 必须加 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')`

## 脚本部署 (base64 传输)

禁止 SFTP。使用 base64 over SSH:
```python
import base64
with open('script.sh', 'rb') as f:
    content = f.read()
b64 = base64.b64encode(content).decode('ascii')
client.exec_command(f'echo "{b64}" | base64 -d > /volume1/技术部/script.sh')
```
注意: CRLF→LF 转换！部署前用 `content.replace(b'\r\n', b'\n')`。
