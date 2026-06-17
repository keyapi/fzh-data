
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

流量词
关键词翻译
AC推荐词
流量占比
预估周曝光量
campng chars
露营椅
20.18
20843|
beach char
沙滩椅
14599
15070
Outdoor chars
户外椅
8904
9191
campng char
露营椅
765
7899
Iawn chars
草坪椅
5.154
5323
outdoor char
户外椅
355
3665
rocker char
9c摇椅
291
3002
campng chars for adults
成人露营椅
288
2980
folding char
折叠椅
2.16
2233
Iawn char
草坪椅
209N
2.162
portable char
便携椅
166K
1.718
foldable char
折叠椅
157
1622
portable chars for adults
成人便携式椅子
138
1425
folding chars
折叠椅
131
1355
camp chars
露营椅
128
1321
camp chars for aduls
成人露营椅
1.11
1.148
camp char
营椅
1.104
1.140
campng chars heavy duty
重型野营椅
098
1013
outside chars
外面的椅子
089
919
heavy duty foldng char
重型折叠椅
068K
705
char
雪人椅
065K
670
fishng char
钓鱼椅
061
626
chars Ior outside
户外椅子
059
607
sports char
运动椅
053
549
fold
camp char
折叠露营椅
051
527
fold
chars Ior outside
户外折叠椅
051
523
oversized campng char
超大露营椅
050
513
Iawn chars foldng
草坪椅折叠
047
481
comfortab le foldng char
舒适的折叠椅
045
465
X
竞品出单词.Xlsx
gci
yeti
Ing
Ing

---
**第 7 页**
---

