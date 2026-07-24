# EN_API — ERPNext REST API 工具

通过 ERPNext REST API 上传图片、更新物料组 (Item Group) 主图、生成销售出库追溯报表。

## 脚本列表

| 脚本 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `upload_item_images.py` | 更新物料组主图 | 赛狐图片链接 Excel | 上传结果报告 |
| `upload_local_images.py` | CLI 批量上传本地图片 | 本地图片目录 | 图片链接 Excel |
| `image_upload_app.py` | **Web 可视化上传** | 浏览器拖拽图片 | 图片链接 Excel |
| `upload_pim_images.py` | 上传图片到物料组 custom_pim_images 子表 | 本地图片目录 | PIM图片上传报告 |
| `dn_trace_report.py` | **销售出库→物料移动追溯报表** | 月份或DN单号 | 追溯明细 Excel |

## 前置条件

- Python >= 3.10, `uv` 管理依赖
- 凭证配置 (任选其一):
  ```bash
  # 方式一: 复制 .env.example → .env 填入真实值 (推荐)
  cp EN_API/.env.example EN_API/.env
  # 方式二: 设置环境变量
  set ERP_API_KEY=xxx && set ERP_API_SECRET=yyy
  ```

## 快速开始

```bash
# Web 可视化上传（推荐普通同事使用，浏览器拖拽+排序）
cd EN_API
uv run python image_upload_app.py

# CLI 批量上传（固定目录，AI/脚本调用）
uv run python upload_local_images.py

# 物料组主图更新（开发用，默认 test 环境）
uv run python upload_item_images.py --dry-run        # 预览
uv run python upload_item_images.py --spu KS0001     # 单 SPU 测试
uv run python upload_item_images.py                  # 批量
```

## 管道

### image_upload_app.py (Web)

```
浏览器拖拽/选图 → 缩略图预览+拖拽排序 → 点击上传
→ FastAPI 后端逐张调用 ERPNext upload_file
→ 生成 Excel 下载（顺序=前端排列顺序）
```

### upload_local_images.py (CLI)

## 命令行参数

### upload_item_images.py

| 参数 | 说明 |
|------|------|
| `--env test/prod` | 目标环境 (默认 test) |
| `--url <URL>` | 直接指定 URL |
| `--spu KS0001` | 仅处理指定款式ID |
| `--dry-run` | 预览模式，只查不写 |
| `--input <path>` | 指定输入文件 |

### upload_local_images.py

| 参数 | 说明 |
|------|------|
| `--env test/prod` | 目标环境 (默认 prod，开发测试用 `--env test`) |
| `--input-dir <path>` | 图片目录 (默认 D:/EN上传图片) |
| `--no-compress` | 不压缩，直接上传原图 |
| `--max-size <px>` | 压缩后最大边长 (默认 1500) |
| `--quality <1-100>` | JPEG 质量 (默认 85) |

### image_upload_app.py

| 参数 | 说明 |
|------|------|
| `--port <port>` | 服务端口 (默认 8099) |
| `--no-browser` | 不自动打开浏览器 |

> 启动后浏览器自动打开，页面顶部可切换测试/生产环境。
> 页面上有「压缩图片」复选框，默认勾选（quality 85, max 1500px）。

## 环境

| 环境 | 基础 URL | 适用 |
|------|---------|------|
| prod (默认) | https://erpnext.vilavi.cn | 普通用户日常使用 |
| test | https://ensh.vilavi.cn | 开发测试用 |

> **普通用户直接运行即可，默认就是生产环境**，不需要关心 `--env` 参数。
> 只有你和个别开发同事在调试时需要用 `--env test`。

## 输入格式

Excel 文件（`赛狐图片链接/` 目录），列：
- `SKU` — 完整的物料 SKU
- `品名` — 产品名称
- `图片链接` — 图片 HTTPS URL
- `spu` — 款式ID，对应 Item Group 的 `custom_model_id` 字段

## 输出

### upload_local_images.py / image_upload_app.py

`out/图片上传链接_{timestamp}.xlsx` — 单 sheet `图片链接`，列：
- `文件名` / `file_url` / `完整链接` — 可直接粘贴到销售平台

