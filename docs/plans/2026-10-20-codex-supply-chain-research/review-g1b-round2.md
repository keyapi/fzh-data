---
okf: v0.1
type: Reference
title: G1b修复与每日备份链路第二轮复审
date: 2026-10-21
reviewed_ref: aad55822d942706bc0ba7177e5523c757d0d6cf7
status: fixes-partially-accepted-not-g1-acceptance
---

# 结论与范围

**本轮有实质修复，关闭已验证的子项；G1B01–05还不能整体关闭。** 首轮抽取脚本修好不等于新增“stock_daily_backup → g1b_from_daily_backup → coverage”端到端可靠。9/9未发分解difference=0只能证明该分解算术一致，不能证明生产四量、当前供给完整性或全family验收。

输入为用户2026-10-21粘贴记录（其中较早“补跑中”已由末段“09:46补跑成功”更新），以及[Claude #300固定aad55822](https://github.com/keyapi/fzh-data/tree/aad55822d942706bc0ba7177e5523c757d0d6cf7/docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract)。只审修复与重跑差异，不重做研究，不读本地业务xlsx/库存JSONL/凭证，不调用生产API/浏览器/任务计划器，不改Claude文件。上轮见[首版复审](review-g1b-first.md)。

## 1. 可以关闭什么

| 原项 | 本轮结论 | 已核证据与边界 |
|---|---|---|
| G1B01 未采样当0 | 部分接受 | 缺口现在过滤sampled_complete，旧450/501已撤回；新131/194/127仍是Claude报告，Codex未重跑原始数据。complete如何绑定实际选中数据仍有下节问题 |
| G1B02 坏列/坏数 | 部分接受 | 必需列/缺月有报告，direct snapshot的None/非法值返回None，已离线验证；订单非整数只计数仍纳入，转换器重新将空值变0 |
| G1B03 页数截断 | 原direct snapshot满页上限子项关闭，其余部分接受 | 满max_pages返回truncated且complete=false已离线验证；每日备份对响应形状仍不严格，不能整体关闭 |
| G1B04 重复库存 | 同值快照不再重复加总，冲突处理部分接受 | 新load_stock保留选中文件且计duplicate_conflicts；但其冲突/坏值不降complete，转换器冲突first-wins |
| G1B05 工序与SE | 部分接受 | 已从跨全部工序总和改为按工序，并新增SE查询；但首/末工序定义和SE未知处理尚未闭合 |
| G1B06 DN自身键 | 代码投影缺口关闭 | 同SHA上游与导出都有dn_line_id，so_line_id继续为SO外键。100行自身ID非空/唯一是Claude报告，未独立读取原始结果 |
| G1B07 差7 | 文档与分解代码缺口关闭 | 421+622+9−16=1036，合成分解difference=0；不得用超发−16冲减另SKU/另SO待履约的采购需求，实际履约应保留正未交、Closed/超发各自语义 |
| G1B08 BOM歧义 | 首映射fail-open缺口关闭 | 冲突客户码进ambiguous并移除，合成双EN命中被隔离。canonical alias/共享池的现实核对仍为后续数据工作，不擅自混池 |
| G1B09 合仓依据 | 业务口径问题关闭，系统审计另留pending | 用户确认2026-09改名及旧皮壳并入美中；脚本注释是佐证，不替代余额凭证。接受user-confirmed-rename，不再让业务重答；不把5/8月旧余额叠加当前库存 |

`lead_date`已不再导出、so_delivery_date上游已补；on_hand与含在途名义覆盖分列，接受这些P2修正。登记/补跑成功按来源记录，未验证本机调度运行实况。

## 2. 仍需修复：沿实际输入路径而非只看旧脚本

所有行号对应固定aad55822。下表P1影响事实结果，P2为报告/抗异常完善；反例复现不意味着原批次已触发。

| 新ID | 级别 | 具体问题与来源行 | 最小修复与验收 |
|---|---|---|---|
| RR01 | P1 | coverage.py:277–278把任意旧快照的complete仓取并集，:283–287又选最新数据；冲突/坏值:311–318不降状态，:378按branch放行 | complete随选中的具体仓/文件/版本绑定，冲突或坏行使对应SKU/仓incomplete；多物理仓需已确认范围全覆盖，不能任一仓complete代表整个branch。旧10件complete＋新0件incomplete不得得到sampled_complete零库存；同文件冲突也不能完整放行 |
| RR02 | P1 | from_daily_backup.py:82–87用float(value or 0)，:92–94对相同仓/SKU所有重复直接丢后者 | 缺值/NaN/Infinity/负数/分数按字段口径校验，unknown不变0；重复同值计数、异值conflict，不保留首值当确定库存。保留原行/原因和单位，坏仓不得complete |
| RR03 | P1 | stock_daily_backup.py:161按rows_of把未知响应当空，:170–172立刻complete；Client.call也接受None业务码。direct snapshot对code200但datas未知结构仍可走空列表 | 区分合法空数组和无法解析/业务失败；结构与分页终止均校验。无仓清单/请求仓不命中不能靠all([])称全量成功；坏行也要降低对应完整性 |
| RR04 | P1 | en_extract.py:86–96把“有卡的第一道/最后一道”当实际首/末道 | 路由cut→sew而只有sew卡时，first=cut且数量unknown，不可改名first=sew。无末道同理；保留JC自身ID/有效状态与批次覆盖，排除虚拟/撤销卡。上游当前过滤docstatus<2，取消卡合成例主要验证helper边界，未声称该批已含取消卡；缺首工序改取后道本身是有效缺口 |
| RR05 | P1 | en_extract.py:183 SE详情缺失返回finished_qty=None但error=None；:323–325把未汇总到的WO量当0 | 每WO保留查询完整状态；已知无SE才0，详情失败/无匹配成品行/单位未知保持unknown。SE明细需保留行ID、item、stock_uom/转换、目标仓、finished标记，才能证实单位一致与守恒；不能由“63张SE、query_error=None”推出四量通过 |
| RR06 | P1 | coverage.py:378只看branch complete；Wayfair只要API快照complete就被当sampled_complete，未校验权威库存来源 | Wayfair后台manual才是本轮指定库存源；通途API完备性与业务库存可信性两字段分开。即使09:46全仓APIcomplete，Wayfair92/4/2也不能变后台实盘。保留数据供对照，不进入可确认供给/缺口 |
| RR07 | P2 | from_daily_backup.py:65–68漏文件continue，:110–111仍报告complete；字段complete_warehouses在coverage.load_stock里又没有逐仓消费 | 请求仓/实际读完仓/文件hash/行数/页数对齐；漏文件明确失败。注意当前只缺文件、warehouses=[]时coverage不会因此直接放行该仓，本轮不夸大为必然假零；但转换产物的global complete确为假。混合一仓失败一仓成功时，正确仓的complete也应独立保留 |
| RR08 | P2 | coverage.py:189–190非整数只计数仍纳入；NaN/Infinity可在int(qty)处异常；non_family_rows把所有未映射都命名非family | 保留逐行invalid/pending，不把非整数件数当成功毛量；缺月/列虽window_complete=false，仍需限制不完整窗口输出资格。759未匹配pending与其他out_of_scope依据保留，不因未命中family直接裁定 |

另：daily backup同日用固定JSONL路径`open("w")`覆盖，旧manifest可能暂时指向新半成品；建议run_id目录＋临时文件完成后原子发布manifest，并记录hash/脚本版本。此处是当前小管道的文件一致性要求，不扩建监控平台或重写架构。

## 3. 新结果如何使用

- **131/194/127**暂记为Claude该批重算报告，不称Codex复现或G1门槛通过。需给确切coverage产物hash与选中快照、三个完整仓的输入来源和cutoff；results§6目前引用2026-10-20 18:19，而粘贴又报告10-21 09:46补跑，应区分两批，不自动用后批“complete”给前批背书。
- **9/9 difference=0**是同一SO字段分解回同一totals的自洽校验，值得保留；还需独立DN行符号净额与SO行/单位核验、SE/JC数量完整性，不代表四量守恒。top10选择清单需有原始10个→去重客户码→查询成功/跳过/未映射/失败的去向；当前文字“9客户码＋1TT”与表内9行（含TT）需解释。不能把“9/9”自动称“top10全覆盖”。
- **浏览器库存结存不是成本模板**：接受原始downloads库存结存、合并output库存与派生成本模板三类区分；销售库存报表SKU不全不能替代结存备份。1,527/568/1,140请统一标注“唯一SKU/仓×SKU/别名/规范物料”粒度和同cutoff比较范围，不能直接按不同粒度断言覆盖更全。
- **任务与API空结果**：02:17成功/09:46补跑按Claude运行报告登记；本轮没检查日志、任务或ASCII副本，不改配置。0条调拨只说明该查询范围/权限/接口返回零，Wayfair供货归属unknown保持；不推断现实没有调拨，不等待这项阻塞已知事实修复。

## 4. 本轮可复跑证据与下一步

[g1b_round2_probes.py](g1b_round2_probes.py)复用前轮离线AST读取工具，固定aad55822，仅用合成临时JSON/JSONL和stub，无生产模块导入或API。**8个剩余问题反例复现＋4个修复正例通过**（差7分解、BOM歧义移除、direct满页上限、direct缺/坏数None）；旧35个契约例不变且通过。这里“通过”指探针符合观察预期，反例意味着仍有缺陷，不是生产验收通过。

先修RR01–RR06并对实际采用的daily转换入口添加同类负例，用既有本地输入重跑，带manifest/hash/逐行与异常处置；再扩全family。已关闭的G1B06/07/08子项不重开、G1B09业务确认不反复追问。Wayfair手工实盘/供货归属、历史迁移凭证继续独立pending，不阻塞修复与已知事实回放。无需再泛调研。

主Agent实跑并核对源码，另有便宜模型只读复查库存链路；采纳经核实的发现，已纠正“漏文件必然让coverage标该仓complete”的过度推论。
