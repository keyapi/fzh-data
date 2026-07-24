# NAS-ERPNext 文件夹对账

比对 ERPNext 产品物料组与 Synology NAS `/产品信息/` 文件夹，自动创建/重命名/移动空文件夹，有内容时阻塞报告。

## 快速启动

```bash
cd nas_itemgroup_folders
uv run python build_nas_folders.py              # 测试模式 (KS0001, KS0002)
uv run python build_nas_folders.py --full       # 全量 404 个
uv run python build_nas_folders.py --dry-run    # 仅对比，不操作
```

## 布局切换

```bash
uv run python build_nas_folders.py --layout=tree   # 按 ERPNext 树结构
uv run python build_nas_folders.py --layout=flat   # 扁平结构（默认）
```

## 对账逻辑

每次运行从头对比 ERPNext ↔ NAS：

| 状态 | 说明 | 策略 |
|------|------|------|
| MATCH | 一致 | 无事 |
| MISSING | ERPNext 有，NAS 无 | 自动创建 + 子文件夹 |
| NAME_MISMATCH | 同 KS 码，名称不同 | 空→自动重命名；有内容→阻塞 |
| STRUC_MISMATCH | 同 KS 码，路径不同 | 空→自动移动；有内容→需确认 |
| EXTRA | NAS 有 (KS格式)，ERPNext 无 | 空→建议删除；有内容→阻塞 |
| IGNORE | NAS 有 (非 KS 格式) | 不碰 |

## 配置

编辑 `.env`：
- `NAS_TARGET_FOLDER` — 目标路径（默认 `/产品信息`）
- `ITEM_GROUP_ROOT` — ERPNext 根节点（默认 `产品`）
- `SUB_FOLDERS` — 标准子文件夹，逗号分隔（默认 `调研报告,设计稿,图片,视频`）

NAS 凭证在 `../NAS_API/.env`。
