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
```markdown
| 流量词 | 关键词翻译 | AC推荐词 | 流量占比 | 预估周曝光量 |
| :--- | :--- | :--- | :--- | :--- |
| camping chairs | 露营椅 | | 20.18% | 20.843 |
| beach chair | 沙滩椅 | | 14.59% | 15.070 |
| outdoor chairs | 户外椅 | | 8.90% | 9.191 |
| camping chair | 露营椅 | | 7.65% | 7.899 |
| lawn chairs | 草坪椅 | | 5.15% | 5.323 |
| outdoor chair | 户外椅 | | 3.55% | 3.665 |
| gcirocker chair | gc摇椅 | | 2.91% | 3.002 |
| camping chairs for adults | 成人露营椅 | | 2.88% | 2.980 |
| folding chair | 折叠椅 | | 2.16% | 2.233 |
| lawn chair | 草坪椅 | | 2.09% | 2.162 |
| portable chair | 便携椅 | | 1.66% | 1.718 |
| foldable chair | 折叠椅 | | 1.57% | 1.622 |
| portable chairs for adults | 成人便携式椅子 | | 1.38% | 1.425 |
| folding chairs | 折叠椅 | | 1.31% | 1.355 |
| camp chairs | 露营椅 | | 1.28% | 1.321 |
| camp chairs for adults | 成人露营椅 | | 1.11% | 1.148 |
| camp chair | 营椅 | | 1.10% | 1.140 |
| camping chairs heavy duty | 重型野营椅 | | 0.98% | 1.013 |
| outside chairs | 外面的椅子 | | 0.89% | 919 |
| heavy duty folding chair | 重型折叠椅 | | 0.68% | 705 |
| yeti chair | 雪人椅 | | 0.65% | 670 |
| fishing chair | 钓鱼椅 | | 0.61% | 626 |
| chairs for outside | 户外椅子 | | 0.59% | 607 |
| sports chair | 运动椅 | | 0.53% | 549 |
| folding camp chair | 折叠露营椅 | | 0.51% | 527 |
| folding chairs for outside | 户外折叠椅 | | 0.51% | 523 |
| oversized camping chair | 超大露营椅 | | 0.50% | 513 |
| lawn chairs folding | 草坪椅 折叠 | | 0.47% | 481 |
| comfortable folding chair | 舒适的折叠椅 | | 0.45% | 465 |
```markdown
| BOCR16C1P2 |  |
| --- | --- |
| Title: | Oversized Camping Chair, Portable Folding Camping Chairs with Side Pocket, Cup Holder and Carry Bag, Heavy Duty Outdoor Camping Chairs for Adults, Fishing, Sports, Trip, up to 400lbs, Style 2 |
| Bullet Point: |  |
|  | Extremely Comfortable: Our camping chairs for adults heavy duty, designed with ergonomic principles, feature spacious seats with unfolded dimensions of 40.5" L x 28" W x 39" H. The Camping Folding Chair is filled with high-loft, high-density padding in areas such as the headrest, backrest, armrests, and seat cushion, providing ample space and support for your head, neck, back, waist, and hips. This ensures a comfortable experience even during prolonged sitting |
|  | Sturdy and Enduring: Our camping chairs consist of a robust steel frame and newly upgraded support components, with a weight capacity of up to 400 pounds. The powder-coated finish on the steel frame effectively prevents corrosion and fading. Additionally, the 600D tear-resistant Oxford fabric is tightly stitched and highly breathable. Therefore, the Folding Camping Chair will remain stable, allowing for long-term use |
|  | User-Friendly Details: For added convenience, we ingeniously designed 2 cup holders and 2 side pockets on this folding chair, allowing you to place beverages, smartphones, notebooks, and other items in an organized manner. This thoughtful design aims to provide you with the best seating experience while freeing up your hands |
|  | Lightweight and Portable: This portable folding chair requires no assembly and can be opened for use within seconds. The outdoor folding chair is lightweight at only 12.6 pounds, making it extremely easy to carry. The compact structure of the camp chair allows for easy folding and storage in the provided portable carrying bag after fishing or any outdoor activity |
|  | Versatile Applications: This folding lawn chair for adults is not only suitable for hiking, camping, and hiking activities but is also perfect for outdoor concerts, open-air movie nights, picnics, or for use at home. The universality of the folding camping chair for adults makes it an ideal seating choice for various occasions |
|  | Modern Appearance: The foldable chair not only excels in functionality but also boasts a sleek modern appearance. Meticulously coordinated colors make the portable chair a fashionable accessory for outdoor activities, adding a touch of brilliance to your camping gear |
| B0FJF2Y8G5 |  |
| Title: | Oversized Camping Chairs for Adults - Heavy Duty Padded Outdoor Folding Lawn XL Camp Chair with Cup Holder Cooler Pockets for Outside Sports Beach Fishing Garden Portable Supports 500lbs, Black |
| Bullet Point: |  |
|  | Oversized Padded Comfort - PUVASIA oversized camping chair heavy duty is designed with extra-wide 38.6" x 23.1" seating area with multi-layer high-density padding. Ergonomic lumbar/neck support and padded headrest deliver all-day comfort. |
|  | Heavy-Duty Steel Frame - Newly upgraded reinforced X-shape steel construction with 22mm thickened tubes and anti-rust coating. Supports up to 500lbs for long-lasting durability. Non-slip textured feet ensure a stable seating experience for everyone. |
|  | Extra Storage Space - Our foldable chairs for outside features side/back mesh pockets, along with adjustable cup holder and large insulated cooler bag. Perfectly stores drinks, snacks, and phones within easy reach. It a versatile choice for comfortable padded camping chair for adults. |
|  | All-Weather Durability - Built to last, our luxury portable camping chairs construct with durable 600d tear-resistant oxford breathable fabric and reinforced stitching to prevent fraying. Ideal for camping, sporting events, barbecues, fishing, hiking, backyard lawn use, and more outdoor adventures. |
|  | Portable & Quick Setup - Folds flat to 9.4" thick (only 12.9 lbs with carry bag). Sets up in 3 seconds for picnics, concerts, tailgates, or home use. The compact structure of our lightweight beach chairs allow for easy folding and storage in the carrying bag after any outdoor activity. |
| B0DDQB78L2 |  |
| Title: | Oversized XL Camping Chairs for Adults Heavy Duty Support 500 lbs Outdoor Folding Chairs Padded Portable Lawn Chairs Camp Chairs with Cup Holder |
| Bullet Point: | Comfortable Camping Chair: The camping folding chair is filled with cotton padding in areas such as the headrest, backrest, armrests, and seat cushion, providing great space and support for your head, neck, back, waist, and hips. Allowing you to relax and stretch out ensures a comfortable experience during long time sitting. Our oversized comfy folding chair feature spacious seats and fine details with unfolded dimensions of 38.5"L x 23"W x 40"H |
|  | 竞品listingcamping chair.xlsx |
| 流量词 | 关键词翻译 | AC推荐词 | 流量占比 | 预估周曝光量 |
| --- | --- | --- | --- | --- |
| camping chairs | 露营椅 |  | 27.65% | 2.037 |
| oversized chair | 特大号椅子 |  | 23.26% | 1.713 |
| folding chair | 折叠椅 |  | 5.09% | 375 |
| hammock camping chair | 吊床露营椅 |  | 4.65% | 343 |
| camping chairs heavy duty | 重型野营椅 |  | 4.42% | 326 |
| camping chairs for adults | 成人露营椅 |  | 3.46% | 255 |
| camp chair | 营椅 |  | 2.88% | 212 |
| oversized camping chair | 超大露营椅 |  | 2.39% | 176 |
| padded folding chairs | 软垫折叠椅 |  | 2.23% | 164 |
| coleman camping chairs | 科尔曼露营椅 |  | 1.85% | 136 |
| camp chairs for adults | 成人露营椅 |  | 1.78% | 131 |
| padded camping chair | 带衬垫的露营椅 |  | 1.71% | 126 |
| camping couch | 露营沙发 |  | 1.66% | 122 |
| camp chairs for adults heavy du | 成人重型露营椅 |  | 1.59% | 117 |
| heavy duty camping chairs | 重型野营椅 |  | 1.44% | 106 |
| comfy camping chair | 舒适的露营椅 |  | 1.36% | 100 |
| camping chairs | 露营椅 |  | 1.33% | 98 |
| oversized camping chairs for ad | 成人超大露营椅 |  | 1.28% | 94 |
| helinox chair | 海利诺克斯椅 |  | 1.21% | 89 |
| camping sofa | 野营沙发 |  | 1.19% | 88 |
| folding camping chairs | 折叠式野营椅 |  | 1.11% | 81 |
| camping couch for adults | 成人露营沙发 |  | 1.06% | 78 |
| yeti chair | 雪人椅 |  | 0.80% | 59 |
| padded folding chair | 软垫折叠椅 |  | 0.65% | 48 |
| heavy duty folding chair | 重型折叠椅 |  | 0.65% | 48 |
| comfortable folding chair | 舒适的折叠椅 |  | 0.59% | 44 |
| rocking lawn chair | 摇摆草坪椅 |  | 0.45% | 33 |
| foldable chair | 折叠椅 |  | 0.44% | 32 |
| chair camping | 椅子露营 |  | 0.40% | 29 |
| silla camping | 露营椅 |  | 0.36% | 26 |
| outdoor camping chairs | 户外露营椅 |  | 0.26% | 19 |
| folding chairs 10 pack | 折叠椅10包 |  | 0.25% | 18 |
| reclining camping chair | 躺椅 |  | 0.21% | 15 |
| ice fishing chair | 冰钓椅 |  | 0.13% | 9 |
| camping chair | 露营椅 |  | 0.09% | 6 |
| folding lawn chair | 折叠草坪椅 |  | 0.04% | 3 |
| heavy duty chair | 重型椅子 |  | 0.02% | 1 |
| sports chair | 运动椅 |  | 0.02% | 1 |
| outdoor folding chairs | 户外折叠椅 |  | 0.02% | 1 |
| camping chair with canopy | 带顶篷的露营椅 |  | 0.02% | 1 |
| sports chairs for adults | 成人运动椅 |  | 0.01% | 1 |
| folding chair padded | 折叠椅软垫 |  | 0.01% | 1 |
| folding camping chair | 折叠露营椅 |  | 0.01% | 0 |
| foldable camping chairs | 可折叠露营椅 |  | 0.00% | 0 |
| folding camp chair | 折叠露营椅 |  | 0.00% | 0 |
| rocking camping chairs for adult | 成人摇摆露营椅 |  | 0.00% | 0 |
| heavy duty folding chairs | 重型折叠椅 |  | 0.00% | 0 |
| camping rocking chair | 露营摇椅 |  | 0.00% | 0 |
| rocking camp chair | 摇椅 |  | 0.00% | 0 |

