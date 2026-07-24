
---
**第 1 页**
---

创建Gems智能体SOP
—— Rufus / COSMO / A9 三算法 Listing 智能体
一、SOP 目标定义（不可省略）
1️⃣ 业务目标（唯一）
自动生成一份：
•
符合 Amazon 合规要求
•
能被 A9（搜索）完整收录
•
能被 COSMO（场景理解）正确识别
•
能被 Rufus（事实检索）准确引用
的【可直接上架】Listing 文案
二、Gems 结构总览（标准）
一个完整 Gem = 4 个模块：
1. 名称
2. 说明
3. 指令（核心）
4. 知识库（合规约束）
三、具体搭建 SOP（逐步执行）
STEP 1｜新建 Gem
路径：
Gemini → Gems 管理器 → 新建 Gem

---
**第 2 页**
---

STEP 2｜名称与说明（照填）
✅ 名称（示例）
```
AMZ那些事｜亚马逊 Listing 撰写专家（A9 / COSMO / Rufus）
名称仅用于识别，不影响执行逻辑
```
✅ 说明（必须精确）
```
请在当前对话框中上传以下 4 个文件：
1️⃣ 竞品出单词报告.csv  
2️⃣ ABA关键词数据.csv  
3️⃣ 竞品Listing文本.txt  
4️⃣ 本品属性表.txt  
我将结合知识库中的合规红线，基于 A9（搜索）、COSMO（意图）和 Rufus（推荐）算法为您生成
Listing。
```
STEP 3｜核心指令（Instructions）【直接可用】
🔧【Gems 核心指令全文】
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
1
1
2
3
4
5
6
1
2
3
4
5
6
7

---
**第 3 页**
---

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
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46

---
**第 4 页**
---

