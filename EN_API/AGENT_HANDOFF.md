# EN_API — Agent 交接说明

> **脚本**: `upload_item_images.py` + `upload_local_images.py`
> **人读文档**: [README.md](README.md)

### 相关交接文档

| 文档 | 说明 |
|------|------|
| [AGENT_HANDOFF_物料组重构.md](AGENT_HANDOFF_物料组重构.md) | 赛狐分类 → EN 系统物料组重构 |
| [AGENT_HANDOFF_PIM_ANALYSIS.md](AGENT_HANDOFF_PIM_ANALYSIS.md) | PIM 图片缺失统计分析 |
| [AGENT_HANDOFF_NAS_ANALYSIS.md](AGENT_HANDOFF_NAS_ANALYSIS.md) | NAS 路径与物料组关联性分析 |
| [AGENT_HANDOFF_LG_QUERY.md](AGENT_HANDOFF_LG_QUERY.md) | LG 前缀物料组款式ID更新 |
| [AGENT_HANDOFF_独立站产品链接.md](AGENT_HANDOFF_独立站产品链接.md) | daneey.com 产品链接写入物料组 |

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

## 8. 脚本: `upload_local_images.py` — 本地图片批量上传

与 `upload_item_images.py`（赛狐 Excel → 更新物料组主图）不同，此脚本直接从本地目录读取图片文件，上传到 ERPNext 生成公开 URL（不绑定任何 doctype）。

**用途**: 同事需要图片 URL 用于销售平台贴图。

### 命令行

```bash
uv run python upload_local_images.py                       # 默认生产环境 (最常用)
uv run python upload_local_images.py --env test            # 开发测试用
uv run python upload_local_images.py -i D:/图片             # 自定义目录+生产
```

### 输出

`out/图片上传链接_{ts}.xlsx` — 单 sheet `图片链接`，列：文件名、file_url、完整链接

### 关键函数

| 函数 | 作用 |
|------|------|
| `ErpnextClient.upload_local_file(file_path)` | 读取本地文件 → POST upload_file → 返回 file_url |

---

## 9. ⚠️ 环境策略（重要）

### 用户分层

| 角色 | 认知 | 默认环境 | 说明 |
|------|------|---------|------|
| **普通同事** | 只知道生产环境 | prod | 直接运行，不需要知道 `--env` 参数 |
| **开发同事（你、个别开发）** | 知道有 test 环境 | 开发时手动 `--env test` | 测试通过后再切回 prod |

### AI / Codex / Agent 行为规则

1. **默认 `prod`** — 脚本的 `_DEFAULT_ENV = "prod"`，普通用户无感
2. **不要主动问"测试还是生产"** — 除非用户明确提到"测试/开发/test"，否则默认就是生产
3. **开发场景下用 `--env test`** — 你和开发同事在调试/测试时自行指定
4. **永远不要硬编码 URL** — 仍通过 `_ENV_URLS` 映射 + `--env` 参数切换

### 原因

- 大部分同事是普通用户，连"测试环境"这个概念都不知道
- 他们只需要跑脚本拿到结果，不需要额外的选择负担
- 测试/生产共用同一套 API 凭证，环境切换靠 URL 区分，没有权限屏障

---

## 10. 脚本: `image_upload_app.py` — Web 图片上传管理工具

面向电商运营同事的 Web UI，支持拖拽上传 + 缩略图排序 + Excel 下载。

### 启动

```bash
# 前台直接运行（唯一正确方式，不要用 Start-Job / Start-Process Hidden）
cd EN_API && uv run python image_upload_app.py

# 验证是否启动成功：终端必须看到 "Uvicorn running on http://127.0.0.1:8099"
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8099   # 应返回 200
```

> 已踩坑: ❌ `Start-Job` (PowerShell) — 端口 Listen 但外部不可达
> ❌ `Start-Process -WindowStyle Hidden` — 进程存活但端口不绑定
> ❌ `log_level="warning"` — 沉默启动，无法判断成功与否
> ✅ 唯一正确: 在当前终端直接 `uv run python image_upload_app.py`

浏览器自动打开后:
1. 拖拽/点击选择图片（可多次追加）→ 缩略图显示
2. 拖拽缩略图调整顺序（第1张=主图）
3. 页面顶部切换测试/生产环境
4. 点击"上传到ERPNext"→ 后端逐张上传 → 下载Excel

### 架构

- **后端**: FastAPI + `ErpnextClient`（复用同一认证+nginx417处理）
- **前端**: 单 HTML，FilePond 只负责投掷区；独立 `.thumb-grid` (CSS Grid `auto-fill` + SortableJS) 渲染缩略图
- **API**: `POST /api/upload-images` — 接收 multipart files + env + compress → 返回 Excel
- **响应式**: Grid `auto-fill minmax(130px, 1fr)` + `aspect-ratio: 1`，无需媒体查询自适应列数

### 压缩

默认启用客户端压缩（quality 85 + max 1500px），比 ERPNext 内置优化（2MB→111KB 过度压缩）更温和可控。

- CLI: `--no-compress` / `--quality` / `--max-size`
- Web: 页面上"压缩图片"复选框
- 安全保护: 压缩后若变大则保留原图

### 与 CLI 工具的关系

| 工具 | 适用场景 |
|------|---------|
| `upload_local_images.py` (CLI) | AI 自动调用、批处理、固定目录 |
| `image_upload_app.py` (Web) | 普通同事手动操作、不同文件夹选图、需要排序 |