关键词.xlsx
```markdown
| 款号 | sku编码 | 产品名称 | 解决方案 |
| :--- | :--- | :--- | :--- |
| KC2508 | KC2508_BLACK/GREY | oversized camping chair | 家居系统 |

本品属性表1.xlsx

2.知识库文件：亚马逊禁用词黑名单
```markdown
此文档包含亚马逊严禁在标题(Title)、五点描述(Bullets)、产品描述(Description)及后台搜索词 (Search Terms)中出现的词汇与表达。

一、促销与主观评价类 (Promotional & Subjective Claims)

亚马逊规定 Listing 必须是对产品的客观描述，禁止包含任何促销信息或无法证实的主观评价。

[严禁出现]:

- Best seller, Top rated, Best selling, #1 (最畅销/排名第一)
- Hot item, Popular choice (爆款)
- Free shipping, Free delivery (包邮)
- Free gift, Bonus, Gift included (赠品)
- On sale, Discount, x% off, Best price, Lowest price, Cheap (促销/打折/低价)
- Satisfaction Guarantee, 100% Quality, Money back (满意度保证/退款保证)
- Order now, Buy now (诱导购买动词)
- Amazon's Choice, Certified (官方认证词)

二、知识产权与品牌兼容性 (Intellectual Property)

严禁未经授权使用他人的商标、品牌名。