请直接输出：
1. **Title**
2. **5 Bullet Points**
3. **Product Description** (含HTML代码)
4. **Search Terms**
5. **竞品分析洞察：** (简短总结：你发现了这几个竞品有什么共同弱点？我们的Listing是如何针
对性优化的？)
```
STEP 4｜知识库（Knowledge）配置 SOP
✅ 必须配置（这是“紧箍咒”）
1️⃣ 新建文档
•
文件名：
```
amazon_compliance_blacklist.txt
2️⃣ 文档内容
•
粘贴你文件中提到的
《亚马逊 Listing 合规性与违禁词速查表》正文
3️⃣ 上传路径
Gems → Knowledge → “+” → 上传 txt 文件
```
四、标准运行 SOP
1️⃣ 上传 4 个指定文件
2️⃣ 确认文件齐全
3️⃣ 直接提交
⛔ 不要换说法
⛔ 不要追加聊天式指令
47
48
49
50
51
52
1

---
**第 5 页**
---

五、SOP 成功判定标准
一份合格输出，必须满足：
•
Rufus 可检索到全部参数
•
A9 关键词自然嵌入
•
COSMO 能识别清晰使用场景
•
无任何违规或“AI味”营销词
参考文档附件：
1.竞品出单词，竞品listing，本品属性表，ABA关键出单词

---
**第 6 页**
---

| 流量词 | 关键词翻译 | 戌C推荐词 | 流量占比 | 预怙周曝光量 |
|---|---|---|---|---|
| camp ng chars | 露营椅 | 20.18 | 20843 |  |
| b8ach char | 沙滩掎 | 1453 | 15070 |  |
| Ouldoor chars | 户外掎 | 890骑 | 9.191 |  |
| campng char | 露营椅 | 765 | 7899 |  |
| bwn Chafs | 草坪椅 | 5.15 | 5323 |  |
| ouldoor char | 户外椅 | 355 | 3665 |  |
| gci rocker char | 9c摇椅 | 291 | 3 002 |  |
| campng chars lor adults | 成人露营椅 | 2& | 2980 |  |
| foldng | char | 折叠椅 | 2.16 | 2233 |
| bmn char | 草坪掎 | 209 | 2.162 |  |
| portable char | 便携掎 | 166 | 1.71 |  |
| foldab 1e char | 折叠椅 | 157驹 | 1622 |  |
| portable chars lor adulls | 成人便携式椅子 | 138 | 1425 |  |
| foldng chars | 折叠椅 | 131 | 1355 |  |
| carmp chars | 露营掎 | 128 | 1321 |  |
| camp chars lor adults | 成 人露营椅 | 1.11 | 1.148 |  |
| cammp char | 营椅 | 110 | 1.140 |  |
| campig chars heay duly | 重型野营椅 | 098 | 1013 |  |
| Outside Chars | 外面的椅子 | 0899 | 919 |  |
| heawy duty loldng char | 重型折叠椅 | 068 | 705 |  |
| yeti | char | 雪人椅 | 065 | 670 |
| fishng char | 钓鱼掎 | 061 | 626 |  |
| chars lor outside | 户外椅子 | 059 | G07 |  |
| sorts char | 运动椅 | 053 | 549 |  |
| foldng | camp char | 折叠露营椅 | 051驹 | 527 |
| foldng chars for outside | 户外折叠掎 | 051~ | 523 |  |
| 回 | wersiz8d campng char | 超大露营椅 | 050 | 513 |
| bw Chars |  folding | 草坪掎折叠 | 047 | 481 |
| comfortab le loldng char | 舒适的折叠椅 | 045 | 465 |  |
| X | 竞品出单词.Xlsx |  |  |  |

---
**第 7 页**
---

EOCRIGCIE2
IitE:
Cjersized Campi ng Chair, Dt
Bullet
Extremely Comfortable: Qur camping chairs for adults heawy duty, designed mith ergonomic principles; feature spacious seats Iithunfolded dimansions Of 40.5" L K 28" I &39" H.Tha Camping Folding Chair is fllad tith high-loft; hlgh-dansity padding In areas such88 the headrest, backregt, armregts, and s8at Cushlon, providing ampla space and gupport for your head, nack, back; aist; and hips。
This ensures a comfortable experlence even during prolonged sitting
Sturdy and Enduring: Qur camping chairs consist of a robust staal frame and nawly upgraded support components。 with a Ialghtcapacity of up to 400 pounds. The powdar-coatad finish on the staal frame effectlvaly prevants corroslon and fading. Additionally; the GOOD taar-resistant Oxord fabric 1s tightly stitched and highy breathabla. Tharefore, the Folding Camping Chair wll remain stable。 alowlng for long-term Use
User-Friendly Details: For added conenlence, We Ingenlously dasigned 2 cup holders and 2 slde pockets on this folding chair,allowing you to place boverages; smartphones, notebooks; and other itams in an organizgd manner This thoughtful dosign aims tprovide VOU tith the best saatlng experiance thile freelng Wp your hands
Llghtwalght and Portable: This portable folding chair requlras no assembly and can be opened for usa within saconds. The Outdoorfolding chair 1 lighteight at only 12.6 pounds, making it extramaly easy t0 carry. The compact structure of the camp chair allows foreagy folding and storage in the provided portabla carring bag after fishing orany outdoor activity
Versatile Applications: This folding Iawm chalr for adults Is not only suitable forfor outdoor concerts, open-air movle nights; picnics, Or for Use at hord. The universality of the folding camping chair for adults makesian Ideal seating choice for various occaslons
Modern Appearance: The foldable chair not onl ekcels in functiionality butals0 boasts 8 Slaak modern appearance. Waticuloushy coordinaatad colors makethe portable chair a fashionable accessory for outdoor activitiies, adding atouch of brilllance t your camping gear BOPJR 貂[5
Title:
Cjersized Canpi n Chairs [or
Cooler
Bullet
Owersized Padded Comfortmulti-layer high-density padding. Ergonomic lumbarlneck support and padded headrost daliver alH-day comfort。
Haawy-Duty Stael Frame
Supports Up to 500lbs for long-asting durability. Non-slip txurad faet ensure a stable saating exparience for averyona。
Extra Storaga Spaceinsulatad coolar hag. Perfactly storeg drinks, snacks, and phones within 8asy reach。 I a wersatila choice for comfortabla paddadcamping chair for adults。
All-Waather Durability - fabric and rainforced stitchlng to prevent fraying. Ieal for camping, sporting events; barbecues; fishing, hiking, backyard Iaw use; and more Outdoor adwentures。
Portable & Quick Setuphomg use. The compact structure of our lightwalght beach chairs allow for easy folding and storage In tha carrlng ba9 aftar any
Outdoor actlity。 BIB78L
Title:
Csersized .讧 Campi JB Chairs [0r
Lam Chairs Camp Chair5
Bullet
Comfortable Camping Chair: The camping folding chair Is filled with cotton padding in areas such a5 the headrest, backrest, armrests。 and seat cushlon, prowiding great space and support for your head, neck, back。 Walst, and hips. Allowing VOU to relak and stratch outensures 8 comfortabla experience during long timg sitting. Qur Owersized Comfy folding chair faature apaclous s8at and fine datallsth unfolded dimenglons of 38.5"匕鬣23"4 *40"H X

---
**第 8 页**
---

| 谥量词 | 苤键词翻译 | 亘推萑词 | 谥量占比 | 预估周曝,量 |
|---|---|---|---|---|
| campng chars | 露营椅 | 2765 | 2037 |  |
| Owersized char | 特大号椅子 | 2326 | 1.313 |  |
| loldng char | 折叠椅  | 509 | 375 |  |
| hammock camp ng char | 吊床露营椅 | 465 | 343 |  |
| campng chars hea y duty | 重型野营椅 | 442 | 326 |  |
| camp ng chars foradults | 成人露营椅 | 346 | 255 |  |
| camp char | 营椅 | 28 | 212 |  |
| Owerslzed campng char | 超大露营椅 | 239 | 176 |  |
| padded foldng chars | 软垫折叠椅 | 223 | 164 |  |
| coleman campng chars | 科尔曼露营椅 | 185 | 136 |  |
| camp chars lor adults | 咸人露营椅 | 1.J8 | 131 |  |
| padded campng char | 带衬垫的露营椅 | 1孑1骑 | 126 |  |
| campng Couch | 露营沙发 | 166g | 122 |  |
| camp Chars for aduls heavy du 成 人重型露营椅 | 159 | 113 |  |  |
| heawy duty campng chars | 重型野营椅 | 144- | 106 |  |
| comfy campng char | 舒适的露营椅 | 136 | 100 |  |
| camp chars | 露营椅 | 133 | 鸵 |  |
| oversized campng chars lor ad 成人超大露营椅 | 128 | 94 |  |  |
| helno   char | 海利诺克斯椅 | 121 | 8 |  |
| camp ng 50怕 | 野营沙发 | 119 | 8 |  |
| foldng campng chars | 折叠式野营椅  | 1.11 | 81 |  |
| campng Couch lor aduls | 成人露营沙发 | 106 | 7 |  |
| yeti | char | 雪人椅  | 080驹 | 59 |
| padded foldng char | 软垫折叠椅 | 065驹 | 4 |  |
| heaw duty loldng char | 重型折叠椅 | 065 | 4 |  |
| comfortab le loldng char | 舒适的折叠椅 | 059 | 44 |  |
| rockng Ias char | 摇摆草坪掎 | 0454 | 33 |  |
| loldable char | 折叠椅 | 044 | 32 |  |
| char campng | 椅子露营 | 040 | 29 |  |
| silla campng | 露营椅 | 036驹 | 26 |  |
| Outdoor campng chars | 户外露营椅 | 026 | 19 |  |
| foldng chars 10pack | 折叠椅10包 | 0254 | 18 |  |
| reclnng campng char | 躺椅 | 021 | 15 |  |
| ice fishng char | 冰钓椅 | 0.13 | 9 |  |
| campng char | 露营椅 | 009 | 6 |  |
| loldng law char | 折叠草坪椅 | 004 | 3 |  |
| heaw | duly | char | 重型椅子 | 002 |
| 卯Orts char | 适动掎_ | 002 |  |  |
| outdoor foldng chars | 户外折叠椅 | 002 |  |  |
| campng char t canopy | 带顶篷的露营椅 | 002 |  |  |
| SOrts chars lor adults | 成人适动椅 | 001 |  |  |
| loldng char padded | 折叠掎软垫 | 001 |  |  |
| foldng camp ng char | 折叠露营椅 | 001驹 |  |  |
| loldab b camp ng chars | 可折叠露菖椅 | 0 0Oy |  |  |
| foldng camp char | 折叠露营椅 | 000g |  |  |
| rocking camping chars for adul 咸人播摆露瞢掎 | 0 0Oy | ; |  |  |
| heayy duty loldng chars | 重型折叠椅 | 0 0Oy |  |  |
| campng rockng char | 露营摇椅 | 000N |  |  |
| rockng camp char | 摇椅 | 0 0Oy |  |  |
| X | 关键词.Xlsx |  |  |  |

---
**第 9 页**
---

| 款写 | 5k编码 | 产品名称 | 解#方案 |
|---|---|---|---|
| r2508 | KC2508_耻tH CHR' | oyersized Cami nB  Chair 家居系统 |  |
| 义 | 本品属性表1.XlsX |  |  |
| 2.知识库文件:  亚马逊禁用词黑名单 |  |  |  |

---
**第 10 页**
---

此穴档包名亚马逊严禁在标题(Title} _
Iearch Terms] t出的词汇与表达。 '亚马逊规寇 ListinE 必领是肘产品的客观描述。禁止包含任何促销借息或无法证实的芏观评份。
[严禁出珧]:
Best seller; Top rated, Best selling。 #1 (最畅销排名笫一」
Hnt iem Rollar chnice (爆颛]
FreC shippinB; FreC delinry [ 包邮]
RreC E, Bonlls, Cift mchuded (赠品] On sale; Discount;   Off; Best price; Lofest price; Cleap (促销打折低价]
Satisfaction [llarantec; LOR Quality; Iotey back: (鞲意度保证;退颛保证
Orer Don; Bl Do (诱导购买动词]
MmlazoT's Choice; Certifed [官方认证词知识产杈与品牌蒗容性 [Intellectulal Fropeityl严禁末经授杈使用他人的商标。品牌名。
[严禁出珧]: 任何非本产品的品牌名称 (如: Ie; Disnei, 』pp匕;
Tplcro (维可牢魔术  必?改为 "llnnki ad lacp


Clapstick: (鞠唇育}:  必领改为 "Iip balm"
- Q-t [棉簋]:  必瓴改为 "cotton 5rab" _

[配件兼容性正确写迭]: 错误写法: 正确写祛: "Case Compatible with [Brand Lame]注意:  品牌名之前必狈有 "compatible nith" 或 "[or"三_非 OIC 药品或末获得}认证的医疗器械。严禁暗示治疗。预防或治愈犊病的功能。
[严禁出珧]:
Culre; Heal, Treat, Treatment; Remedy [浒愈'治疗{疗'法]
Frerent; Frerention (预防」

unti-ritlls; mnti-flu Mnti-inflammatoni (抗痴毒}消览]

褴度其体犄症名称: Cancer, Diabctes; Jthritis 等。
四. 这是亚马逊最窄易误杀的重灾区。任何暗示能 "亲灭。驱除。抑`"  生物 (细菌。霹菡。昆虫的词。都会被判定为杀虫剂。}要E$注册写。
[严禁出珧 {除非你有 EPl号 ]:
Snti-bacterial, Mnti-microbial [抗菌;抗微生物]
Jnti-flngal, Uold Iesistant (抗霹菡{防:]
Snti-dust mite {防尘螨]
Inscct IeDIlent
Disinfect; Sanitize, Sterilize (诮毒{粱菌] Lo-toric (无毒}:  披易触岌审核。建议旋为 "B8 FreC" 或 "Safe material"
Safe; Hcaltlff HaImless [绝衬化安全用语]amazon_compliance_blacklist.txt