# NAS-ERPNext 对账引擎设计

> 状态: 设计完成 | 日期: 2026-06-12

## 背景

视觉部负责人 LM 需要在 Synology NAS `/产品信息/` 下，按 ERPNext 物料组（Item Group）创建文件夹结构，存放调研报告、设计稿、图片、视频。初期先扁平放置叶子节点，后续可能按 ERPNext 树结构在 NAS 上复刻层级。

核心挑战：ERPNext 和 NAS 是两个独立系统，物料组会新增/改名/删除/移动，NAS 文件夹会被 LM 手动放入内容。需要一套对账机制确保两边一致，且绝不破坏已有人工内容。

## 架构：快照对比型

每次运行从头对账 ERPNext 当前数据 vs NAS 当前文件系统，无状态依赖，快照只存一份供人回溯。

```
┌─────────────────┐     ┌─────────────────┐
│ ERPNext API      │     │ NAS FileStation │
│ Item Group 树    │     │ /产品信息/       │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
    erpnext snapshot      nas snapshot
         │                       │
         └───────────┬───────────┘
                     ▼
              对账比较引擎
                     │
                     ▼
         ┌─────────────────────┐
         │      差异报告        │
         │  ✅ 自动操作 (安全)   │
         │  ⚠️ 需确认 (阻塞)    │
         │  📋 信息项 (不操作)  │
         └─────────────────────┘
```

## 对账矩阵

每个 ERPNext 叶子节点（产品 > ... > 叶子）与 NAS 文件夹逐一比对，归入以下状态：

| 状态 | ERPNext | NAS | 说明 |
|------|---------|-----|------|
| `MATCH` | 有 | 有，名称匹配 | 一致 |
| `MISSING` | 有 | 无 | 新物料组，需创建 |
| `NAME_MISMATCH` | 有 | 有同 KS 码但不同名 | 物料组改名 |
| `STRUC_MISMATCH` | 有 | 有但路径不对 | 物料组父节点变更 |
| `EXTRA` | 无 | 有（KS 码格式） | 物料组可能已删除 |
| `IGNORE` | — | 有（非 KS 格式） | 非脚本创建，不碰 |

## 操作决策树

```
对每个叶子物料组:
  │
  ├─ MISSING
  │   └─ → [CREATE] 自动创建文件夹 + 标准子文件夹  ✅ 安全
  │
  ├─ MATCH → 无事
  │
  ├─ NAME_MISMATCH (同 KS 码、不同名)
  │   ├─ 旧文件夹为空 → [RENAME] 自动重命名  ✅ 安全
  │   └─ 旧文件夹有内容 → [BLOCKED]
  │       报告建议: 新建正确名称文件夹，提示需手动迁移内容
  │
  ├─ STRUC_MISMATCH (同 KS 码、路径不符)
  │   ├─ 旧路径为空 → [MOVE] 自动 CopyMove 到新路径  ✅ 安全
  │   └─ 旧路径有内容 → [MOVE_APPROVAL]
  │       报告详情: 旧路径 / 新路径 / 文件数 / 大小
  │       用户确认后 FileStation CopyMove 整体搬迁
  │       搬迁失败 → 保留原状，输出失败原因
  │
  ├─ EXTRA (NAS 有 KS 格式、ERPNext 无)
  │   ├─ 文件夹为空 → 报告建议可安全删除
  │   └─ 文件夹有内容 → [BLOCKED]
  │       报告建议: ①确认 ERPNext 是否误删 ②手动归档
  │
  └─ IGNORE (NAS 有、不匹配 KS 格式)
      └─ → 列出在报告中，不操作
```

**有内容的判定**: NAS `get_file_list` 递归统计文件夹内非目录文件数量 > 0。

## 扁平 ↔ 树状切换

```
flat → tree:
  1. 拍当前 NAS 快照（保底）
  2. 计算每个叶子新旧路径差异
  3. 空文件夹 → 自动 CopyMove
  4. 有内容 → 报告详情，用户确认后 CopyMove
  5. 搬迁完成验证: 新路径存在 + 旧路径已空
  6. 中间空父节点清理（可选）

tree → flat: 同理反向
```

## 子文件夹管理

每个物料组文件夹下的标准子文件夹列表（可配置）：
`["调研报告", "设计稿", "图片", "视频"]`

- 缺失 → 自动补建
- 存在 → 不管
- 多余（LM 手动加的，如"发货"）→ 记录到快照，不删不碰
- 搬迁时整个父文件夹带走（含所有子文件夹）