BOCRIGCIP2
Title:
Oersized Campi nB Chair,
Portable Foldi ng Cami IB Chairs wilh Side Pockel
Hlder and Carry
Havy
Dly_QuldoorCampi DR_Chairs [or
Adulls,
Rishi D
Sporls,
Trip,
upLo_40OLbs
Slvle 2
Bullet
Point
Extremely Comfortable: Qur camping chairs for adults heavy duty, designed with ergonomic principles, feature spacious seats with
unfolded dimensions of 40.5" L x 28" W x 39" H. The Camping Folding Chair is filled with high-loft, high-density padding in areas such
as the headrest, backrest, armrests, and seat cushion, providing ample space and support for your head, neck, back, waist, and hips。
This ensures a comfortable experience even during prolonged sitting
Sturdy and Enduring: Our camping chairs consist of a robust steel frame and newy upgraded support components, with a weight
capacity of up to 400 pounds. The powder-coated finish on the steel frame effectively prevents corrosion and fading. Additionally, the
600D tear-resistant Oxford fabric is tightly stitched and highly breathable. Therefore, the Folding Camping Chair will remain stable;
allowing for long-term use
User-Friendly Details: For added convenience, we ingeniously designed 2 cup holders and 2 side pockets on this folding chair,
allowing you to place beverages, smartphones, notebooks, and other items in an organized manner. This thoughtful design aims to
provide you with the best seating experience while freeing up your hands
Lightweight and Portable: This portable folding chair requires no assembly and can be opened for use within seconds. The outdoor
folding chair is lightweight at only 12.6 pounds, making it extremely easy to carry. The compact structure of the camp chair allows for
easy folding and storage in the provided portable carrying bag after fishing or any outdoor activity
Versatile Applications: This folding lawn chair for adults is not only suitable for hiking, camping, and hiking activities but is also perfect
for outdoor concerts, open-air movie nights, picnics, Or for use at home. The universality of the folding camping chair for adults makes
ian ideal seating choice for various occasions
Modern Appearance: The foldable chair not only excels in functiionality but
also boasts a sleek modern appearance. Meticulously coordinaated colors make
the portable chair a fashionable accessory for outdoor activitiies, adding a
touch of brilliance to your camping gear
BOFJR2Y8O
Title:
Oversized Campi nB Chairs [or
Adulls
Havy Duly Padded Qul door Folding Law 肛 Cam Chair
W Lh Cup Hlder
Cooler
Pockels [or
Qulside_Sporls
Beach Fishi DR_Carden _Portable _Supports
50OLbs,
Black
Bullel
Poinl
Oversized Padded Comfort -
PUASIA oversized camping chair heavy duty is designed with extra-wide 38.6" x23.1" seating area with
multi-layer high-density padding. Ergonomic lumbarlneck support and padded headrest deliver allday comfort:
Heavy-Duty Steel Frame - Newy upgraded reinforced Xshape steel construction with 22mm thickened tubes and anti-rust coating。
Supports up to SOOlIbs for long-lasting durability. Non-slip textured feet ensure a stable seating experience for everyone。
Extra Storage Space
Qur foldable chairs for outside features sidelback mesh pockets, along with adjustable cup holder and large
insulated cooler bag. Perfectly stores drinks, snacks, and phones within easy reach. 比 a versatile choice for comfortable padded
camping chair for adults。
AIL-Weather Durability -
Built to last, our luxury portable camping chairs construct with durable Good tear-resistant oxford breathable
fabric and reinforced stitching to prevent fraying. Ideal for camping, sporting events, barbecues, fishing, hiking, backyard lawn use;
and more outdoor adventures。
Portable & Quick Setup - Folds flat to 9.4" thick (only 12.9 Ibs with carry ba9). Sets up in 3 seconds for picnics, concerts, tailgates, or
home use. The compact structure Of our lightweight beach chairs allow for easy folding and storage in the carrying bag after any
outdoor activity.
80D087812
Title:
Oversized ~ Campi nB Chairs [or
Adults
favy Duly Support
500
bs Qul door Polding Chairs Padded Porlable
Lawn_Chairs_Camp_Chairs
wi lh_Cup_Hlder
Bullet
Point
Comfortable Camping Chair: The camping folding chair is flled with cotton padding in areas such as the headrest, backrest, armrests;
and seat cushion, providing great space and support for your head, neck, back, waist, and
Allowing YOU to relaxand stretch out
ensures 3 comfortable experience during long time sitting. Our oversized comfy folding chair feature spacious seats and fine details
with unfolded dimensions of 38.5"L X23"W X40"H
竞品listingcamping chairxlsx
Cup
BaB'
hips。

---
**第 8 页**
---

 量词
关键词翻译
AC推茬词
溢量占比
预估周曝光量
campng chars
露营椅
2765
2037
Oversized char
特大号椅子
2326
1713
foldng char
折叠椅
5099
375|
hammock campng char
吊床露营椅
465
3431
campng chars heavy duly
重型野营椅
442
3261
camp
chars Ior aduls
成人露营椅
346
255
camp char
营椅
288
212
Oversized campng char
超大露营椅
2399
176
padded foldng chars
软垫折叠椅
223
164
coleman campng chars
科尔曼露营椅
185
136
camp chars Ior aduls
成人露营椅
1.78
131
padded campng char
带衬垫的露营椅
1.71
126
campng couch
露营沙发
166N
122
camp chars foraduls heavy du 成人重型露营椅
1599
117
heavy duly campng chars
重型野营椅
144
106
comfy campng char
舒适的露营椅
136
100
camp chars
露营椅
133
98
oversized campng chars Ior ad
成人超大露营椅
1
28
94
helnox char
海利诺克斯椅
121
89
campng sola
野营沙发
1.19
88
foldng campng chars
折叠式野营椅
1.11y
81
campng couch Ioraduls
成人露营沙发
106N
78
char
雪人椅
080y
59
padded fo
char
软垫折叠椅
065
48
heavy duty foldng chai
重型折叠椅
065y
48
comfortab le loldng char
舒适的折叠椅
059
44
rockng lawn char
摇摆草坪椅
0454
33
Ioldable char
折叠椅
044
32
char campng
椅子露营
040y
29
silla campng
露营椅
036
26
Qutdoor campng chars
户外露营椅
026
19
Io
chars IOpack
折叠椅10包
025
18
reclnng campng char
躺椅
021K
15
ice fishng char
冰钓椅
0.13
9
campng char
露营椅
009N
6
foldng lawn char
折叠草坪椅
0044
3
heavy duty char
重型椅子
002
sports char
运动椅
002
Outdoor fo
chars
户外折叠椅
002"
campng cha with canopy
带顶篷的露营椅
002
sports chars for adults
成人运动椅
001
Io
char padded
折叠椅软垫
001"
foldng campng char
折叠露营椅
001
foldable campng chars
可折叠露营椅
00ON
0
Io
camp char
折叠露营椅
000"
0
rocking campng chars for adul 成人摇摆露营椅
000N
0
heavy duty foldng chars
重型折叠椅
00ON
campng rockng char
露营摇椅
000"
0
rockng camp char
摇椅
000N
0
X
关键词.Xlsx
ng
yeli
Idng
Idng
Idng
Idng
Idng

---
**第 9 页**
---

款号
511编码
产品名称
解兴方案
K2508
K2508_耻{Cr CHR'
oversized campi ] Chair 家居系统
X
本品属性表1.Xlsx
2.知识库文件:  亚马逊禁用词黑名单

---
**第 10 页**
---

此文档包含亚马逊严禁在标题(Title) _
五点描述(Bullets) . 产品描述(Description) 及后台搜索词
Search Terms) 巾出珧的词汇与表达。
促销与芏观评价类 (Promotional & Subjective Claims)
)马逊规定 Listing 必须是对产品的客观描述。禁止包含任何促销信息或无法证实的芏观评价。
[严禁出现]:
Best seller; TOp rated, Best selling; #1 (最畅销1排名笫一)
Hot item, Popular choice (爆款)
Free shipping; Free delivery (包邮)
Free Bif, Bonus;, Gift icluded (赠品)
On sale; Discount; 8%6 0f Best price; Lowest price; Cheap (促销'打折/低价)
Satisfaction Guarantec; LOOG Quality, Money back (d意度保证/退款保证)
Order now; Buy now (诱导购买动词)
Amazon's Choice; Certifed (官方'认证词)
知识产权与品牌兼『性 (Intellectual Property)
严禁末经授权使用他人的商标。品牌名。
[严禁出珧]:
任何非本产品的品牌名称 (如: Nike; Disney, Apple;
Velcro 等)
Velcro (维可牢1魔术贴}:  必须改为 "hook and loop"
Onesie (连体衣):  必须改为 "bodysuit" 或 "romper
Hula
(呼啦圈):  必须改为
Chapstick (涸唇膏):  必须改为 "l balm"
-Q-t (棉签):  必须改为 "cotton swab"
Popsicle (冰棍):  必须改为 "ice pop"
[配件兼斧性正确写 ]:
错误写泫:
"[Brand Name] Case" (例如 hone 15 Case) > 会被判定为侵权。
正确写法: "Case compatible with [Brand Name]" 或 "Case for [Brand Name]"
注意:  品牌名之前必须有 "compatible with" 或 "for"
三
厌疗器械与功效撖感词 Medical & Health Claims)
非 OTC 药品或末获得 FD4 认证的厌疗器械。严禁隋示治疗。预防或治愈犊病的功能。
[严禁出珧]:
Cure; Heal, Treat, Treatment; Remedy (治愈/治疗|疗法)
Prerent; Frevcntion (预防)
Relief, Relieve;
pain (止痛1缓解
除非是合规 OTC)
Anti-virus; Anti-[lu, Anti-inflammatory (抗病毒/消炎)
FDAapproved, FDA cleared (除非有真实证书并已备案。否则严禁使用)
诎及其体病症名称: Cancer, Diabetes; Arthritis 等
四
杀虫剂与生物杀灭剂敏感词 (Pesticide & Biocides)
这是亚马逊最斧易误杀的重灾区。任何暗示能 *杀灭。驱除。抑制"  生物 (细菌。胥菌。昆虫)
的词。都会被判定为杀虫剂。需要 EPA 注册写.
[严禁出珧 (除非你有 EPA 写) ]:
Anti-bacterial, Anti-microbial (抗菌抗徵生物)
Anti-funpal, Mold resistant (抗霉菌{防雷)
Anti-dust mite (防尘蛸)
Insect repellent, BuB stop (驱蚊防虫
Disinfect; Sanitize, Sterilize (消莓|杀菌)
Non-toxic (无毒):  极易触发审核。建议改为 "BPA Free" 或 "Safe material"。
Safe; Healthy, Harmless (绝对化安全用语)
amazon_compliance_
blacklist.txt
LeBa;
Hoop
"toy
hoop"
Stop