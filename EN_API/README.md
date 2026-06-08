# EN_API — ERPNext REST API 工具

通过 ERPNext REST API 上传图片、更新物料组 (Item Group) 主图。

## 脚本列表

| 脚本 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `upload_item_images.py` | 更新物料组主图 | 赛狐图片链接 Excel | 上传结果报告 |
| `upload_local_images.py` | CLI 批量上传本地图片 | 本地图片目录 | 图片链接 Excel |
| `image_upload_app.py` | **Web 可视化上传** | 浏览器拖拽图片 | 图片链接 Excel |

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

### image_upload_app.py

| 参数 | 说明 |
|------|------|
| `--port <port>` | 服务端口 (默认 8099) |
| `--no-browser` | 不自动打开浏览器 |

> 启动后浏览器自动打开，页面顶部可切换测试/生产环境。

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
