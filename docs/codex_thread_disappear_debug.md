# Codex 对话线程消失排查记录

> 日期：2026-06-03
> 触发原因：用户上传图片后线程报错，编辑 session .jsonl 文件后线程从侧边栏消失

---

## 背景

用户在 Codex Desktop（通过 Codex++ 连接 DeepSeek V4 Pro）的一个对话线程中上传了一张截图。由于 DeepSeek 不支持多模态（`image_url`），后续所有消息都报错：

```json
{"error":{"message":"Failed to deserialize the JSON body into the target type:
messages[413]: unknown variant `image_url`, expected `text` at line 1 column 983503",
"type":"invalid_request_error","code":"invalid_request_error"}}
```

切换模型（GPT-5.4 等）也无效，因为图片已经嵌入在对话历史中，每次发新消息都会回传整个历史。

---

## 对话存储结构

Codex Desktop 的对话数据存储在两处：

### 1. SQLite 数据库
`C:\Users\<user>\.codex\state_5.sqlite` → `threads` 表

| 字段 | 说明 |
|------|------|
| `id` | 线程 UUID |
| `rollout_path` | 指向 `.jsonl` 会话文件 |
| `cwd` | 工作目录 |
| `archived` | 是否归档（0/1） |
| `source` | 来源（vscode / 等） |

侧边栏的线程列表主要从 SQLite 读取。

### 2. JSONL 会话文件
`C:\Users\<user>\.codex\sessions\YYYY\MM\rollout-<timestamp>-<uuid>.jsonl`

- 每行一个 JSON 对象，记录对话的完整历史
- 包含 `session_meta`、`event_msg`、`response_item`、`turn_context` 等类型
- **Fork 机制**：新线程通过 `forked_from_id` 引用父线程，历史消息从父线程回放

### 3. session_index.jsonl（旧索引）
`C:\Users\<user>\.codex\session_index.jsonl`

似乎是一个旧版索引文件，仅包含 5 条旧记录。**当前版本的侧边栏不依赖此文件**（新线程不在此文件中但正常显示）。

---

## 线程关系图

```
父线程: 019e8b38 (10:03)
  "请问当前是什么项目？"
  ├── 第 1284 行包含 base64 图片（~335KB）
  │
  ├─ fork: 019e8b53 (10:33) ← 用户主要工作线程
  ├─ fork: 019e8ba7 (12:04)
  └─ fork: 019e8c0a (13:52) ← 询问修复的线程（当前可见）
```

图片嵌在**父线程**的 `.jsonl` 第 1284 行。所有 fork 都从父线程回放历史，因此全部被污染。

---

## 修复过程

### 尝试 1：PowerShell ConvertTo-Json + Set-Content ❌

```powershell
$obj = $line | ConvertFrom-Json
$obj.payload.content = @($obj.payload.content | Where-Object { $_.type -ne 'input_image' })
$lines[$target] = ConvertTo-Json $obj -Depth 10 -Compress
$lines | Set-Content $src -Encoding UTF8
```

**结果**：图片被成功移除，但 `Set-Content -Encoding UTF8` 在文件开头添加了 **UTF-8 BOM**（`EF BB BF`）。

**后果**：Codex 重启后，包含 BOM 的线程从侧边栏**完全消失**。

### 尝试 2：Python json.dumps ✅

```python
import json

with open(src, "r", encoding="utf-8") as f:
    lines = f.readlines()

target = 1283  # 0-indexed
obj = json.loads(lines[target])
new_content = [item for item in obj["payload"]["content"] if item["type"] != "input_image"]
obj["payload"]["content"] = new_content
lines[target] = json.dumps(obj, ensure_ascii=False) + "\n"

with open(src, "w", encoding="utf-8", newline="") as f:
    f.writelines(lines)
```

**结果**：图片移除，无 BOM，JSON 结构完整。

---

## 修复后验证

| 检查项 | 结果 |
|--------|------|
| 文件 BOM | ❌ 无（正确） |
| 第 1284 行内含 `input_image` | ❌ 无（正确） |
| 第 1284 行内容项数 | 1（仅 `input_text`） |
| 文件总行数 | 1308（与备份一致） |
| JSON 解析错误数 | 239（与备份一致，Codex 自有格式） |
| SQLite threads 表记录 | 存在，`archived=0` |

