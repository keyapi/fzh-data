# EN_API — Agent 交接说明

> **脚本**: `upload_item_images.py` (单文件)
> **人读文档**: [README.md](README.md)

---

## 1. 业务背景

从赛狐「图片链接」Excel 读取 SPU（款式ID）和图片 URL，更新 ERPNext 对应 **物料组 (Item Group)** 的 `image` 主图字段。

Excel 来源：赛狐下载中心导出。列: `SKU`、`品名`、`图片链接`、`spu`。
`spu` 即款式ID → Item Group 的自定义字段 `custom_model_id`。

---

## 2. 管道步骤

```
赛狐图片链接/ 目录下最新 xlsx
  → pd.read_excel 读取
  → 逐行处理 (SPU 查询缓存, 同 SPU 跳过上传):
      1. GET /api/resource/Item Group (按 custom_model_id 查询, 缓存)
      2. 查所有 File 记录 → 按 content_hash 分组, 找重复记录
      3. 附件 ≥3: 只删 image 字段的重复记录 (同 hash) + hash=None 记录
         绝不删: 非 image 字段附件 (如 PDF) / 唯一 hash 的记录
      4. 无安全可删记录 → 跳过并报告
      5. 下载图片 → POST upload_file (真实文件) → PUT IG.image
  → 写入 out/图片上传结果_{ts}.xlsx (所有行, 含跳过)
```

**为什么要下载再上传为实际文件？**
- COS (腾讯云对象存储) 开启了防盗链: 浏览器通过 ensh.vilavi.cn 页面加载 COS 图片时发送 `Referer` 头 → COS 返回 403
- 将图片下载后以真实文件存入 ERPNext，使用本地 `/files/xxx` 路径，无跨域/防盗链问题
- `file_url` 模式创建的 File 记录 `file_size=0`、预览不显示；真实文件 `file_size>0`、预览正常

---

## 3. 关键函数

| 函数 | 作用 |
|------|------|
| `ErpnextClient(base_url, api_key, api_secret)` | API 客户端, 管理 session + 认证 + Expect 头处理 |
| `ErpnextClient.find_item_group(spu)` | 按 custom_model_id 查 Item Group, 带缓存 |
| `ErpnextClient.get_attached_files(ig_name)` | 查询挂载到 IG image 字段的所有 File 记录 |
| `ErpnextClient.delete_files(names)` | DELETE 指定的 File 记录 → 返回删除数 |
| `ErpnextClient.download_and_upload(ig_name, url)` | 下载图片 + multipart 上传 → 返回本地 file_url |
| `ErpnextClient.set_image_field(ig_name, url)` | PUT 更新 Item Group.image 字段 |
| `_find_latest_xlsx(dir, keyword)` | 按关键词选最新 xlsx (排除 ~$) |
| `_NoExpectAdapter` | HTTPAdapter: 移除 Expect 头, 解决 nginx 417 |

---

## 4. API 端点与关键参数

| 端点 | 方法 | 关键参数 |
|------|------|---------|
| `/api/resource/Item Group` | GET | `filters`=`json.dumps([["Item Group","custom_model_id","=",spu]])` |
| `/api/method/upload_file` | POST | `file` (multipart 文件), `doctype=Item Group`, `docname=<name>`, `fieldname=image` |
| `/api/resource/Item Group/{name}` | PUT | `{"image": url}` |

### filters/fields 参数格式

必须使用 `json.dumps()` 而非手动拼接 JSON 字符串，且 filters 中需带 doctype 前缀：
```python
params = {
    "filters": json.dumps([["Item Group", "custom_model_id", "=", spu]]),
    "fields": json.dumps(["name", "item_group_name", "image"]),
}
```

### nginx 417 问题

nginx/1.18.0 对 `Expect: 100-continue` 返回 417。通过自定义 `HTTPAdapter` 在发送前移除 Expect 头解决。

---

## 5. 命令行

```bash
python upload_item_images.py                  # 批量 (test 环境)
python upload_item_images.py --spu KS0001     # 单 SPU 测试
python upload_item_images.py --dry-run        # 预览匹配, 不写
python upload_item_images.py --env prod       # 生产环境
python upload_item_images.py --input "x.xlsx" # 指定输入文件
```

---

## 6. 数据路径

| 角色 | 默认位置 |
|------|---------|
| 输入 | `./赛狐图片链接/` (文件名含 "图片链接", 最新 mtime) |
| 输出 | `./out/图片上传结果_{timestamp}.xlsx` |

---

## 7. 边界条件 / 已知限制

1. **全行报告** — 报告展示 Excel 所有行，同 SPU 后续行标记"跳过（同SPU已处理）"
2. **SPU 查询缓存** — 同 SPU 只查一次 ERPNext，后续行复用结果
3. **custom_model_id 查询** — 需在 filters 中带 doctype 前缀 `"Item Group"`（否则被权限校验拒绝）
4. **两步更新** — 下载 + `upload_file` (multipart 真实文件) + `PUT image` 缺一不可
5. **COS 防盗链** — 下载图片到本地再上传 ERPNext，绕过 COS 的 Referer 校验
6. **HTTP 重试** — 每个请求失败后重试 1 次 (3s 延迟)
7. **附件上限** — 每文档最多 3 个附件。≥3 时按 content_hash 找重复记录: 同 hash 的 image 字段记录只保留一条, 删其余 + hash=None 记录。非 image 字段附件 (如 PDF) 绝不删。无可安全清理的记录则跳过
8. **附件上限按文档** — 不是按字段: PDF 等挂在文档上 (attached_to_field=null) 也占 3 个名额
9. **凭证** — `.env` 文件 (gitignored) 或环境变量 `ERP_API_KEY` / `ERP_API_SECRET`

---

*若与代码不一致, 以 upload_item_images.py 为准。*
