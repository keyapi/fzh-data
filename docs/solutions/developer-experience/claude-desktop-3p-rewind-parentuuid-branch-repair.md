---
okf: v0.1
type: Reference
title: "Claude Desktop 3P 会话 rewind 报 No message found：转录 parentUuid 分支接错与等长修复"
date: 2026-10-21
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "Claude Desktop（3P/本地 Agent 模式）会话在「发送 → 停止 → rewind → 重发」后反复报 No message found with message.uuid"
  - "日志出现 [Rewind] resumeSessionAt=<uuid> + forkSession 后紧跟同样的报错"
  - "消息在转录文件里明明存在，CLI 却坚持说找不到"
tags:
  - claude-desktop
  - claude-code
  - session-transcript
  - rewind
  - jsonl
  - parent-uuid
  - session-recovery
---

# Claude Desktop 3P 会话 rewind 报 No message found：转录 parentUuid 分支接错与等长修复

## Context

Claude Desktop 的 3P（本地 Agent）模式把每个聊天映射成一个 Claude Code CLI 会话。一次长会话里，用户「发送 → 立即停止 → rewind 到上一条用户消息 → 重发」后，桌面端开始反复报：

```
Claude couldn't process that message
Try sending it again
No message found with message.uuid of: <anchor-uuid>
```

报了以后无论重发多少次都一样。表面看像消息丢了，实际消息完整地躺在会话转录（`~/.claude/projects/<编码后的 cwd>/<cli-session-id>.jsonl`）里，JSON 也全部合法。

根因是**转录的分支接错**：桌面端 rewind 时把「目标用户消息之前的那条 assistant 消息」作为锚点传给 CLI（`resumeSessionAt`），但那条用户消息的 `parentUuid` 指向了一条并行的 `new_api_error` / `stop_hook_summary` 系统记录分支。CLI 从最后一条记录沿 `parentUuid` 回溯得到的**活跃分支**因此绕过了锚点，于是否认它的存在。

这个错误分支的产生时机很窄：模型请求经历了一轮 API 报错重试，成功回复与错误记账被写成两条并行分支；错误分支末端的 `stop_hook_summary` 时间戳恰好比成功回复晚约 1ms，下一条用户消息就以它为父，整条对话从此切到了错误分支上。

## Guidance

### 1. 先确认三件事实，别急着改文件

- **会话映射**：`%APPDATA%\Claude-3p\claude-code-sessions\<plugin-id>\<collection>\local_<uuid>.json` → 字段 `cliSessionId` 就是 CLI 会话 id（auto memory [claude]：Desktop 会话清单与日志就在 `Claude-3p` 下）。
- **锚点**：在 `%APPDATA%\Claude-3p\logs\main.log` 搜 `No message found` 与 `[Rewind] resumeSessionAt=`，得到 Desktop 每次重放的锚点 uuid。
- **转录**：`~/.claude/projects/<编码后的 cwd>/<cliSessionId>.jsonl`。先确认每行 JSON 可解析。

### 2. 判断是「消息丢了」还是「分支断了」

不要全文 grep 后看到 uuid 就认为没问题。正确做法是从**最后一条带 uuid 的记录**开始沿 `parentUuid` 向上回溯，得到活跃分支：

```python
rows = [json.loads(line) for line in open(path, encoding="utf-8")]
by_uuid = {o["uuid"]: o for o in rows if o.get("uuid")}
chain, cur = [], [o for o in rows if o.get("uuid")][-1]
while cur:
    chain.append(cur["uuid"])
    parent = cur.get("parentUuid")
    if not parent:
        break
    cur = by_uuid.get(parent)          # None 表示父节点缺失
```

锚点 uuid 在文件里、但不在 `chain` 里 → 分支接错。顺带检查 `missing parent` 是否为空。

### 3. 定位断点

- 锚点通常是成功回合的 assistant 消息，后面紧跟一条 Stop hook 的 `hook_success` 附件。
- 看紧随其后的那条**用户消息**：它的 `parentUuid` 如果指向 `stop_hook_summary` / `new_api_error` 这类系统记录，而不是成功回合的附件，断点就在这里。
- 那些系统记录的链头往往挂在更早的一条记录上，与正常分支形成分叉（同一父节点两个子节点）。