## 快照格式

`nas_itemgroup_folders/out/last_snapshot.json`（每次覆盖）

```json
{
  "run_at": "2026-06-12T10:30:00",
  "layout": "flat",
  "erpnext": {
    "root": "产品",
    "total_leaves": 404,
    "items": [{
      "name": "三角靠枕",
      "model_id": "KS0001",
      "parent": "三角靠枕类",
      "ancestors": ["产品", "床品类", "床头靠枕", "三角靠枕类"],
      "expected_path": "/产品信息/KS0001_三角靠枕"
    }]
  },
  "nas": {
    "target": "/产品信息",
    "script_created": [{
      "name": "KS0001_三角靠枕",
      "path": "/产品信息/KS0001_三角靠枕",
      "content_count": 15,
      "content_bytes": 2048000,
      "sub_folders": ["调研报告", "设计稿", "图片", "视频"],
      "extra_folders": ["发货"]
    }],
    "manual_or_unknown": [{
      "name": "旧的设计文件1",
      "path": "/产品信息/旧的设计文件1",
      "content_count": 30,
      "content_bytes": 2147483648
    }]
  }
}
```

## 报告格式

```
=== NAS-ERPNext 对账报告 ===  2026-06-12 10:30
模式: TEST (KS0001, KS0002)  布局: flat

ERPNext: 404 叶子 | NAS: 3 文件夹

差异:
  MATCH            0
  MISSING         402  (自动创建)
  NAME_MISMATCH     0
  STRUC_MISMATCH    0
  BLOCKED           0
  EXTRA             1  (非 KS 格式)

自动操作（已执行）:
  [CREATE] KS0003_xxx → /产品信息/KS0003_xxx/  (+4 子文件夹)
  ...共 402 项

阻塞项（需手动确认，未执行）:
  [MOVE_APPROVAL] KS0001: /产品信息/ → /产品信息/床品类/.../  (15 文件, 2.0 MB)

NAS 额外项目（非脚本创建）:
  [DIR] 旧的设计文件1/  (30 文件, 2.0 GB)

子文件夹补齐: 已补建 8 | 已存在 0
总计: 创建 0 | 跳过 0 | 失败 0 | 阻塞 0
```

## 文件结构

```
nas_itemgroup_folders/
  build_nas_folders.py       # 主脚本（对账 + 创建 + 报告）
  reconcile.py               # 对账引擎（核心逻辑，可独立导入）
  verify_tree_structure.py   # 树结构预览（已存在）
  .env
  out/
    last_snapshot.json       # 最新快照
    report_YYYYMMDD_HHMMSS.json  # 逐次报告
```

## CLI

```bash
uv run python build_nas_folders.py              # 测试模式 (KS0001, KS0002)
uv run python build_nas_folders.py --full       # 全量
uv run python build_nas_folders.py --dry-run    # 仅对比，不操作
uv run python build_nas_folders.py --layout tree  # 切换到树状
uv run python build_nas_folders.py --layout flat  # 切换到扁平
uv run python build_nas_folders.py --auto         # 自动执行安全操作 + 有内容MOVE也自动
```

## 边界条件 & 异常处理

| 场景 | 处理 |
|------|------|
| ERPNext API 不可达 | 终止，提示检查网络/VPN |
| NAS 不可达 | 终止，提示检查 NAS URL/凭证 |
| NAS 磁盘满 | 创建失败计入报告，不中断后续操作 |
| 文件夹名含非法字符 | `safe_name()` 转义，记录原始名→转义后名映射 |
| 两个物料组共享同一 KS 码 | 报告中标记冲突，取第一个，跳过后续 |
| 物料组无 custom_model_id | 跳过，不计入差异，报告中单独列出 |
| NAS 文件夹被外部删除（运行间隙） | 下次对账自动发现 MISSING，重建 |
| 网络超时中途失败 | 单条失败计入报告，不中断，最后汇总 |
| CopyMove 中途失败 | 回滚报告（验证新旧状态），不丢数据 |
| 快照文件损坏 | 不影响（无状态设计），覆盖写新快照 |
| 权限不足（NAS 403） | 终止，提示检查共享文件夹权限 |

## 非目标

- 不做 Web UI（CLI + JSON 报告足够）
- 不做增量同步（每次全量对比）
- 不做定时自动运行（`--auto` 标志预留但手动触发）
- 不碰非 `/产品信息/` 以外的 NAS 路径
