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
| 流量词 | 关键词翻译 | AC推荐词 | 流量占比 | 预估周曝光量 |
| --- | --- | --- | --- | --- |
| campng Chars | 露营椅 | 2018 | 20843 |  |
| beach char | 沙滩掎 | 1459 | 15070 |  |
| outdoor chars | 户外椅 | 890N | 9.191 |  |
| camping char | 露营椅 | 765 | 7899 |  |
| 旧m chars | 草坪掎 | 5.15 | 5323 |  |
| outdoor char | 户外椅 | 355 | 3665/ |  |
| gcirocker char | gci摇掎 | 291 | 3002 |  |
| campng Chars lor adults | 成人露营掎 | 288 | 2980 |  |
| folding char | 折叠椅 | 216 | 2233/ |  |
| bam char | 草坪椅 | 209 | 2.162 |  |
| portable char | 便携掎 | 16BK | 1718 |  |
| foldab le char | 折叠椅 | 157 | 1622 |  |
| portable chars for aduls | 成人便携式椅子 | 138 | 1425 |  |  |
| foldng chars | 折叠椅 | 131 | 1355 |  |  |
| carp chars | 露营椅 | 128 | 1321 |  |
| camp chars lor adulls | 成人露营椅 | 111 | 1.148 |  |
| camp char | 营椅 | 1.10 | 1.140 |  |
| camping chars heawy = | July | 重型野营椅 | 098 | 1013/ |
| outside Chars | 外面的掎子 | 083 | 919 |  |
| heawy duty foldng char | 重型折叠椅 | 068 | 705 |  |
| yeti Char | 雪人椅 | 065 | 670 |
| fishng char | 钩鱼椅 | 061驺 | 626 |  |
| Chars lor Oulside | 户外椅子 | 05躺 | 607 |  |
| sorts char | 运动掎 | 053 | 549 |  |
| folding camp char | 折叠露营椅 | 051] | 527 |  |
| foldng chars for outside | 户外折叠掎 | 051 | 5231 |  |
| owersized campig char | 超大露营椅 | 050哟 | 513 |  |
| Iawn chars loldng | 草坪椅折叠 | 047 | 481 |  |
| comfortable foldng char | 舒适的折叠椅 | 045 | 465 |  |
| X | 竞品出单词.Xlsx |  |  |  |
BOCRIGCIF2
Title:
Orersized Cami ne Chair, Fortable Foldi w Cami D Chairs Tth Side Focket
Duty_Outdoor_Campin_Chairs _[orNdults,Fi shi 卫r_Sports,Trip,up_to_4001b3
Bullet Foint :
Extremely Comfortable: Qur camping chairs for adults heawy duty, designed with ergonomic principles; faature spaclous seats thunfoldad dimansions Of 40.5" L* 28" IW 《39" H.The Camping Folding Chair is filled tith high-loft high-density padding In areas suchas the headrast, backrest, armrests, and seat cushion, providing ample space and support for your head, neck, back, waist and hips。
This ensures a comfortable experience even durlng prolonged sitting
Sturdy and Enduring: Our camping chalrs conslst of a robust steel frame and newly upgraded support components; with a welightcapacity of up to 400 pounds. The powder-coated flnish on the steel frame_effectaly pravents corrosion and fading. Additionally, the GOOD tear-resistant Oxford fabric is tightly stitched and highly breathable. Therefore, the Folding Camping Chair wll remain stable。 allowng for long-term Use
User-Friendly Details: For added convaniance, We inganlously designed 2 cup holders and 2 slde pockets on thls folding chair; allowing you to place baverages, smartphonas, notebooks, and other itams in an organizad manner This thoughtful dasign alms toprovide VOU with the best seating axperience hile freelng u your hands
Lightaight and Portabla: This portable folding chair raqulras no assembly and can be opanad for usa Within saconds. Tha Outdoorfolding chair i lighteight at only 12.6 pounds, making it axramaly easy t0 carry. The compact structure of the camp chair allows foreasy folding and storage in the provided portable carrying bag after flshing or any Outdoor actlvity
Versatile Applications: This folding lawn chalr for adults Is not only suitable for hlking, camping, and hking actiities but Is also perfectfor outdoor concarts, open-air movia nights; plcnics, or for Use at homg. The unlversality of the folding camping chair for adults makesi an Ideal seating choice forvarlous occasions
Modern Appearance: The foldable chair not only axcels In functionality butalso boasts a sleak modern appearance. Maticulously coordinaated colors makethe portable chalr a fashionable accessory for utdoor actlvitiies; adding atouch Of brilliance t0 Vour camping gear BORJ R2 3C5
Title:
Oersized Campi ne Chairs [0r dults
Cooler Fockels [or_Qulsi de_Sports Beach Fishi 1 Carden Fortable Supports 5OOLbs, Black
Bullet Point:
Owersized Padded Comfort 一mult-layer high-density padding. Ergonomic lumbarlneck support and padded headrest deliver al-day comfort:
Heaw-Duty Steel Frame
Supports up to 50OIbs for long-lasting durability. Non-slip texured feet ensure a stable seating experiance for everyone。
Extra Storage Spacainsulated cooler bag. Perfactly storas drinks, snacks; and phones within easy reach. I a versatila cholce for comfortabla paddedcamping chair for adults。
Hll-Waatherfabric and reinforced stitching to pravent fraying. Ideal for camping, sporting avents; barbecues, fishing, hiklng, backyard law use。 and more Outdoor adwentures。
Portable & Quick Setup 一home use. The compact structure of our lightwalght beach chairs allow for easy folding and storage in the carrying ba9 after anyoutdoor actiity. BITBY8L2
Title:
Oersized 讧 Catpi 1 Chairs [Or Aults HaVy Duty Suppott 500 Ibs Qutdoor Folding Chaits Padded Portable
Iam_Chairs_Cam_Chairsw th_Cup_HLder
Bullet Foi nt :
Comfortable Camping Chair: The camping folding chair Is flled with cotton padding in areas such as the headrest, backrest, armrests。 and seat cushlon, providing great space and support for your head, neck, back; walst, and hips. Allowing yOU t relaxand stretch outengures a comfortabla axparience during long timg sitting. Qur oversized comfy folding chair faature spacious s8ats and fine datailswth unfolded dimansions of 38.5"L|23"W #40"H X
| 谥量词 | 关键词翻译 | AC推荏词 | 谥蠡比 | 预估周曝,量 |
| --- | --- | --- | --- | --- |
| campng chars | 2365 | 2037 |  |  |
| 骥誓椅孑 |  |  |  |  |
| Owersized char | 23.26 | 1713 |  |  |
| foldng char | 折叠椅 | 509 | 375 |  |
| hammock campng char | 465K | 343 |  |  |
| campng chars heayy duly | r哺 | 442驹 | 326 |  |
| campng Chars loraduls | 34[ | 255 |  |  |  |
| camp Char | 营椅 | 288 | 212 |  |
| Owersized campng char | 超大露萱椅 | 239 | 176 |  |
| padded foldng chars | 223 | 164 |  |  |
| coleman camp ng Chars | 185 | 1361 |  |  |
| camp chars for adults | 178 | 131 |  |  |
| Char | 撺 |  |  |  |
| paddedl ceonomg | 136 | 128 |  |  |
| carp chars lor aduls heawy du_ | 159 | 1I7 |  |  |
| heayy duly campng chars | 144 | 1OBI |  |  |
| comfy campng char | 136 | 100 |  |  |  |
| camp Chars | 133 | 驵 |  |  |
| Oyersized campng chars lorad | 128 | 94 |  |  |
| 蠹 |  |  |  |  |
| belmonchota | 19 | 8 |  |  |
| foldng campng chars | 111 | 81 |  |  |
| campng couch for aduls | 106 | 78 |  |  |
| yeli Ichar | 雪人椅 | 080哟 | 59 |
| padded folding cha | 软垫折叠椅 | 065g | 48 |  |
| heavy duty foldng char | 重型折叠椅 | 065 | 4 |  |
| comfortable foldng char | 舒适的折叠椅 | 059 | 44 |  |
| rockng law char | 摇摆草坪椅 | 045 | 33 |  |
| foldab 1 char | 折叠椅 | 044 | 32 |  |
| char campng | 040 | 29 |  |  |
| silla campng | 036 | 26 |  |  |
| < |  |  |  |  |
| outdoor campng chars | 026 | 19 |  |  |
| foldng chars Iopack | 025 | 1 |  |  |
| reclining camping chai | 躺椅 | 021 | 15 |  |
| Jce fishng char | 013 | 9 |  |  |
| campng char | x5 | 00躺 | B |  |
| foldng lawn char | 004 | 3 |  |  |
| heawy duty char | 002 |  |  |  |
| 』 |  |  |  |  |
| sorts char | 002 |  |  |  |
| outdoor foldng chars | 002 |  |  |  |
| campng char wirh canopy | '噩 | 002 |  |  |
| sorts Chars lor adults | 001 |  |  |  |
| foldngchar padded | 折叠椅软垫 | 001 |  |  |
| foldng campng char | 折叠露萱掎 | 001 |  |  |
| Ioldab le campng chars | 00Oy |  |  |  |
| 莱-犄 |  |  |  |  |
| rodng campmhacharstoradul | O00w |  |  |  |  |
| 成人摇摆露营椅 |  |  |  |  |
| heavy duty folding chars | 00Cy |  |  |  |
| campng rockng chai | 嚣= | 000y |  |  |
| rocking camp char | 00Cy |  |  |  |
| X | 关键词.Xlsx |  |  |  |
| 款写 | 5ku编码 | 产品名称 | 解#方案 |
| --- | --- | --- | --- |
| 12508 | }2508_盯 ACT CHE' | owersized Cami 1 Chair 家居系统 |  |
| X | 本品属性表1.XlsX |  |  |
| 2.知识库文件:  亚马逊禁用词黑名单 |  |  |  |
| 此文档包含亚马逊严禁{标题 Iitle) 。 五点描述IBullets) . | 产品描述 [Description] 皮后台搜索词 |  |  |  |  |
| --- | --- | --- | --- | --- | --- |
| ISeach Terns]f出珧的词汇与表达。 |  |  |  |  |  |
| 一 | 促销与芏观评价类 (Fromotional & Subjective Claimsl |  |  |  |  |
| 亚马逊规定 Listing 必颏是对产品的客观描述。禁止包含任何促销信息或无法证实的主观评怵。 |  |  |  |  |  |
| [严禁出珧]: |  |  |  |  |  |
| C | Bcst seler; Top Iated, Best selline; #1 (最畅销 | 排名笫-) |  |  |  |  |
| = | Hot iem, Fopllar Chnice (爆款1 |  |  |  |  |
|  | Fr8C shipping; FreC deliver { 包邮) |  |  |  |  |
| C | FrCC Ei, Bonlls, Cift ichded (赠品] |  |  |  |  |
| 一 | On sale; Discount, x%6 0f; Bcst price, Lowest price, Cleap (促销打折{低价] |  |  |  |  |
| 一 | Satisfaction [llarantec; LOOMi Quality, Money back (黼意度保证'退款保证) |  |  |  |  |
|  | Order IOI, Buy DO (诱导购买动词 |  |  |  |  |
| a | Amazon's Choice; Certifed [官方认证词] |  |  |  |  |
|  | 知识产杈与品牌兼容性 (Intellectlual Fropeity) |  |  |  |  |
| 严禁末经授权使用他人的府标。品牌名。 |  |  |  |  |  |
| [严禁出珧]: |  |  |  |  |  |
| 任何非本产品的品牌名称 (如: Nic; Disney, Applc; LEBO, Telcro 等). |  |  |  |  |  |
| 一 | Velcro (维可牢{魔术贴:必领改为 "Iook and luop" |  |  |  |  |
| = | Onesie {连体衣:_必领改为 "bodysuit" 或 "romper" |  |  |  |  |
| a | Hula Hoop [呼咄圈:  必领改为 | "tov | Icop" |  |  |
| a | Chapstick (润屑膏:  必领改为 "lip balm" - |  |  |  |  |
| - Q-tip [棉签}:  必颈改为 "cotton Swab" - |  |  |  |  |  |
| = | Fopsicle (冰棍):  必颈改为 "ice pop" |  |  |  |  |
| [配卅兼容性正确写滋]: |  |  |  |  |  |
| 错误写迭: "[Brand Name] Casc" {例如 vhone 15 Case) -> 会被判寇为侵杈。 |  |  |  |  |  |
|  | 正确写祛: "Case Compatible with [rand Lame]" 或 "Casc Rr [Brand Iame]"一 |  |  |  |  |
| = | 注意:  品牌名之前必颏有 "compatible sith " 或 "for"。 |  |  |  |  |
| 三。 匮疗器械与功效撖感词 [edical & Health Claims] |  |  |  |  |  |
| 非OTC 药品或耒获得}4讥证的医器械。严禁睛示治疗。预防或治愈蒺病的功能。 |  |  |  |  |  |
| [严禁出珧]: |  |  |  |  |  |
|  | Cure; Heal, Treal;, Treatment; Remedy (治;愈'治疗法] |  |  |  |  |
|  | Frewent; Frerention (预防) |  |  |  |  |
|  | Relief; Relicr; | Stop | ' Pain {止痛}缓解 | a | 除非是合规 OIC] |
| : | Mnti-rirls; Ainti-flu, Anti-inflammator [抗病毒[消炎] |  |  |  |  |
| 一 | RA approved, 印D4 cleared (除非有真实证书升已备案。否则严禁使用] |  |  |  |  |
|  | 褴及具忡病症名称: Cancer; Diabetes; thritis 等。 |  |  |  |  |
| 凹。。杀虫剂与生物杀灭剂撖感词 [Pesticide & Biocides} |  |  |  |  |  |
| 这是亚马逊最窄易误杀的重灾区。任何艄示能 "杀灭。驱除。抑剁"  生物 {细菌。霹菌。昆虫 |  |  |  |  |  |
| 的词。都会被判定为杀虫剂。肃要 B』 注册写 |  |  |  |  |  |
| [严禁出现 (除非你有 EPA 写) ]: |  |  |  |  |  |
| : | Anti-bacterial, Anti-microbial [抗菌航微生物] |  |  |  |  |
|  | Anti-funBal, Wold Iesistant (抗:菌防'爵] |  |  |  |  |
| = | Anti-dust mite {防尘螨) |  |  |  |  |
|  | Insect Iepcllent BuB stop (驱蚊'防虫 |  |  |  |  |
| 一 | Disinfect; Sanitize;, Sterilize [消毒{杀菡] |  |  |  |  |
| 一 | Non-toxic (无莓}:  椴易触岌审核。建设改为 "B4 Frec" 或 "Safe material"- |  |  |  |  |
| = | Safe, Healthy, Harmless (绝对化安全用语) |  |  |  |  |
| amazon_compliance_blacklist:txt |  |  |  |  |  |