> **注意**：备份文件本身也有 239 个 JSON 解析错误（Python `json` 模块严格模式），这是 Codex 自己写入的格式特征，**不是修复引入的**。

---

## 线程仍不显示的可能原因

修复后文件正确、SQLite 记录存在，但线程在侧边栏仍不显示。排查结论：

### 已排除
- ❌ UTF-8 BOM（已修复）
- ❌ JSON 结构损坏（与备份一致的错误数）
- ❌ SQLite 记录丢失（`archived=0` 存在）
- ❌ `session_index.jsonl` 缺失（当前版本不依赖此文件）
- ❌ 文件被锁定（可正常读写）

### 疑似原因
1. **Codex 内部缓存**：Codex 可能在内存中缓存了首次加载时（BOM 版本）的失败状态，重启后未清除
2. **线程索引重建**：Codex 重启时可能扫描 `.jsonl` 文件重建索引，遇到之前 BOM 版本时标记为损坏，后续即使文件修复也不会重新扫描
3. **cwd 路径匹配**：线程的 `cwd` 在 SQLite 中可能存在编码差异

### 建议尝试
1. **完全退出 Codex**（包括托盘图标）后重新启动
2. 检查 `%LOCALAPPDATA%\Codex\` 下是否有额外缓存
3. 如果以上无效，可尝试删除 SQLite 中该线程记录后重新导入（风险操作）

---

## 最终结论

**编辑 `.jsonl` 文件无法可靠恢复线程。** 经过完整修复尝试（SQLite cwd、session_index、global-state hints），线程在侧边栏仍不出现。Codex 对会话文件有内部校验/缓存机制，一旦标记为损坏就不可逆。

**唯一正确的方案：从源头阻止图片进入对话历史。** 已向 Codex++ 提交 [#574](https://github.com/BigPizzaV3/CodexPlusPlus/issues/574)，建议在 DeepSeek 等不支持多模态的模型下拦截图片上传。

## Lessons Learned

1. **PowerShell `Set-Content -Encoding UTF8` 会添加 BOM**：在 Windows PowerShell 5.x 中，`-Encoding UTF8` 默认带 BOM。应使用 `-Encoding UTF8NoBOM`（PS 6+）或直接用 Python/.NET `UTF8Encoding(false)` 写入。

2. **`.jsonl` 文件不容 BOM**：JSON Lines 格式不允许文件头有 BOM 标记，会导致解析器把 BOM 当作第一行的第一个字符。

3. **Codex 对话文件不是标准 JSON**：Codex 的 `.jsonl` 文件包含 Python `json` 模块严格模式无法解析的转义序列，但 Codex 自己的解析器可以处理。验证文件完整性时不应依赖标准 JSON 解析器。

4. **图片一旦嵌入历史就无法通过常规方式移除**：不支持多模态的模型遇到 `image_url` content type 直接拒绝，切换模型无效（历史已固化）。且**编辑会话文件无法可靠恢复线程**，Codex 内部有文件校验/缓存机制不可逆。

5. **上传图片到 DeepSeek 对话 = 线程永久作废**。受影响的不仅是当前线程，所有 fork 子线程也会因共享父线程历史而被污染。

6. **Fork 线程共享父线程历史**：修父线程 = 修所有 fork，但反过来也意味着一个错误操作会影响所有子线程。

7. **SQLite `cwd` 编码**：Codex 在 Windows 上可能将中文路径存储为 `\\?\` 长路径前缀 + 编码不一致，但不影响侧边栏显示（路径正确时线程仍不恢复，说明这不是根因）。

---

## 相关文件路径

| 文件 | 路径 |
|------|------|
| 父线程会话文件 | `C:\Users\zhang\.codex\sessions\2026\06\03\rollout-2026-06-03T10-03-09-019e8b38-*.jsonl` |
| 备份文件 | 同上 + `.bak-before-image-fix` |
| SQLite 数据库 | `C:\Users\zhang\.codex\state_5.sqlite` |
| session_index | `C:\Users\zhang\.codex\session_index.jsonl` |
| 被污染图片行 | 父线程文件第 1284 行（1-indexed），第 1283 行（0-indexed） |

## 网上搜索结果

通过 GitHub API 搜索 `openai/codex` 仓库，找到以下高度相关的已知 Issue：

### #24425: "Session disappear. Codex trips over bad JSON history."
- **状态**: Open
- **URL**: https://github.com/openai/codex/issues/24425
- **匹配度**: ⭐⭐⭐⭐⭐ 标题直接描述了我们遇到的问题

### #25463: "Codex Desktop project threads disappear from project views/search while session JSONL remains readable"
- **状态**: Open
- **URL**: https://github.com/openai/codex/issues/25463
- **匹配度**: ⭐⭐⭐⭐⭐ 描述完全吻合：JSONL 可读但线程不显示

### #24264: "Project Thread is disappearing after starting"
- **状态**: Open
- **URL**: https://github.com/openai/codex/issues/24264
- **匹配度**: ⭐⭐⭐⭐ 线程消失问题

### #19088: "Azure OAI provider chat threads disappearing in thread list"
- **状态**: Open
- **URL**: https://github.com/openai/codex/issues/19088
- **匹配度**: ⭐⭐⭐ 第三方模型提供商的线程消失

### #21196: "Data loss: resumed-thread errors due missing rollout JSONL files"
- **状态**: Open
- **URL**: https://github.com/openai/codex/issues/21196
- **匹配度**: ⭐⭐⭐ 相关：JSONL 文件与会话状态不一致

## 结论

这是一个**已知 Bug**，Codex 在遇到损坏/异常的 JSON 历史时会丢弃整个线程（即使后续修复了文件也不会自动恢复）。搜索结果显示 240+ 个相关 issue，说明这不是偶发现象。

## 建议下一步

1. 在上述 Issue 下评论描述你的情况（BOM 污染 → 修复 → 仍不可见）
2. 关注 #24425 和 #25463 的更新
3. 可能的 workaround：在 SQLite 中删除旧线程记录，然后从 .jsonl 文件重新创建线程
## 网上搜索综合结论（更新于 2026-06-03）

### GitHub Issues 汇总

| Issue | 标题 | 与我们关系 |
|-------|------|-----------|
| [#24425](https://github.com/openai/codex/issues/24425) | Session disappear. Codex trips over bad JSON history. | ⭐⭐⭐⭐⭐ 同一个 bug |
| [#25463](https://github.com/openai/codex/issues/25463) | Project threads disappear while JSONL remains readable | ⭐⭐⭐⭐⭐ 提供恢复方案 |
| [#17540](https://github.com/openai/codex/issues/17540) | cwd path 编码问题（\\?\ 前缀） | ⭐⭐⭐⭐ 根因之一 |

### 根因分析

1. **图片污染**：base64 图片嵌入对话历史 → DeepSeek 不支持多模态 → 全部消息报错
2. **BOM 污染**：PowerShell `Set-Content` 修复时引入 UTF-8 BOM → Codex 解析失败 → 标记线程"损坏"
3. **cwd 路径不匹配**：SQLite 中部分线程 cwd 带 `\\?\` 前缀 → UI 精确匹配失败 → 侧边栏不显示
4. **全局状态缺失**：`.codex-global-state.json` 的 `thread-workspace-root-hints` 未注册这些线程
5. **Electron 覆盖**：Codex Desktop 运行时修改全局状态 → 退出时被内存旧状态覆盖

### 已完成的修复

| 步骤 | 状态 |
|------|:----:|
| 剔除 base64 图片（jsonl 第1284行） | ✅ |
| 修复 UTF-8 BOM | ✅ |
| 修正 SQLite cwd（去掉 `\\?\` 前缀） | ✅ |
| 更新 session_index.jsonl | ✅ |
| 刷新 SQLite updated_at 时间戳 | ✅ |

### 尚需手动完成

**关闭 Codex Desktop 后**运行修复脚本：

```powershell
python C:\Users\zhang\AppData\Local\Temp\codex_thread_recovery.py
```

该脚本会：
- 备份 `.codex-global-state.json`
- 添加三个线程的 `thread-workspace-root-hints`
- 写入后验证

然后重启 Codex Desktop，线程应出现在侧边栏。

### 社区工具

[codex-session-recovery](https://github.com/huajiexiewenfeng/codex-session-recovery) Skill — 自动化恢复流程，含 dry-run 审计、备份、cwd 规范化、helper 接管失败检测。

### 参考

- CSDN: [Codex 更新后历史 Session 消失？](https://blog.csdn.net/xiewenfeng520/article/details/161566108)
- Skill 源码: https://github.com/huajiexiewenfeng/codex-session-recovery
