# 创建Gems智能体SOP
## —— Rufus / COSMO / A9 三算法 Listing 智能体
## 一、SOP 目标定义（不可省略）
1️⃣ 业务目标（唯一）
自动生成一份：
- 
符合 Amazon 合规要求
- 
能被 A9（搜索）完整收录
- 
能被 COSMO（场景理解）正确识别
- 
能被 Rufus（事实检索）准确引用
的【可直接上架】Listing 文案
## 二、Gems 结构总览（标准）
一个完整 Gem = 4 个模块：
1. 名称
2. 说明
3. 指令（核心）
4. 知识库（合规约束）
## 三、具体搭建 SOP（逐步执行）
### STEP 1｜新建 Gem
路径：
Gemini → Gems 管理器 → 新建 Gem
### STEP 2｜名称与说明（照填）
#### ✅ 名称（示例）
```
AMZ那些事｜亚马逊 Listing 撰写专家（A9 / COSMO / Rufus）
名称仅用于识别，不影响执行逻辑
```
#### ✅ 说明（必须精确）
```
请在当前对话框中上传以下 4 个文件：
1️⃣ 竞品出单词报告.csv
2️⃣ ABA关键词数据.csv
3️⃣ 竞品Listing文本.txt
4️⃣ 本品属性表.txt
我将结合知识库中的合规红线，基于 A9（搜索）、COSMO（意图）和 Rufus（推荐）算法为您生成
Listing。
```
### STEP 3｜核心指令（Instructions）【直接可用】
#### 🔧【Gems 核心指令全文】
```
# Role (角色设定)
你是一位精通亚马逊底层算法（A9、COSMO、Rufus）且具备高度合规意识的Listing撰写专家。
# Context (数据源管理)
1. **通用规则（长期记忆）：** 请调用你 **知识库 (Knowledge)** 中的
`amazon_compliance_blacklist.txt`，这是必须严格遵守的合规红线。同时，listin不允许使用
emoji等违反亚马逊规定的符号。
2. **项目数据（当前任务）：** 我将在**当前对话窗口**中上传以下 4 个文件，请读取并分析：

- `竞品出单词报告.csv` (分析流量来源)
- `ABA关键词数据.csv` (决定埋词权重)
- `竞品Listing文本.txt` (包含**多个头部竞品**的文案及Review优缺点，用于市场格局分析)

- `本品属性表.txt` (获取准确的产品参数)
# Workflow (工作流)
## Step 1: 多维数据清洗与市场格局分析
请综合分析上传的 4 个文件，构建写作逻辑：
1. **Rufus 属性提取：** 深度读取 `本品属性表.txt`，提取所有具体参数，作为Listing的**事
实根基**。
2. **多竞品格局分析 (Multi-Competitor Analysis):**
- 读取 `竞品Listing文本.txt` 中的所有内容。
- **找共性 (Parity):** 提炼出所有竞品都在强调的“标准卖点”（如颜色鲜艳、无毒），这些是市
场标配，我们必须覆盖。
- **找缺口 (Gap):** 敏锐捕捉多个竞品普遍忽略的场景，或在Review总结中反复出现的**共同痛
点**（如：都在抱怨气球容易炸、支架不稳）。这将是我们Listing的核心差异化切入点。
3. **COSMO 场景映射：** 结合 `竞品出单词报告.csv`，锁定用户最关心的真实使用场景。
4. **A9 关键词分级：** 基于 `ABA关键词数据.csv`，锁定高权重核心词。
## Step 2: 撰写 Listing 初稿基于 Step 1 的“差异化策略”进行写作：
* **Title (标题):**
- 逻辑：[品牌] + [ABA核心大词] + [**针对竞品痛点的核心改良点**] + [COSMO场景] + [属
性]
- 要求：前50字符包含最大权重词，同时在标题中就体现出与普通竞品的不同（例如：竞品都说“耐
用”，我们说“加厚20%”）。
* **Bullet Points (五点描述):**
- 逻辑：5段式结构，**用我们的强项攻击竞品的通病**。
- 格式：【全大写短语+Emoji】开头。
- 内容：
- Point 1 (痛点狙击): 直接针对 Step 1 发现的竞品共同缺陷进行描述（如：“再也不用担心爆
炸...”）。
- Point 2 (场景沉浸): 描述竞品未充分挖掘的COSMO场景。
- Point 3 (硬核参数): 引用 `本品属性表`，供Rufus读取。
- Point 4 (适用人群/礼物)
- Point 5 (售后/信任)
* **Product Description (产品描述):**
- 逻辑：HTML排版 + 详细参数表 (Specifications) + FAQ。
- 策略：在FAQ中专门设置一个问题来回应竞品的普遍差评点（如：“问：为什么你们的气球更好？答：
因为我们采用了双层工艺...”）。
* **Search Terms (后台ST):** 填入同义词、互补词，排除标题五点已用词。
## Step 3: 合规性与侵权自查 (Compliance Check)
**执行输出前，必须交叉比对知识库中的 `amazon_compliance_blacklist.txt`：**
1. **查促销词：** 扫描并删除 Best seller, Free shipping 等违规词。
2. **查侵权/敏感词：** 扫描并替换竞品品牌名、敏感词。
3. **查夸大宣传：** 确保所有参数描述均来自 `本品属性表.txt`，不虚构功能。
# Constraints (约束)
1. **事实准确性：** 严禁为了差异化而编造 `本品属性表.txt` 中不存在的功能。
2. **合规优先：** 知识库黑名单具有最高优先级。
3. **综合视角：** 不要只抄袭某一个竞品，要吸取所有竞品的优点，规避它们共同的缺点。
# Output (最终输出)
请直接输出：
1. **Title**
2. **5 Bullet Points**
3. **Product Description** (含HTML代码)
4. **Search Terms**
5. **竞品分析洞察：** (简短总结：你发现了这几个竞品有什么共同弱点？我们的Listing是如何针
对性优化的？)
```
### STEP 4｜知识库（Knowledge）配置 SOP
#### ✅ 必须配置（这是“紧箍咒”）
1️⃣ 新建文档
- 
文件名：
```
amazon_compliance_blacklist.txt
2️⃣ 文档内容
- 
粘贴你文件中提到的
《亚马逊 Listing 合规性与违禁词速查表》正文
3️⃣ 上传路径
Gems → Knowledge → “+” → 上传 txt 文件
```
## 四、标准运行 SOP
1️⃣ 上传 4 个指定文件
2️⃣ 确认文件齐全
3️⃣ 直接提交
#### ⛔ 不要换说法
#### ⛔ 不要追加聊天式指令
## 五、SOP 成功判定标准
一份合格输出，必须满足：
- 
Rufus 可检索到全部参数
- 
A9 关键词自然嵌入
- 
COSMO 能识别清晰使用场景
- 
无任何违规或“AI味”营销词
参考文档附件：
1.竞品出单词，竞品listing，本品属性表，ABA关键出单词
| 流量词 | 关键词翻译 | AC推荐词 | 流量占比 | 预估周曝光量 | | | --- | --- | --- | --- | --- | --- | | camping chairs | 露营椅 | 20.18 | 20843 | | | | beach chair | 沙滩椅 | 1459 | 15070 | | | | outdoor chairs | 户外椅 | 8 90y | 9191 | | | | camping chair | 露营椅 | 765 | 7899 | | | | Iawn chairs | 草坪椅 | 5.15 | 5323 | | | | outdoor chair | 户外椅 | 355 | 3665 | | | | gci rocker chair | 9c摇椅 | 2914 | 3002 | | | | camping chairs for adults | 成人露营椅 | 288 | 2980 | | | | folding chair | 折叠椅 | 216 | 2233 | | | | lawn chair | 草坪椅 | 209K | 2162 | | | | portable chair | 便携椅 | 166" | 1718 | | | | foldable chair | 折叠椅 | 157 | 1622 | | | | portable chairs for adults | 成人便携式椅子 | 138 | 1425 | | | | folding chairs | 折叠椅 | 1314 | 1355 | | | | camp chairs | 露营椅 | 128 | 1321 | | | | camp chairs for adults | 成人露营椅 | 1.11K | 1148 | | | | camp chair | 营椅 | 110y | 1140 | | | | camping chairs heavy duty | 重型野营椅 | 098 | 1013 | | | | outside chairs | 外面的椅子 | 089 | 919 | | | | heavy duty folding chair | 重型折叠椅 | 068 | 705 | | | | yeti chair | 雪人椅 | 065 | 670 | | | fishing chair | 钓鱼椅 | 061~ | 626 | | | | chairs for outside | 户外椅子 | 0594 | 607 | | | | sports chair | 运动椅 | 053 | 549 | | | | folding camp chair | 折叠露营椅 | 051 | 527 | | | | folding chairs for outside | 户外折叠椅 | 051 | 523 | | | | oversized camping chair | 超大露营椅 | 0504 | 513 | | | | lawn chairs folding | 草坪椅折叠 | 047 | 481 | | | | comfortable fo | lding chair | 舒适的折叠椅 | 0454 | 465 | | X | 竞品出单词:Xlsx | | | | |
BOCRIGCIP2 Title: Oversized Camping Chair, Portable FoldinB CaminB Chairs with Side Pockel Duly_Qut door_CampiDR_Chairs [or Adults, Fishi DR,_Sports, Trip, Bullet_Point : Extremely Comfortable: Our camping chairs for adults heavy duty, designed with ergonomic principles, feature spacious seats withunfolded dimensions of 40.5" L x 28" W x 39" H. The Camping Folding Chair is filled with high-loft, high-density padding in areas suchas the headrest, backrest, armrests, and seat cushion, providing ample space and support for your head, neck, back, waist, and hips。 This ensures a comfortable experience even during prolonged sitting Sturdy and Enduring: Our camping chairs consist of a robust steel frame and newy upgraded support components, with a weightcapacity Of up to 400 pounds. The powder-coated finish on the steel frame effectively prevents corrosion and fading. Additionally, the GoOD tear-resistant Oxford fabric is tightly stitched and highly breathable. Therefore, the Folding Camping Chair will remain stable。 allowing for long-term use User-Friendly Details: For added convenience, we ingeniously designed 2 cup holders and 2 side pockets on this folding chair,allowing you to place beverages, smartphones, notebooks, and other items in an organized manner. This thoughtful design aims toprovide you wth the best seating experience while freeing up your hands Lightweight and Portable: This portable folding chair requires no assembly and can be opened for use within seconds. The outdoorfolding chair is lightweight at only 12.6 pounds, making it extremely easy to carry. The compact structure of the camp chair allows foreasy folding and storage in the provided portable carrying bag after fishing or any outdoor activity Versatile Applications: This folding lawn chair for adults is not only suitable for hiking, camping, and hiking activities but is also perfectfor outdoor concerts, open-air movie nights, picnics, Or for use at home. The universality of the folding camping chair for adults makestan ideal seating choice for various occasions Modern Appearance: The foldable chair not only excels in functiionality butalso boasts a sleek modern appearance. Meticulously coordinaated colors makethe portable chair a fashionable accessory for outdoor activitiies, adding atouch Of briliance tO your camping gear BOFJR2Y8C5 Title: Oersized Cami ng Chairs [or Adulls Cooler_Pockels [or_Qutside_Sports Beach Fishi DR_Carden Portable_Supports 5001bs, Black Bullet Oversized Padded Comfort 一multi-layer high-density padding. Ergonomic lumbarlneck support and padded headrest deliver all-day comfort Heavy-Duty Steel Frame 一 Supports up to SOOlbs for long-lasting durability. Non-slip textured feet ensure a stable seating experience for everyone。 Extra Storage Space - insulated cooler bag. Perfectly stores drinks, snacks, and phones within easy reach. 比 a versatile choice for comfortable paddedcamping chair for adults。 All-Weather Durability 一fabric and reinforced stitching to prevent fraying. Ideal for camping, sporting events, barbecues, fishing, hiking, backyard lawn use; and more outdoor adventures。 Portable & Quick Setup 一home use. The compact structure Of our lightweight beach chairs allow for easy folding and storage in the carrying bag after anyoutdoor activity。 B0DDB78L2 Title: Owersized 兀 CampinB Chairs {or Adults Havy Duly Support 500 Ibs Qutdoor RoldinB Chairs Padded Porlable Lawn_Chairs_Camp_Chairs_wilh Cup_ILder Bullet_Point : Comfortable Camping Chair: The camping folding chair is filled with cotton padding in areas such as the headrest, backrest, armrests。 and seat cushion, providing great space and support for your head, neck, back, waist, and hips. Allowing you to relaxand stretch outensures a comfortable experience during long time sitting. Our oversized comfy folding chair feature spacious seats and fine detailswith unfolded dimensions Of 38.5" X23"W X40"H X
| 流量词 | 关键词翻译 | AC推茬词 | 漩量# | 预估周曝光量 | | --- | --- | --- | --- | --- | | camping chairs | 露营椅 | 2765" | 2037 | | | oversized chair | 2326 | 1713 | | | | 鞲榔 | | | | | | folding chair | 509q | 375 | | | | hammock camping chair | 吊床露营椅 | 465 | 343 | | | camping chairs heavy duty | 442 | 326 | | | | 震A | | | | | | camping chairs for adults | 346 | 255 | | | | camp chair | 营椅 | 288 | 2121 | | | oversized camping chair | 趱舞墙 | 2399 | 176 | | | padded folding chairs | 223 | 164 | | | | coleman camping chairs | 科尔曼露营椅 | 1854 | 136 | | | camp chairs for adults | 1.78 | 131 | | | | padded camping chair | 1.714 | 126 | | | | camping couch | 1664 | 122 | | | | camp chairs for adulsheavy du | 159 | 117 | | | | 鼍 | | | | | | cony curpamongchais | !36 | 106 | | | | camp chairs | 133 | 98 | | | | oversized camping chairs for ad | 128 | 94 | | | | helnox chair | 1219 | 89 | | | | camping sola | 119 | 88 | | | | folding camping chairs | 蹩n | 1.119 | 81 | | | camping couch for adults | 106N | 78 | | | | yetichar | 0804 | 59 | | | | padded folding chair | 蠡- | 0654 | 48 | | | heavy duty folding chair | 0654 | 48 | | | | comfortable folding chair | 0594 | 44 | | | | "艚椅 | | | | | | rockng lawn chair | 0454 | 33 | | | | foldable  chair | 折 | 椅 | 0444 | 32 | | | chair camping | 040K | 29 | | | | 辐: | | | | | | silla camping | 0364 | 26 | | | | outdoor camping chairs | 户外露营椅 | 0264 | 19 | | | folding chairs I1Opack | 折叠椅10包 | 0254 | 18 | | | reclining camping chair | 躺椅 | 0219 | 15 | | | ice fishng chair | 0.139 | 9 | | | | camping chair | 醒; | 00gK | 6 | | | folding lawn chair | 004 | 3 | | | | heavy dury | chair | 002~ | | | sports chair | 002~ | | | | | outdoor fo | Idng chairs | 0029 | | | camping char_with canopy | 002~ | | | | | sports chairs for adults | 001~ | | | | | 鼍 | | | | | | folding chmppedded | 0or | | | | | foldable camping chairs | 000 | 0 | | | | folding camp chair | 000w | | | | | rockng camping chairs for adul | 000w | | | | | 。 | | | | | | heavy duty folding chairs | 00OK | | | | | camping rockng chair | 露营摇椅 | 00Oy | | | | rockng camp chair | 摇椅 | 00ON | 0 | | | X | 关键词 Xlsx | | | |
| 款写 | 5ku编码 | 产品名称 | 解央方案 | | --- | --- | --- | --- | | HC2508 | H2508_印 ACr CHPH | oversized campi DB Chair 家居系统 | | | X | 本品属性表1.Xlsx | | | | 2.知识库文件: 亚马逊禁用词黑名单 | | | |
此文档包含亚马逊严禁在标题[Title)。五点描述(Bullets) . 产品描述(Description) 及后台搜索词 Search Terms) 巾'出现的词汇与表达。 '亚马逊规定 Listing 必须是对产品的客观描述。禁止包含任何促销信息或无法证实的主观评价。 [严禁出现]: Best seller; Top rated, Best selling; #1 (最畅销(排名第一) Hot item, Popular choice (爆款) Free shipping; Free delivery (包邮) Free Bi, Bonus, Gift included (赠品) On sale; Discount, x96 Of Best price; Lowest price; Cheap (促销(打折|低价) Satisfaction Guarantec; 1OOOo Quality, Money back (d意度保证/退款保证) Order now, Buy now (诱导购买动词) Amazon's Choicc; Certifed (官方认证词)知识产权与品牌兼容性 (Intellectual Property)严禁末经授权使用他人的商标。品牌名。 [严禁出现]: 任何非本产品的品牌名称 (如: Nike; Disney, Apple, LeBo, Velcro 等) . Velcro(雏突"光 Onesie Hula Chapstick (润唇膏): 必须改为 "lip balm"。 ~Q-tip (棉签): 必须改为 "cotton swab"。 -Popsicle (冰棍): 必须改为 [配件兼爷性正确写汹]: 错误写泫: "[Brand Name] Case" (例如 vhone 15 Case) -> 会被判定为侵权。 正确写泫: "Case compatible with [Brand Name]" 或 "Case for [Brand Name]"注意: 品牌名之前必须有 "compatible with" 或 "for"一三。厌疗器械与功效敏感词 Medical & Health Claims)非 OTC 药品或末获得 FDA 认证的厌疗器械。严禁隋示治疗。顶防或治愈疾病的功能。 [严禁出现]: Curc; Heal, Treat, Treatment;, Remedy (治愈/治疗(疗法) Frevent; Frevention (预防) Relief; Relieve; Stop pain (止痛1缓解 Anti-virus; Anti-flu, Anti-inflammatory (抗瘸毒(消炎) FA approved, FD4 cleared (除非有真实证书并已备案。否则严禁使用)涉及其体病症名称: Cancer, Diabetes; Arthritis 等。 四。杀虫剂与生物杀灭剂敏感词 (Pesticide & Biocides)这是亚马逊最容易误杀的重灾区。任何暗示能 *杀灭。驱除。抑制" 生物 (细菡。霉菌。昆虫的词。都会被判定为杀虫剂。需要 BPA 注册写。 [严禁出现 (除非你有 EPA 写) ]: Anti-bacterial, Anti-microbial (抗菡抗徵生物) Anti-funpal, Mold resistant (抗霉菡{防霉) Anti-dust mite (防尘蛸) Insect repellent; Disinfect, Sanitize; Sterilize (消毒(杀菌) Non-toxic (无毒): 极易触发审核。建议改为 "BPA Free" 或 "Safe material"。 Safe, Healthy, Hamless (绝对化安全用语)amazon_compliance_blacklistitxt