# SKU×客户生命周期（2026-11-11）

推荐订单仓 sqlite 加按日 parquet。不建 DocType，不写 EN。①DocType 粒度对，但 4049 行进生产，并绑全局 disabled。②物料组×客户只能批量确认，同组异色会误伤，不能当 D6 键。③现有快照 4049 行（USNJ 1904、USTX 948、波兰 1197），权威全是 unknown_pending，推断与 eligible 分开。取③，②只做确认批量。

键：sku×客户（波兰/USNJ/USTX），未归属不补。字段：lifecycle_status、inferred_status、confidence、sales_ytd、sales_365d、last_sold_on、季节窗、source、evidence_json、evidence_status、en_disabled_snapshot、确认人与时间、valid_until、as_of。

权威态：unknown_pending、active、seasonal、clearance、discontinued、blocked。机器只写候选，人确认才升级。断货不标清仓；没卖过不等于停售。KS0307 波兰 2026 年 126 件为 active 候选，美国 0 不停售。KS0198 自 2025 起仅波兰（233、93），美国有量后归零，为 discontinued 候选。去年同月有量、今年窗口外为 0，为 seasonal。

E/D6：已确认且未过期的 active 或窗内 seasonal 才补；clearance 只卖库存；其余不补。特批另记。周更。active 且 90 天内有售则顺延，免点。反证、改动作、置信度<0.8、季节边界、disabled 变了但仍在卖：入队，不翻态。过期回 unknown_pending。人按型号×客户批，变体跟随，单色相反才拆。审计追加前后态、人、时、证据哈希、原因；快照只追加。disabled 只读：启用不等于 active，禁用不等于 discontinued。三客户都停售后，是否关 EN 另开任务。
