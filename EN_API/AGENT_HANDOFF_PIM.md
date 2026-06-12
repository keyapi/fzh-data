# upload_pim_images.py — Agent 交接说明

> **脚本**: `upload_pim_images.py`
> **人读文档**: [README.md](README.md)

---

## 1. 业务背景

将本地图片上传到 ERPNext 物料组 (Item Group) 的 `custom_pim_images` 子表（PIM 图片管理）。
图片文件名（不含扩展名）作为 `item_group_name` 查询匹配的物料组。
若图片名与物料组名不一致，通过 `FILENAME_MAPPING` 字典进行映射转换。

可选通过 `--update-image` 开关同步更新物料组的 `image` 主图字段（即物料组默认显示图片）。
当前有值则替换，当前无值则直接设置。

---

## 2. 管道步骤

```
C:/Users/DEV01/Pictures/EN物料组图片/ 目录
  → 列出所有 .jpg/.jpeg/.png/.gif/.webp
  → 逐文件处理:
      1. filename stem → FILENAME_MAPPING 查询 (有映射则使用映射名)
      2. 对每个目标物料组名称执行:
         a. 查 Item Group (支持一对多，如单双人地板沙发→单人位+双人位)
         b. 压缩图片 (max 1500px, JPEG quality 85)
         c. 查重: 检查 custom_pim_images 是否已存在同名文件 → 存在则跳过
         d. POST /api/method/upload_file (上传到 ERPNext)
         e. PUT /api/resource/Item Group/{name}
            → 追加一行到 custom_pim_images 子表
         f. [可选 --update-image] PUT /api/resource/Item Group/{name}
            → 设置 image 字段为 file_url
  → 写入 out/PIM图片上传结果_{ts}.xlsx
  → 写入 out/PIM图片上传结果_{ts}.xlsx
```

---

## 3. 关键函数

| 函数 | 作用 |
|------|------|
| `ErpnextClient(base_url, api_key, api_secret)` | API 客户端, 管理 session + 认证 + Expect 头处理 |
| `ErpnextClient.find_item_group_by_name(name)` | 按 item_group_name 查 Item Group |
| `ErpnextClient.get_item_group_full(docname)` | 获取物料组完整数据（含子表） |
| `ErpnextClient.upload_file(filename, bytes, doctype, docname)` | 上传文件到 ERPNext，返回 file_url |
| `ErpnextClient.update_pim_images(docname, file_url)` | 向 custom_pim_images 子表追加记录 |
| `ErpnextClient.set_image_field(docname, file_url)` | 更新物料组的 image 主图字段 |
| `compress_image(data, max_size, quality)` | 压缩图片（缩放 + RGB转换 + 安全回退） |

### custom_pim_images 子表 (Item Group Image) 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image_file` | Attach Image | 是 | 图片文件 |
| `file_url` | Data | 否 | 文件 URL |
| `purpose` | Select | 否 | Main/Gallery/Detail/Fabric/Size/Lifestyle/Other |
| `is_primary` | Check | 否 | 是否为主图 |
| `sort_order` | Int | 否 | 排序 |

---

## 4. API 端点

| 端点 | 方法 | 关键参数 |
|------|------|---------|
| `/api/resource/Item Group` | GET | `filters=json.dumps([["Item Group","item_group_name","=",name]])` |
| `/api/resource/Item Group/{name}` | GET | 获取完整文档（含子表） |
| `/api/method/upload_file` | POST | `file` (multipart), `doctype=Item Group`, `docname=<name>` |
| `/api/resource/Item Group/{name}` | PUT | `{"custom_pim_images": [...]}` 更新子表 |
| `/api/resource/Item Group/{name}` | PUT | `{"image": file_url}` 更新主图字段 |

---

## 5. 文件名映射 (FILENAME_MAPPING)

当图片文件名与 ERPNext 物料组名称不一致时，通过脚本中的 `FILENAME_MAPPING` 字典进行映射。
支持 **一对一**（一个文件名对应一个物料组）和 **一对多**（一个文件名对应多个物料组，上传到每个目标）。

