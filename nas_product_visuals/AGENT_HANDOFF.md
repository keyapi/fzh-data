# NAS 运维脚本集

## 概述

部署在群晖 NAS `/volume1/技术部/` 上的 Bash 脚本集合 — 产品目录扫描 + ACL 权限实时修复。

## 核心文件

| 文件 | 说明 |
|------|------|
| `generate_products_visuals.sh` | 扫描 `/volume1/产品信息/` 下所有产品文件夹路径 |
| `fix_design_permissions.sh` | inotify 实时监控"设计稿"文件夹，自动移除"视觉需求（读取）"角色权限 |
| `folder_paths_simple.txt` | 输出的路径清单报告，位于 `/volume1/FZH共享文件夹/` |
| `docs/` | OKF 文档（[index.md](docs/index.md) / [log.md](docs/log.md)） |

## 部署环境

| 项目 | 值 |
|------|-----|
| NAS 地址 | `fzh.myds.me:31022` |
| 用户 | `fzh.nas` |
| 脚本路径 | `/volume1/技术部/generate_products_visuals.sh` |
| 输出路径 | `/volume1/FZH共享文件夹/folder_paths_simple.txt` |
| 定时任务 | 群晖 DSM 任务计划程序（建议每天凌晨） |

## 目录结构

### 普通产品 (depth 2)

```
/volume1/产品信息/
├── KS0001_三角靠枕/
│   ├── 图片/
│   │   ├── 2026新图/
│   │   │   └── photo.jpg
│   ├── 视频/
│   ├── 设计稿/
│   └── 调研报告/
```

### LGKS 叶子组 (depth 3 — v1.1 新增支持)

根据项目 `docs/company-context.md` 和 `nas_itemgroup_folders/` 模块定义的叶子组规范，LGKS 系列产品在叶子组目录下嵌套了多个 KS 子款式：

```
/volume1/产品信息/
├── LGKS0220_可组合扶手沙发/         ← 叶子组 (depth 1)
│   ├── 图片/                         ← LG 自身分类 (depth 2)
│   ├── 视频/
│   ├── 设计稿/
│   ├── 调研报告/
│   ├── KS0220_可组合扶手沙发套件/    ← KS 子款式 (depth 2)
│   │   ├── 图片/                     ← 子款式分类 (depth 3)
│   │   ├── 视频/
│   │   └── ...
│   ├── KS0245_扶手模块/
│   └── KS0246_靠背模块/
```

NAS 上目前有 **13 个 LGKS 叶子组**，每个包含 2-5 个 KS 子款式。

## 扫描逻辑

1. 从 `BASE_PATH` 出发，最多扫描 **3 层**（覆盖普通产品 depth 2 + LGKS 嵌套 depth 3）
2. 找到所有名为 `图片`/`视频`/`设计稿`/`调研报告` 的目录
3. 在每个分类目录下**递归查找所有文件**（无深度限制）
4. 从文件位置向上回溯，提取所有祖先目录路径
5. **去重**后输出 — 只有子树中存在实际文件的目录才会被记录
6. 自动排除：
   - `@eaDir`：群晖系统缩略图缓存，`find -prune` 跳过
   - `#recycle`：群晖回收站中已删除的产品

## 配置项

脚本顶部可修改变量：

```bash
OUTPUT_FILE="/volume1/FZH共享文件夹/folder_paths_simple.txt"
BASE_PATH="/volume1/产品信息"
```

如需增减分类，修改 for 循环：
```bash
for cat in "图片" "视频" "设计稿" "调研报告"; do
```

如需调整扫描深度，修改 `-maxdepth` 参数（当前为 3）。

## 输出报告结构

```
📁 产品信息目录分类文件夹路径列表
================================
生成时间: Tue Jun 23 ...
基础路径: /volume1/产品信息

图片目录路径:
----------------
/volume1/产品信息/KS0001_三角靠枕/图片
/volume1/产品信息/KS0001_三角靠枕/图片/2026新图
...
/volume1/产品信息/LGKS0220_组合沙发/KS0220_套件/图片
...

图片文件夹数量: 5717

视频目录路径:
...
设计稿目录路径:
...
调研报告目录路径:
...

扫描完成: ...
各分类文件夹总数: 6295
总计生成路径行数: 6323
```

