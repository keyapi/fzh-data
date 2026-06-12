# DAM Phase 7: 多来源 Assets + Collection 架构规划

> 日期: 2026-06-11 | 状态: 调研完成，等待讨论确认后实施
> 关联文档: `docs/superpowers/research/2026-06-11-dam-multi-source-architecture.md`

## 架构决策

### NAS 定位: Assets 的前置来源（pre-source）

```
┌─────────┐    Browse & Import     ┌──────────┐    Reference    ┌────────────┐
│   NAS   │ ─────────────────────> │  Assets  │ ─────────────> │ Collection │
│ (来源)   │   (必须导入才能使用)    │ (DAM 核心)│   (UUID 引用)   │ (抽象层)    │
└─────────┘                        └──────────┘                └────────────┘
     │                                   │                          │
     │ 不可控                             │ 可控                      │ 可控
     │ 文件可被删除/移动                   │ UUID 命名                 │ 版本快照
     │ 文件夹结构可变                      │ AI 标签                   │ 排序管理
     │ 权限独立                           │ 缩略图                    │ 导出 Excel
     └── 仅浏览 + 选择导入 ────────────────┴── 完整管理 ───────────────┴── 运营使用
```

### 为什么 NAS 不能直接作为 Collection 的来源

1. **引用不稳定**: NAS 路径可能随时变化，Collection 中引用会断裂
2. **无元数据**: NAS 文件没有 DAM 的 AI 标签、合规检查、使用统计
3. **无缩略图**: DAM 缩略图独立生成，NAS 缩略图依赖 Synology API 可用性
4. **无审计**: Collection 版本历史无法追踪 NAS 文件的变更
5. **性能不可控**: NAS 访问速度取决于网络状态

### 四层架构

```
┌──────────────────────────────────────────────────────┐
│                    Collection Layer                    │
│  (虚拟分组 + 排序 + 版本快照 + 导出)                     │
│  类型: listing | campaign | catalog | social_post      │
├──────────────────────────────────────────────────────┤
│                     Asset Layer                        │
│  (UUID 文件 + 元数据 + AI标签 + 缩略图 + 合规)          │
│  来源: Upload | NAS Import | API                       │
├──────────────────────────────────────────────────────┤
│                    Storage Layer                       │
│  files/{path}/{uuid}.ext + thumbnails/                 │
│  未来可选: S3 (dfp_external_storage)                    │
├──────────────────────────────────────────────────────┤
│                    Source Layer                        │
│  NAS (Synology) | Local Upload | OSS (未来)            │
│  角色: 只读浏览 + 选择性导入                              │
└──────────────────────────────────────────────────────┘
```

### Static vs Smart Collection

| | Static Collection | Smart Collection |
|---|---|---|
| 填充 | 手动选择 + 排序 | 规则引擎自动 |
| 状态 | **已实现** | 远期 Phase 8 |
| 参照 | AEM Static, Lightroom Collection | AEM Smart, Lightroom Smart Collection |

---

## Phase 7 实施计划

### Phase 7a: 后端 NAS→Assets 导入完善

- [ ] **真实 NAS 文件下载 API**: 当前 `/api/nas/import` 对真实 NAS fallback 到本地，需要实现 `SynologyNAS.download_file()` 通过 FileStation API 下载文件字节
- [ ] **导入进度回调**: 大文件/批量导入需要 WebSocket 或 SSE 进度推送
- [ ] **去重逻辑增强**: 基于文件 hash（SHA-256）而非仅文件名

### Phase 7b: 前端拖拽实现

三种拖拽流:

| 拖拽路径 | 动作 | UX 反馈 |
|---------|------|---------|
| **NAS Grid → DAM Sidebar** | 导入选中 NAS 文件到 Assets | 进度条 + toast |
| **Assets Grid → Collection Editor** | 添加资产到当前编辑的 Collection | drop zone 高亮 + 计数 |
| **Assets Grid → Collection Sidebar** | 快速创建/添加到 Collection | 弹出 Collection 选择器 |

跨面板拖拽: 从 NAS 直接拖到 Collection → 自动先导入 Assets（隐式导入）

### Phase 7c: UX 打磨

- [ ] Split-pane 持久化: NAS 树 + Assets 网格同屏
- [ ] 拖拽指示器: drop zone 高亮 + 拖拽预览缩略图
- [ ] 批量操作栏增强: 跨面板选中 + 操作
- [ ] 右键上下文菜单: "Add to Collection"、"Import from NAS"
- [ ] 导入进度条: 替代纯 toast 通知
- [ ] 键盘快捷键: Ctrl+A 全选、Delete 移除等

---

## Phase 8: Smart Collection（远期）

借鉴 AEM Assets 和 Lightroom Classic:

- **规则引擎**: 基于标签/产品/合规状态的动态集合
  - 示例: `tag=product_photo AND linked_sku=KS0001 AND compliance=passed`
- **Smart Collection 编辑器 UI**: 可视化规则构建器
- **实时预览**: 编辑规则时实时显示匹配资产数量

---

## 关键文件

| 文件 | 用途 |
|------|------|
| `dam-prototype/main.py` | FastAPI 后端 (SynologyNAS + ErpnextClient + 所有 API) |
| `dam-prototype/models.py` | 数据模型 (Asset, Collection, AssetCollectionItem) |
| `dam-prototype/static/index.html` | Vue 3 SPA 前端 |
| `dam-prototype/AGENT_HANDOFF.md` | Agent 交接文档 |
| `docs/superpowers/2026-06-10-session-summary.md` | **主入口** — 新对话从这里开始 |

## 业界参考

- Orange Logic Media Bridge (2025): 混合存储 DAM, index in-place
- AEM Assets: Static/Smart Collection, S3/NAS/Connected Assets
- Lightroom Classic: Collection/Smart Collection 模型
- vilavi_pim `item_group_browser` 分支: NAS 浏览器参考实现