### 当前映射表

| 图片文件名 | 目标物料组 | 映射类型 |
|-----------|-----------|---------|
| 半圆宠物辅助爬梯 | 半圆宠物爬梯 | 一对一 |
| 儿童泡沫攀岩块 | 儿童泡沫攀岩块类 | 一对一 |
| 单双人地板沙发 | 单双人地板沙发-单人位、单双人地板沙发-双人位 | 一对多 |
| 可组合扶手沙发组合 | 可组合扶手沙发 | 一对一 |
| 安全感宠物窝 | 安全感靠墙宠物窝 | 一对一 |
| 弧形海绵靠枕-涤麻 | 弧形海绵靠枕 | 一对一 |
| 弧形海绵靠枕-菱形 | 弧形海绵靠枕 | 一对一 |
| 户外托盘垫-云朵款 | 户外托盘垫-云朵款靠背、户外托盘垫-云朵款坐垫 | 一对多 |
| 户外托盘垫印花款 | 户外托盘垫印花款类 | 一对一 |
| 扭结地板沙发 | 扭结地板沙发-沙发、扭结地板沙发-脚踏 | 一对多 |
| 拼图模块沙发 | 拼图模块沙发-六边形模块、拼图模块沙发-单人 | 一对多 |
| 曲线沙发 | 曲线沙发座椅、曲线沙发茶几 | 一对多 |
| 椭圆墩—旧铁皮 | 椭圆墩-旧铁皮 | 一对一 |
| 大尺寸车载狗窝 | 大尺寸车载宠物窝 | 一对一 |

> 未在映射表中的文件名，直接使用文件名（不含扩展名）作为物料组名称查询。

### 添加新映射

在脚本 `FILENAME_MAPPING` 字典中增加条目：
```python
# 一对一
"图片文件名": "物料组名称",
# 一对多
"图片文件名": ["物料组名称1", "物料组名称2"],
```

---

## 6. 命令行

```bash
uv run python upload_pim_images.py                      # 默认 test，仅写入子表
uv run python upload_pim_images.py --env prod           # 生产环境
uv run python upload_pim_images.py --update-image       # 同步更新物料组主图
uv run python upload_pim_images.py --dry-run            # 预览模式
uv run python upload_pim_images.py --no-compress        # 不压缩
```

### 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--env` | test | 目标环境 (test/prod) |
| `--update-image / -m` | false | 同步更新 image 主图字段 |
| `--dry-run` | false | 预览模式 |
| `--input-dir` | C:/Users/DEV01/Pictures/EN物料组图片 | 图片目录 |
| `--no-compress` | false | 关闭压缩 |
| `--max-size` | 1500 | 最大边长 |
| `--quality` | 85 | JPEG 质量 |

---

## 7. 数据路径

| 角色 | 默认位置 |
|------|---------|
| 输入 | `C:/Users/DEV01/Pictures/EN物料组图片/` |
| 输出 | `./out/PIM图片上传结果_{timestamp}.xlsx` |

---

## 8. 边界条件

1. **物料组未找到** → 跳过该文件，报告标记"跳过"
2. **图片压缩** → 仅当 `max(w,h) > 1500` 时缩放；透明背景填充白色；压缩后变大则保留原图
3. **--update-image 失败** → 不影响子表写入，报告标记"成功"（非"成功(含主图)"）
4. **子表已有记录** → 自动递增 `sort_order`；首条记录 `is_primary=1`
5. **文件名映射** → 先在 `FILENAME_MAPPING` 中查找，未命中则直接用文件名查询
6. **一对多映射** → 同一张图片上传到多个物料组，报告分别为每行记录
7. **凭证** — `.env` 文件或环境变量 `(TEST|PROD)_ERP_API_KEY` / `(TEST|PROD)_ERP_API_SECRET`
8. **文件名编码** → 中文文件名正常支持（通过 `requests` + UTF-8 传输）
