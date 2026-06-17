
---
**第 1 页**
---

创建Gems智能体SOP​
—— Rufus / COSMO / A9 三算法 Listing 智能体​
一、SOP 目标定义（不可省略）​
1️⃣ 业务目标（唯一）​
自动生成一份：
•
符合 Amazon 合规要求​
•
能被 A9（搜索）完整收录​
•
能被 COSMO（场景理解）正确识别​
•
能被 Rufus（事实检索）准确引用​
的【可直接上架】Listing 文案
二、Gems 结构总览（标准）​
一个完整 Gem = 4 个模块：​
1. 名称
2. 说明
3. 指令（核心）
4. 知识库（合规约束）
三、具体搭建 SOP（逐步执行）​
STEP 1｜新建 Gem​
路径：
Gemini → Gems 管理器 → 新建 Gem​


---
**第 2 页**
---

STEP 2｜名称与说明（照填）​
✅ 名称（示例）​
代码块​
AMZ那些事｜亚马逊 Listing 撰写专家（A9 / COSMO / Rufus）
名称仅用于识别，不影响执行逻辑
✅ 说明（必须精确）​
代码块​
请在当前对话框中上传以下 4 个文件：
1️⃣ 竞品出单词报告.csv  
2️⃣ ABA关键词数据.csv  
3️⃣ 竞品Listing文本.txt  
4️⃣ 本品属性表.txt  
我将结合知识库中的合规红线，基于 A9（搜索）、COSMO（意图）和 Rufus（推荐）算法为您生成
Listing。
STEP 3｜核心指令（Instructions）【直接可用】​
🔧【Gems 核心指令全文】​
代码块​
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
STEP 4｜知识库（Knowledge）配置 SOP​
✅ 必须配置（这是“紧箍咒”）​
1️⃣ 新建文档​
•
文件名：
代码块​
amazon_compliance_blacklist.txt
2️⃣ 文档内容​
•
粘贴你文件中提到的
《亚马逊 Listing 合规性与违禁词速查表》正文​
3️⃣ 上传路径​
Gems → Knowledge → “+” → 上传 txt 文件​
四、标准运行 SOP​
1️⃣ 上传 4 个指定文件​
2️⃣ 确认文件齐全​
3️⃣ 直接提交​
⛔ 不要换说法​
⛔ 不要追加聊天式指令​
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

五、SOP 成功判定标准​
一份合格输出，必须满足：
•
Rufus 可检索到全部参数​
•
A9 关键词自然嵌入​
•
COSMO 能识别清晰使用场景​
•
无任何违规或“AI味”营销词​
参考文档附件：
1.竞品出单词，竞品listing，本品属性表，ABA关键出单词​


---
**第 6 页**
---