## ERPNext 集成

测试环境的 ERPNext 系统有脚本读取 `/volume1/FZH共享文件夹/folder_paths_simple.txt`。路径格式遵循 `编号_名称/分类/子目录...` 的层级结构，ERPNext 脚本可以按产品编号（KSxxxx/LGKSxxxx）和分类维度解析。

---

## 部署经验教训 (Lessons Learned)

### Lesson 1: CRLF 换行符污染

**问题：** 从 Windows (Git) 直接上传 `.sh` 文件到 Linux NAS，脚本中的 `\r\n` 导致：
- 每行末尾 `\r` 被 bash 解释为命令名的一部分（`$'\r': command not found`）
- 变量赋值末尾带 `\r`，如 `OUTPUT_FILE="/volume1/.../folder_paths_simple.txt\r"`
- `> "$OUTPUT_FILE"` 创建了带 `\r` 字符的文件名，产生幽灵空文件

**解决：**
```bash
# 上传后必须转换
sed -i 's/\r//g' "/volume1/技术部/generate_products_visuals.sh"
# 或在本地转换后再上传
content = content.replace(b'\r\n', b'\n')
```

**预防：** 项目应在 `.gitattributes` 中声明 `*.sh text eol=lf`。

### Lesson 2: Synology ACL 锁定特殊文件名

**问题：** 含控制字符（`\r`）的文件名被 Synology ACL 保护，SSH 下 `rm`、`mv`、`chmod` 均返回 `Permission denied`，即使文件 owner 匹配。

**现象：**
```
-rwxrwxrwx+ 1 fzh.nas users 0 Jun 23 15:06 folder_paths_simple.txt\r\r
PermissionError: [Errno 13] Permission denied
```

**解决：** 通过 DSM 网页端 File Station 手动删除，或从 Windows SMB 映射驱动器删除。

### Lesson 3: Windows GBK 控制台编码

**问题：** 脚本输出和文件内容含 emoji / 中文，Python `print()` 在 Windows GBK 控制台报错：
```
UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f4c1'
```

**解决：**
```python
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```
或者将输出写入文件后通过 `Read` 工具查看，避免控制台编码问题。

### Lesson 4: 不要用 SFTP 上传文件到群晖

**问题：** 群晖默认关闭 SFTP 子系统，paramiko `SFTPClient.from_transport()` 报 `Channel closed`。

**解决：** 使用 base64 编码通过 SSH exec 传输：
```python
b64 = base64.b64encode(content).decode('ascii')
client.exec_command(f'echo "{b64}" | base64 -d > /path/to/file')
```
**注意：** 确保内容已先做 CRLF→LF 转换，否则上传后立即产生问题。

### Lesson 5: 群晖 find 对 @eaDir 的 Permission Denied 是正常的

群晖 `@eaDir/SYNO@.fileindexdb` 目录受系统保护，`find` 会报 `Permission denied`。这些消息输出到 stderr，不影响脚本功能。已在脚本中用 `-prune` 跳过 `@eaDir`，但根级 `@eaDir` 仍会触发一次警告。

### Lesson 6: LGKS 叶子组需要 3 层深度扫描

详见 Fix 2。最初 PR #34 只设了 `-maxdepth 2`，遗漏了 LGKS 下 KS 子款式的分类目录。
修改为 `-maxdepth 3` 并加 `! -path "*/#recycle/*"` 排除回收站可解决。

---

## 修改记录

### v1.1 (2026-06-23)

- **Fix:** `maxdepth 2 → 3` 支持 LGKS 叶子组内 KS 子款式扫描
- **Fix:** 添加 `! -path "*/#recycle/*"` 排除回收站
- **Doc:** 记录完整部署经验教训（Lesson 1-6）
- **已验证:** 输出从 6222 → 6295 文件夹，新增 73 个 KS 子款式路径，LGKS mentions 从 63 → 136
