---
okf: v0.1
type: Log
title: missing_products 变更日志
tags: [missing_products, log]
---

# 变更日志

## 2026-08-20
- **修复**: 三角靠枕/无扣成品缺皮壳变体 6 条已按多规格补齐（`PK#KS0001-CMM-153-PURPLE` 因 `variant_of` 不可改而取消 BOM 后重建）。脚本 `fix_missing_cover_variants.py`。
- **记录**: cover-only 暂缓（KS0001 176 / KS0248 27），不补成品。Lesson：`docs/solutions/conventions/erpnext-product-cover-variant-pairing.md`。
- **路由**: 赛狐皮壳 Listing 共享库存代理不走本模块创建有库存 `PK#`，见 `sellfox-cover-inventory`。
- **根因**: 2026-08-07 惯例 REST 示例漏了 `variant_of`/`attributes`；一键配套是复制已有变体而非笛卡尔积。

## 2026-08-11
- **交接补充**: PR #162 后映射表明确为库存同步设计输入而非同步写入授权；HM1510 25 条产品登记已完成，历史“删除”客户码冻结，两个 HM1510 候选受 EN REST HTTP 417 拦截，本轮不绕过、不新建海绵物料。
- **路由**: Amazon 在线商品配对的候选和运营确认流程移交 `amazon_pairing`，并由根级 conventions 文档定义其与多平台配对的边界。
- **知识沉淀**: 新增根级解决方案 `docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md`、`missing-products` Skill 和 `docs/lessons` 全流程复盘；将完整码精确登记、赛狐产品映射、半成品边界及回读验证固化为可触发流程。
- **修正**: 三方审计改为完整通途 SKU 精确匹配，`-Cover/-Foam` 基码只作候选
- **更新**: 从 EN 产品 Item 完整 `customer_items` 回读，保留一码多产品关系
- **生产写入**: 3 条有库存皮壳 SKU 登记到对应 EN 产品并回读验证
- **结果**: 1411 个有库存通途 SKU 中 1397 已登记 EN 产品；剩余 14 全部是已知暂缓项
- **赛狐验证**: 皮壳 108 条、海绵 25 条对应的 EN 产品 SKU 全部存在
- **只读调查**: `PK#` 无客户码；`HM1510` 有 53 个唯一“物料+客户码”组合，本轮未清理
- **新增只读交付**: `build_mapping_workbook.py`（1411 行映射表，一对多 7 / 多对一 128 / 暂缓 14）、`build_foam_status_workbook.py`（25 条海绵现状，HM1510 223/75/0，不写登记）、`fetch_sellfox_pairing.py`（赛狐配对只读盘点）
- **赛狐配对机制**: Amazon 在线产品配对与多平台配对是两套机制；实测 Amazon 50,169 = 26,100 已配对 + 24,069 未配对；多平台 3,285 且 Amazon/Amazon_VC 为 0
- **API 过滤**: `pageList` 支持 searchType/searchContent/onlineStatusList/match/shopIdList/marketplaceIdList；pageSize 上限 200；全量拉取约 9 分钟，缓存于 out/pairing_cache/
- **新增**: `amazon_pairing` 子项目交接；Amazon 在售未配对 4,407、别名命中 442、可导入 91、人工核对 133、三角靠枕候选 275、不一致 65；建议表补标题/中文提示/双方名称；HM1510 客户码写入被 EN REST 校验（仅产品/套件#物料组）拦截。

## 2026-08-10
- **更新**: `docs/solutions/conventions/erpnext-item-variant-creation-convention.md` — 新增「属性集完整性」「客户码唯一」「abbr 必带」「变体命名」等坑 + 审计确认（仅 KS0013 缺颜色已修复）
- **新增**: `fix_ks0013_color.py` — 修复方形枕套 KS0013 缺颜色（KS0013-HLR-80-COFFEE）
- **更新**: `AGENT_HANDOFF.md` — §4.5 EN 核心原则（防止 AI 犯错）
- **背景**: 审计确认其余物料属性完整；根因是 KS0013 历史属性集不完整
- **新增**: `AGENT_HANDOFF.md` — 完整交接文档（背景/当前状态/下一步/技术细节/经验教训）
- **新增**: `create_en_materials.py` — EN 老产品补齐脚本（星球/石头/张嘴熊/泰迪/方形枕套，幂等，--phase 1-6）
- **更新**: `specs/old-product-completion-plan.md` — 标记阶段1(EN)完成，更新实施记录
- **背景**: 通途未匹配 54→14；EN 老产品补齐完成；下一步赛狐侧