| 流量词 | 关键词翻译 | AC推荐词 | 流量占比 | 预估周曝光量 |  |  |
|---|---|---|---|---|---|---|
| campog Char5 | 露营椅 | 20.18药 | 20843 |  |  |  |
| b89ch char | 沙滩椅 | 1455 | 15070 |  |  |  |
| Duldoor chars | 户外椅 | &9 | 9.191 |  |  |  |
| campg chav | 露营椅 | 765 | 7899 |  |  |  |
| Iaw Chars | 草坪椅 | 5.15 | 5323 |  |  |  |
| Gutdoor char | 户外椅 | 355 | 3665 |  |  |  |
| goi | rocker char | 9c摇椅 | 291 | 3002 |  |  |
| camp 49 chays Ior adylis | 成人露营椅 | 288 | 2580 |  |  |  |
| foldig cha[ | 折叠椅 | 2.16 | 2233 |  |  |  |
| lawn char | 草坪椅 | 209 | 2.162 |  |  |  |
| portab le cha | 便携椅 | 166 | 1318 |  |  |  |
| flable Char | 折叠椅 | 157 | 1622 |  |  |  |
| portab le chars tor aduls | 成人便携式椅子 | 138 | 1425 |  |  |  |
| d旧 | ng | hs5 | 折叠椅 | 131 | 1 | 355 |
| camp chars | 露营椅 | 128 | 1321 |  |  |  |
| camp chaTs Ior aduls | 成 人露营椅 | 1.11纺 | 1148 |  |  |  |
| camp char | 营椅 | 11 | 1.140 |  |  |  |
| campng chars heayy | Uuiy | 重型野营椅 | 058 | 1013 |  |  |
| Gutsde chacs | 外面的掎子 | 085 | 919 |  |  |  |
| heawy duty tol | ldng | char | 重型折叠椅 | 068 | 305 |  |
| yeli | 2ha | 雪人椅 | 065 | 670 |  |  |
| s | Ig | char | 钧鱼椅 | 061N | 626 |  |
| Chars lor Gutslde | 户外椅于 | 059 | 60? |  |  |  |
| sorts char | 运动掎 | 0537 | 549 |  |  |  |
| foldng camp char | 折叠:营椅 | 051驵 | 52? |  |  |  |
| l旧 | ng | chars lor Gutslde | 户外折叠椅 | 051 | 523 |  |
| 回 | Versized campig char | 超大露菅椅 | 050 | 513 |  |  |
| lawn chars lo | long | 草坪掎折叠 | 047 | 41 |  |  |
| Comlorta le lo | Idng | cha | 舒适的折叠椅 | 045 | 465 |  |
| 竞品出单词.XlsX |  |  |  |  |  |  |

---
**第 7 页**
---

BCRIGCIR2
Tit1巳:
Cier5ied
Dl :
Bul le [
Extremely Comfortable: Our camping chairs for adults heavy duty。 designed with ergonomic principles, feature spacious seats with
unfolded dimensions Of 40.5" L %28" I &39" H The Camping Folding Chair is filled with high-loft high-density padding in areas such
95 the headrest, backrest, armrests, and seat cushion prowiding ample space and support for yourhead, neck, back, waist; and hips。
This ensures
Sturdy and Enduring: Qur camping chairs consist of a robust steel frame and newly upgraded support components; with a eight
capacity of up to 400 pounds. The powder-coated finish on the steel frame effectively prevents corrosion and fading. Additionally。 the
GOODtear-resistant Oxford fabric is tightly stitched and highly breathable. Therefore。 the Folding Camping Chair will remain stable。
allowing for long-term Use
User-Friendly Details: For added convenience, W ingeniously designed 2 Cup holders and 2 side pockets on this folding chair
allowing you to place bewerages, smartphones, notebooks, and other items in an organized manner。 This thoughtful design aims t0
prowide yOU with the best seating experience while freeing up your hands
Lightweight and Portable: This portable folding chair requires no assembly and can be opened for USe within Seconds_
folding chair is lightweight at only 12.6 pounds, making i extremely eagy to carry. The compact structure of the camp Chair allos for
easy folding and storage in the prowided portable carrying bag after fishing or any outdoor activity
Versatile Applications: This folding lawn chair for adults is not only suitable for hiking; camping, and hiking activities but is also perfect
for outdoor concerts, open-air movie nights; picnics, Orfor use at home
i an ideal seating choice for Various Occasions
luodern Appearance: The foldable chair not only eaCels in functiionality but
als0 boasts a sleek modern appearance  Meticulously Coordinaated colors make
the portable chair a fashionable accessory for outdoor activitiies。 adding a
touch of brilliance to our camping gear
BOPJ P2  [5
Ti t]e;
Cier5ized
Codler
Bul Iet
Oyersized Padded Comfort
multi-layer high-density padding  Ergonomic lumbarineck support and padded headrest deliver all-day comfort。
Heawy-Duty Steel Frame
Supports Up to 5OOlbs for long-lasting durability. Non-slip texured feet ensure a stable seating experience for ewveryone。
Extra Storage Space
insulated cooler
camping chair foradults
All-Weather Durability
fabric and reinforced
and more outdooradentures。
Portable & Quick Setup
home Uge_
outdoor actiwity。
BDTBZ8LZ
Tit1巳:
Cer5ized
Lum Chair5
Bul let
Comfortable Camping Chair: The camping folding chair is filled with cotton padding in areas such as the headrest, backrest。 armrests。
and seat cUshion, prowiding great space and support for your head。 neck, back。 waist。 and hips. Allowing yOU to relaland stretch out
ensures a Comfortable experience during long time sitting Our Owersized comfy folding chair feature spacious seats and fine details
nt unfolded dimensions of 38.5"匕~23"V !40"H
竞品listingcamping chair.xlsx

---
**第 8 页**
---

| 谥量词 | 关键词翻译 | 6推荐词 | 流量占比 | 预u魑 |  |
|---|---|---|---|---|---|
| camp ng chars | 露营椅 | 2365 | 2033 |  |  |
| OVersled Char | 特大号掎子 | 2326 | 1313 |  |  |
| IoI | ng | char | 折叠椅 | 509 | 335 |
| hammoc camp ng char | 吊床露营椅 | 465N | 343 |  |  |
| Cammp | ng | Chars heayy duty | 重型野营椅 | 442纺 | 326 |
| Damp | ng | chars lor adults | 成人露营掎 | 346 | 255 |
| cam Dha | 菅椅 | 288 | 212 |  |  |
| Owers284 campng cha | 超大露营椅 | 239 | 176 |  |  |
| Dadded loldmg chars | 软垫折叠椅 | 223 | 164 |  |  |
| coleman campmg chars | 科尔曼露菅椅 | 185 | 136 |  |  |
| camp chars loradults | 成人:营椅 | 1.38 | 131 |  |  |
| Padded campmg char | 带衬垫的露营椅 | 1.31 | 126 |  |  |
| cam | ng | CoUch | 露营沙发 | 166 | 122 |
| CSP chars for aduls heayy du 成人重型露营椅 | 159 | 113 |  |  |  |
| heawy duly campng chars | 重型野营椅 | 144 | 106 |  |  |
| comly campng char | 舒适的露营椅 | 136 | 10 |  |  |
| camp chars | 露营椅 | 133 | g |  |  |
| 0 | Versiz8d Campig chats lorad 成 人超大:营椅 | 128 | 94 |  |  |
| hel6翼 char | 海利诺克斯椅 | 121 | 89 |  |  |
| campng 5f | 野营沙发 | 119 | 8 |  |  |
| Ioldng campmg chars | 折叠式野菅椅 | 1.11 | 81 |  |  |
| campng couch loradults | 成 人露营沙发 | 10E | 7 |  |  |
| yeli | chhs | 雪人椅 | 0804 | 59 |  |
| padded folding char | 软垫折叠椅 | 065 | 4 |  |  |
| neaw duty folding char | 重型折叠椅 | 065 | 4 |  |  |
| comlortab  | folding char | 舒适的折叠椅 | 059 | 44 |  |
| rockng lam char | 摇摆草坪椅 | 045 | 33 |  |  |
| fb9le char | 折叠椅 | 044 | 32 |  |  |
| Char campng | 椅子露菅 | 040 | 29 |  |  |
| s campg | 露营椅 | 036 | 26 |  |  |
| Outdoor campng chars | 户外露营椅 | 026 | 19 |  |  |
| loldng chars I0pac | 折叠椅10包 | 025 | 18 |  |  |
| reclnng campng chav | 躺椅 | 021 | 15 |  |  |
| Ie fishng char | 冰钧椅 | 0.13 |  |  |  |
| campng 叻旷 | 露营椅 | 005 |  |  |  |
| foldng law char | 折叠草坪椅 | 004 |  |  |  |
| heaw duty char | 重型掎子 | 002 |  |  |  |
| 卯Orts char | 适动椅 | 002 |  |  |  |
| Outdoor oldmng chars | 户外折叠掎 | 002驺 |  |  |  |
| campng char wth canopy | 带顶篷的露营椅 | 002 |  |  |  |
| m Orts chars Ior aduls | 成人运动掎 | 001驺 |  |  |  |
| Ioldmng char padded | 折叠椅软垫 | 001驵 |  |  |  |
| Iolding camping char | 折叠:营椅 | 001驺 |  |  |  |
| Ioldab l campng chars | 可折叠露菅椅 | 000 |  |  |  |
| folng camp char | 折叠露营椅 | 000N |  |  |  |
| rockng camping chars lor adul 成人摇摆露营椅 | 000 | ; |  |  |  |
| heawy duty loldng chars | 重型折叠椅 | 000N |  |  |  |
| campng roclng char | 露营摇椅 | 00iN |  |  |  |
| rockig camp char | 摇掎 | 000 | 0 |  |  |
| 关键词.XlsX |  |  |  |  |  |

---
**第 9 页**
---

| 款号 | 5压编码 | 产品名称 | 解{方案 |
|---|---|---|---|
| 12508 | 1C2508_巴 AC[ CPe | owersizcd Campi ne  Chair 家居系统 |  |
| X | 本品属性表1.XlsX |  |  |
| 2.知识库文件:  亚马逊禁用词黑名单 |  |  |  |

---
**第 10 页**
---

此穴档包刍亚马趾严禁在标题[itle] 一
ISearch Ters] 廿出珧的词汇与表。。
促销与主观评价类 [Pronntinnal 晨 Subjective {lainlsl
亚马逊规定 Listing 必颈是对产品的客观描迷。禁止包名任何促销倩息或无法证实的主观评价.
[严禁出珧:
Bcst scller; To Iated, Bcst sellilg; #1 {最畅销排名笫-1
Hot item Poplllar chnice [曝款]
Free shipping; Frec Jeliver [ 包邮1
FrcC Bf Bonlls, Cift mchded (赠品]
On Sale; Discount; !- Of; Best price; Lowest plice; Cheap ! 促销打折'低你]
Satisfaction Glarantee; LODN Cuality Ioner back (n意度保证|退款保证)
Orer Ion, Bllr I0y (诱守购买动词
J1a20['s Chnice; Celtifed [官方让证词
知识产杈与品牌兼"性 IIntellectllal Fropertr}
严禁未经授枳使用j人的商标。品牌名
[严禁出珧]:
任何非本产品的品牌名称 (如: Iilke; Disnex Apple;
Telcro (维可牢1魔-:  必狈改为
Onsie [连体衣]:
Hula Hoop [呼啦豳:  必领改为
Chapstick; (涸唇膏}:  必领改为 "I balm
Q-t (棉簋:  必领改为 "cotton 5Wab'
Ropsicle (冰棍]:  必瓴改为 "iCC p叩
[配件兼容性正确写法]:
错溟写逑:
正确写徒:
注意:  品牌名之前必瓴有
二
非 OIC 药品或未获将}认证的医疗器械
[严禁出珧1:
Clre; Heal, Treat Treatment, Remedy [治愈}治疗(疗祛]
Frevent, Frerentinl (3防1
Relief Relieve; Stop pain (止痈{缓解
Mnti-rirlls; Mnti-flu Mnti-inflammatary (抗瘸毒[消泷]
Rlaprorcd; R  Clearcd (陈非有真实证书#巳备案;
诎及具体病症名称:
四
这是亚马逊最"易误亲的重灾区。任何暗示能 *杀灭。驱除。抑制"  生物 (细菌。霹菡。
的词.
[严禁出珧 (除非你有 E写1
Iti-bacterial, mnti-microbial [抗菡抗徵生物]
Mnti-funBal, Uold Iesistant (抗霉菌{防霉]
Mnti-dust Iite (防尘蝤1
Insct Ipcllent BuB stop (驱蚊{防虫
Disinfect, Sanitize; Sterilize [消毒[亲劐]
Lnli-tonic {无毒:  裰易触岌审核
Safi Healthy, Hal1le55 {绝封化安垒用语1
amazon_compliance_blacklist txt