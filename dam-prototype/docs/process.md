# DAM 项目开发方法论

> FZH 跨境电商 PIM+DAM 系统 — 从调研到交付的全过程记录
> 目标：形成可复制、可传播的内部工具开发方法论

---

## 1. 项目背景

- **公司**: FZH 跨境电商（家居纺织品），自有工厂，销售平台 Amazon/Wayfair/Shopify
- **现有系统**: ERPNext (ERP) + 通途/赛狐 (OMS) + NAS (文件存储)
- **痛点**: 产品图片/视频/文档分散在 NAS 各处，运营团队找不到、不知道版本、无法统一管理
- **目标**: 构建 PIM（产品信息管理）+ DAM（数字资产管理）系统

---

## 2. 方法论：四阶段流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 1. 调研   │ → │ 2. 设计   │ → │ 3. 原型   │ → │ 4. 开发   │
│ Research │    │ Design   │    │ Prototype│    │ Build    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
  1-3 天          3-7 天          1-3 周          持续迭代
```

### 2.1 调研阶段 — "先搜再造"

**原则**: 项目 AGENTS.md 铁律：先搜项目内 → 搜网上 → 再自己造

**本次实践**:
1. **市场调研**（3 个并行子 Agent）：Pimcore/Akeneo 开源方案 + Salsify/Plytix/inriver 商业方案 + Frappe 生态
2. **结论**: 市场无现成方案同时满足「ERPNext 深度集成 + DAM + 中英双语 + 本地部署 + 零许可费」
3. **决策**: 自建，分两步走（先原型验证再 Frappe 迁移）

**关键收获**: 并行 Agent 调研是最高效的方式。3 个 Agent 同时跑，30 分钟完成等效 1 天的调研量。

### 2.2 设计阶段 — "DESIGN.md 先行"

**原则**: Open Design 方法论：设计系统必须是纯文本、可版本化、Agent 可理解

**本次实践**:
1. 安装了 `frontend-design` (Anthropic 官方, 517K installs) 和 `brainstorming` (Open Design)
2. 调研了 6 个 DAM 平台 UI（AEM Assets / Bynder / Brandfolder / Cloudinary / Pimcore / Acquia）
3. 选型「Refined Functional」设计方向
4. 编写了 `DESIGN.md`（9 段规范：视觉主题、配色表、字体、组件、布局、深浅层级、DO/DON'T、响应式、Agent 指南）

**关键收获**: 先定设计令牌再写代码，避免了「边写边调样式」的浪费。DESIGN.md 约 150 行，Agent 每次生成前端时自动遵循。

### 2.3 原型阶段 — "可交互验证，不是看图"

**原则**: 原型必须是可操作的 HTML，运营同事能直接在浏览器里用。不要 Figma 截图。

**本次实践**:
1. 第一版原型（FastAPI + Vue 3 CDN + mock 数据）：快速验证布局和交互
2. 用户反馈 → 调整方向 → 安装 Skill → 制定 DESIGN.md
3. 第二版原型（遵循 DESIGN.md + frontend-design skill）：更精致的视觉，完整的交互逻辑
4. 在浏览器中验证：上传、筛选、详情面板、批量操作、暗黑模式

**关键收获**: 两版原型间隔不到 2 小时，从「能用」到「好看」。Vue 3 CDN 免构建方案对内部工具完全够用。

### 2.4 开发阶段 — 待进行

---

## 3. 技术决策记录 (ADR)

### ADR-001: 自建 vs 现成方案
- **决策**: 基于 Frappe/ERPNext 自建 PIM+DAM
- **理由**: 技术栈对齐（Python）、零许可费、ERPNext 深度集成、渐进交付
- **拒绝的方案**: Pimcore (PHP 栈)、商业 SaaS (年费 $12K-180K+)

### ADR-002: 先原型验证再框架迁移
- **决策**: Phase 1 用 FastAPI + Vue 3 + SQLite 本地原型，Phase 3 迁入 Frappe Pages
- **理由**: 设计自由度高、迭代快、风险隔离。Frappe Pages 已验证支持 Vue 3

### ADR-003: Vue 3 CDN 免构建
- **决策**: 不用 React/Next.js，不用 npm/webpack
- **理由**: 团队非前端出身，Vue 3 学习成本低。内部工具不需要 SSR/SEO。Frappe Pages 原生支持 Vue

### ADR-004: DESIGN.md 作为设计令牌单一源
- **决策**: 所有颜色/字体/间距定义为 CSS 变量 + Markdown 文档
- **理由**: AI Agent 可直接读取遵循。开发者一处改全局生效。Git diff 可审查设计变更

### ADR-005: 文件存储 NAS 保留
- **决策**: DAM 文件存储在现有 NAS，数据库只存元数据
- **理由**: 已有基础设施，UUID 命名避免冲突，未来可切换 S3

---

## 4. 工具链

| 工具 | 用途 | 安装方式 |
|------|------|---------|
| `frontend-design` | UI 设计质量约束（禁止 AI slop） | `npx skills add anthropics/skills@frontend-design` |
| `brainstorming` | 结构化设计对话 | `npx skills add nexu-io/open-design@brainstorming` |
| `simplify` | 代码质量三角审查 | Claude Code 内置 |
| `find-skills` | 发现更多 Skill | Claude Code 内置 |

> 暂未安装 `obra/superpowers`（需 Claude Code 内置 plugin marketplace），等后端开发阶段再评估。

---

## 5. 经验教训

### Lesson 1: 不要跳过调研直接写代码
第一次冲动写了原型 → 用户纠正方向 → 浪费了一版原型的时间。正确顺序是：调研 → 设计令牌 → 原型。

### Lesson 2: DESIGN.md 是 Agent 协作的接口
没有 DESIGN.md 时，Agent 生成的 UI 风格每次不同。有了 DESIGN.md 后，所有前端产出自动遵循同一套设计语言。

### Lesson 3: 并行 Agent 调研效率极高
3 个 Agent 同时跑市场调研，覆盖了开源/商业/Frappe 三个维度。等效 1 天的人工调研量，30 分钟完成。

### Lesson 4: Vue 3 CDN 对小团队完全够用
不引入 npm/webpack/Node 构建工具链，迭代速度极快（改 HTML → 刷新浏览器 → 立刻看到）。

---

## 6. 当前状态

- [x] 市场调研（开源 + 商业 + Frappe 生态）
- [x] 战略决策（自建，两步走）
- [x] Skill 安装（frontend-design + brainstorming）
- [x] DESIGN.md 设计令牌
- [x] DAM 原型 v2（可交互，浏览器验证通过）
- [ ] UX 用户旅程设计
- [ ] 后端开发（FastAPI + SQLite）
- [ ] 运营团队用户测试
- [ ] Frappe 迁移

---

**创建日期**: 2026-06-09
**维护者**: FZH 开发团队