[严禁出现]:

- 任何非本产品的品牌名称 (如: Nike, Disney, Apple, Lego, Velcro 等).
- Velcro (维可牢/魔术贴): 必须改为 "hook and loop".
- Onesie (连体衣): 必须改为 "bodysuit" 或 "romper".
- Hula Hoop (呼啦圈): 必须改为 "toy hoop".
- Chapstick (润唇膏): 必须改为 "lip balm".
- Q-tip (棉签): 必须改为 "cotton swab".
- Popsicle (冰棍): 必须改为 "ice pop".

[配件兼容性正确写法]:

- 错误写法: "[Brand Name] Case" (例如 iPhone 15 Case) -> 会被判定为侵权.
- 正确写法: "Case compatible with [Brand Name]" 或 "Case for [Brand Name]".
- 注意: 品牌名之前必须有 "compatible with" 或 "for".

三、医疗器械与功效敏感词 (Medical & Health Claims)

非 OTC 药品或未获得 FDA 认证的医疗器械，严禁暗示治疗、预防或治愈疾病的功能。

[严禁出现]:

- Cure, Heal, Treat, Treatment, Remedy (治愈/治疗/疗法)
- Prevent, Prevention (预防)
- Relief, Relieve, Stop pain (止痛/缓解 - 除非是合规 OTC)
- Anti-virus, Anti-flu, Anti-inflammatory (抗病毒/消炎)
- FDA approved, FDA cleared (除非有真实证书并已备案，否则严禁使用)
- 涉及具体病症名称: Cancer, Diabetes, Arthritis 等.

四、杀虫剂与生物杀灭剂敏感词 (Pesticide & Biocides)

这是亚马逊最容易误杀的重灾区，任何暗示能“杀灭、驱除、抑制”生物（细菌、霉菌、昆虫）的词，都会被判定为杀虫剂，需要 EPA 注册号。

[严禁出现 (除非你有 EPA 号)]:

- Anti-bacterial, Anti-microbial (抗菌/抗微生物)
- Anti-fungal, Mold resistant (抗霉菌/防霉)
- Anti-dust mite (防尘螨)
- Insect repellent, Bug stop (驱蚊/防虫)
- Disinfect, Sanitize, Sterilize (消毒/杀菌)
- Non-toxic (无毒): 极易触发审核，建议改为 “BPA Free” 或 “Safe material”.
- Safe, Healthy, Harmless (绝对化安全用语)

amazon_compliance_blacklist.txt