### upload_item_images.py

`out/图片上传结果_{timestamp}.xlsx`:
- `汇总` sheet — 总行数 + 成功/失败计数
- `明细` sheet — 每行的处理状态和备注

---

## 脚本: `upload_pim_images.py` — PIM图片上传

上传本地图片到 ERPNext 物料组的 `custom_pim_images` 子表，可选同步更新物料组主图字段。

**用途**: 运营/设计同事提供物料组图片，上传到 ERPNext 的 PIM 图片管理中。

### 命令行

```bash
uv run python upload_pim_images.py                      # 默认 test，仅写入子表
uv run python upload_pim_images.py --env prod           # 生产环境
uv run python upload_pim_images.py --update-image       # 同步更新物料组主图
uv run python upload_pim_images.py --dry-run            # 预览模式
uv run python upload_pim_images.py --no-compress        # 不压缩
```

### 参数

| 参数 | 说明 |
|------|------|
| `--env test/prod` | 目标环境 (默认 test) |
| `--update-image / -m` | 上传后同步更新物料组的 `image` 主图字段 |
| `--dry-run` | 预览模式，只查不写 |
| `--input-dir <path>` | 图片目录 (默认 C:/Users/DEV01/Pictures/EN物料组图片) |
| `--no-compress` | 不压缩，直接上传原图 |
| `--max-size <px>` | 压缩后最大边长 (默认 1500) |
| `--quality <1-100>` | JPEG 质量 (默认 85) |

### 处理流程

```
图片目录 → 文件名提取物料组名称 → 查询 ERPNext 物料组
  → 压缩图片 (max 1500px, JPEG 85, EXIF方向修正, 透明背景处理, 安全回退)
  → 查重: custom_pim_images 已存在同名文件? → 是则跳过
  → 上传文件到 ERPNext → 写入 custom_pim_images 子表
  → [可选 --update-image] PUT 更新 image 主图字段
  → 生成 Excel 报告
```

### 输出

`out/PIM图片上传结果_{timestamp}.xlsx`，含汇总 + 明细 sheet。

---

## 脚本: `dn_trace_report.py` — 销售出库→物料移动追溯报表

从销售出库(DN)维度追溯其关联的销售订单(SO)、生产工单(WO)、工单耗用(SE)及发料明细，汇总为 Excel。

**数据链**: `DN → DN Item.against_sales_order → SO → WO.sales_order → WO (In Process/Completed) → SE.work_order → SE (Material Consumption for Manufacture, docstatus 0/1) → SE Item`

**输出**: 两个 Sheet
- `追溯明细` — 非成品工单(production_item 非 KS 开头)的完整链路，含 SE/SE Item 发料明细 + **是否面料**判断
- `成品工单` — 成品工单(KS 开头，不涉及耗用)，仅 DN→SO→WO 层级

### 命令行

```bash
# 按月份拉取
uv run python EN_API/dn_trace_report.py --month 2026-07

# 按单号
uv run python EN_API/dn_trace_report.py --dn DN-2407-00001,DN-2407-00002

# 测试环境
uv run python EN_API/dn_trace_report.py --month 2026-07 --test
```

### 参数

| 参数 | 说明 |
|------|------|
| `--month YYYY-MM` | 目标月份，拉取该月所有已提交 DN（与 `--dn` 二选一） |
| `--dn DN-xxx,DN-yyy` | 指定 DN 单号逗号分隔（与 `--month` 二选一） |
| `--test` | 使用测试系统 (ensh.vilavi.cn) |
| `--output / -o` | 输出路径 (默认 `EN_API/out/`) |

### 关键实现细节

- **仅 DN 按日期过滤**，SO/WO/SE 不受日期限制（解决跨月工单耗用遗漏）
- **操作人自动解析**：从邮箱格式转换为 User.full_name 真实姓名
- **成品/半成品自动分离**：production_item 以 KS 开头归入"成品工单"，其余归入"追溯明细"
- **面料自动识别**：通过物料所属 Item Group 是否属于"面料"及其子组判断，输出"是/否"
