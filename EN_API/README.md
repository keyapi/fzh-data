# EN_API — ERPNext REST API 工具

通过 ERPNext REST API 更新物料组 (Item Group) 主图 (image 字段)。

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
# 预览模式（查询匹配但不更新）
cd EN_API
python upload_item_images.py --dry-run

# 测试单个 SPU
python upload_item_images.py --spu KS0001

# 批量更新所有 SPU
python upload_item_images.py
```

## 管道

```
赛狐图片链接 Excel (SKU, spu, 图片链接)
  → 逐行处理 (SPU 缓存, 同 SPU 跳过)
  → GET Item Group (custom_model_id = spu)
  → 下载图片 + 真实文件上传 (绕过 COS 防盗链)
  → PUT Item Group.image (本地 /files/xxx)
  → 生成结果报告 (所有行)
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--env test/prod` | 目标环境 (默认 test) |
| `--url <URL>` | 直接指定 URL |
| `--spu KS0001` | 仅处理指定款式ID |
| `--dry-run` | 预览模式，只查不写 |
| `--input <path>` | 指定输入文件 |

## 环境

| 环境 | 基础 URL |
|------|---------|
| test | https://ensh.vilavi.cn |
| prod | https://erpnext.vilavi.cn |

## 输入格式

Excel 文件（`赛狐图片链接/` 目录），列：
- `SKU` — 完整的物料 SKU
- `品名` — 产品名称
- `图片链接` — 图片 HTTPS URL
- `spu` — 款式ID，对应 Item Group 的 `custom_model_id` 字段

## 输出

`out/图片上传结果_{timestamp}.xlsx`:
- `汇总` sheet — 总行数 + 成功/失败计数
- `明细` sheet — 每行的处理状态和备注