### 4. 等长修正 parentUuid

- 先确保**该会话没有活跃的 CLI 写入进程**（`Get-CimInstance Win32_Process` 过滤 command line 里的 session id）。修完重启桌面端最稳。
- 备份 jsonl，核对字节数。
- 只替换那条用户消息的 `parentUuid`，指回成功回合的最后一条记录（assistant 后面的 Stop hook 附件；附件在转录里是合法父节点）。
- **必须等长**：`parentUuid` 前后的键名不变，旧值和新值都是 36 字符 uuid，替换后文件大小与字节偏移完全不变。2.1.x 的增量扫描依赖偏移，等长替换是安全前提。
- 写临时文件 → 全量 `json.loads` 校验 → `os.replace` 原子替换。

```python
old = b'"parentUuid":"<error-branch-tail-uuid>"'
new = b'"parentUuid":"<success-turn-tail-uuid>"'
assert len(old) == len(new)
# 定位到含目标用户消息 uuid 的那一行后，只替换行首这一处
patched = raw.replace(old, new, 1)
assert len(patched) == len(raw)
```

### 5. 静态校验后再回到 UI

重新回溯活跃分支，确认：无缺失父节点、锚点 uuid 在链上、目标用户消息在链上。修复前的案例是 2357 个节点不含锚点；修复后 2365 个节点包含锚点。然后回桌面端重试 rewind / 重发，日志里 `[Rewind] resumeSessionAt=...` 之后不应再出现 `No message found`，项目目录下会出现一个新的 fork 会话文件。

### 6. 回滚

修复前必须留有备份。校验不过或重试仍失败时，关掉桌面端、用备份覆盖，再退回「用 CLI `--resume <session-id> --fork-session` 另开会话继续」这条不依赖 rewind 的路。

## Why This Matters

- **不修也能继续**：普通发消息不经过 `resumeSessionAt`，所以「继续对话」往往没问题；但 rewind 会一直卡死，长会话想回退重做就只能放弃整段上下文。
- **误判代价高**：如果把它当成消息丢失去重开会话或删除转录，会丢掉 90 分钟以上的上下文和未提交的工作线索；实际只需要改一个 51 字节的指针。
- **同一个坑会复发**：API 重试风暴 + 紧接着发消息是真实会发生的操作序列。知道「先回溯活跃链」这个判据，下次几分钟就能定位。

## When to Apply

- Claude Desktop 3P / 本地 Agent 模式出现 `No message found with message.uuid`，且只发生在 rewind 后。
- 日志显示 Desktop 每次重发都带同一个 `resumeSessionAt` 和 `forkSession`。
- 任何「uuid 在转录文件里存在，但 CLI 说找不到」的恢复场景——先查活跃分支，再查消息内容。

## Examples

修复前后的分支形状（uuid 用占位符）：

```
修复前：… → A(成功 assistant) → B(Stop hook 附件)        ← 被绕过的正常分支
              └→ E1 → E2 → E3 → E4(错误分支末端)
                                      └→ U(用户消息) ← 活跃分支从这里开始
修复后：… → A → B → U → …
              └→ E1 → E2 → E3 → E4   ← 4 条记录成为不可达的兄弟分支，无害
```

判断依据只看两个数：从最后一条记录回溯的节点数，以及锚点是否在链上。修复前 `2357 / False`，修复后 `2365 / True`；文件大小保持 `22,977,577` 字节不变。

## Related

- [Codex (ChatGPT Desktop) 更新后 Windows 安装失败与对话历史恢复](codex-chatgpt-windows-setup-config-recovery.md) —— 同类桌面端会话/历史恢复问题
- [Windows worktree 下 CLAUDE.md 的 symlink 与 stub](windows-worktree-claude-md-symlink.md) —— 本机 Agent 环境另一类「看起来像丢了」的问题
- [windows-agent-shell](../../../.agents/skills/windows-agent-shell/SKILL.md) —— Windows Agent 环境与本地工具排障入口
