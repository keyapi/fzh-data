# ERPNext File 存储架构 & NAS 集成调研

> 调研日期: 2026-06-10 | 参考: Frappe 源码, dfp_external_storage, vilavi_pim

---

## 一、ERPNext 原生 File 存储

### 1.1 架构: DB 层级 + 扁平物理文件

```
┌─────────────────────────────────────────────────────┐
│                 tabFile (DB 表)                      │
│  name | file_name | file_url | folder | is_folder   │
│  ─────|───────────|──────────|────────|──────────   │
│  Home | Home      | /files/..| null   | 1 (文件夹)   │
│  Att  | Attach..  | /files/..| Home   | 1           │
│  F001 | img.jpg   | /files/..| Att    | 0 (文件)    │
└──────────────────────┬──────────────────────────────┘
                       │ file_url → 物理路径映射
                       ▼
┌─────────────────────────────────────────────────────┐
│  物理磁盘 (完全扁平，无子目录)                         │
│  sites/{site}/public/files/{hashed_name}.ext         │
│  sites/{site}/private/files/{hashed_name}.ext        │
└─────────────────────────────────────────────────────┘
```

**关键理解**: 
- 所有文件物理上存在**同一个扁平目录**中，不按文件夹分子目录
- 文件夹层级**仅存在于 DB** 中，通过 `File` DocType 的 `folder` 字段（Link 到另一个 `File` 记录）形成树
- 文件夹本身也是 `File` 记录（`is_folder=1`）
- 文件 URL 格式: `/files/{hashed_name}.ext`（不含路径）

### 1.2 和对象存储 Bucket 的关系

ERPNext 原生存储**不是**对象存储。对象存储（S3/MinIO）的特点:
- 扁平 key-value 命名空间
- 通过 key 前缀模拟文件夹（如 `folder/subfolder/file.jpg`）
- 无真正的"目录"概念

dfp_external_storage 的作用是**桥接**:
```
Frappe File DocType (folder 层级)
        ↓
dfp_external_storage (路由层: 每个 folder 可映射到不同 S3 bucket)
        ↓
S3 Bucket (key = 文件标识符)
```

### 1.3 dfp_external_storage 架构

**核心概念: 按文件夹映射到 Bucket**

| 配置 | 行为 |
|------|------|
| 未配置 | 文件存本地磁盘（默认） |
| `Home` 文件夹 → S3 Bucket A | **所有**文件走 S3 |
| `Attachments` → S3 Bucket B | 仅附件走 S3 |
| Home + Attachments 同时配置 | Attachments 优先用 Bucket B，其余用 Bucket A |

**关键特性**:
- 上传直连 S3，不经过本地磁盘
- 支持流式传输（不整文件加载到内存）
- 支持 presigned URL（视频流、限时访问）
- 支持缓存（按大小 + TTL）
- 保留 Frappe 的 public/private 权限
- S3 不可达时自动回退到本地磁盘

**URL 模式**: `/file/{File ID}/{filename.ext}`

**我们 DAM 原型的启示**:
- 原型阶段用物理子目录 `files/{path}/{uuid}.ext` 足够
- 迁入 Frappe 后改用 DB 层级 + 扁平文件
- 如需云存储，安装 dfp_external_storage 即可透明切换

---

## 二、vilavi_pim NAS 集成 (Synology FileStation API)

### 2.1 已有实现

在 `vilavi_pim` 仓库（`develop` 分支 commit `7cb8229`）中:

| 文件 | 行数 | 作用 |
|------|------|------|
| `vilavi_pim/api/nas.py` | 160 | SynologyNAS 类 + API 端点 |
| `vilavi_pim/public/js/item_group_nas.js` | 249 | 前端 NAS 浏览器（Frappe Dialog） |
| `vilavi_pim/hooks.py` | - | 在 Item Group 表单注册 "Browse NAS" 按钮 |

**nas.py 核心设计**:

```python
class SynologyNAS:
    def __init__(self):
        # 从 PIM Settings DocType 读取配置
        self.settings = frappe.get_single("PIM Settings")
        self.base_url = self.settings.nas_url       # e.g. https://192.168.1.100:5001
        self.username = self.settings.nas_username
        self.password = self.settings.get_password('nas_password')
        self.is_webdav = self.settings.nas_is_webdav
        self.sid = None  # Session ID
        self._login()

    def _login(self):
        # POST /webapi/auth.cgi?api=SYNO.API.Auth&method=login
        # 获取 SID，缓存 1 小时到 Redis
        # 失败不抛异常（允许 WebDAV fallback）

    def get_file_list(self, folder_path, limit=1000, offset=0):
        # GET /webapi/entry.cgi?api=SYNO.FileStation.List&method=list
        # 参数: folder_path, offset, limit, sort_by=name, sort_direction=asc
        # additional=thumbnail,size,time
        # 返回标准化格式: name, path, is_dir, size, mtime, has_thumbnail

    def get_thumbnail_content(self, path, size='medium'):
        # GET /webapi/entry.cgi?api=SYNO.FileStation.Thumb&method=get
        # 返回原始图片内容
```

**item_group_nas.js 前端设计** (参考模板):

```
┌──────────────────────────────────────────────────┐
│  NAS File Browser                     [extra-large] │
├────────────┬─────────────────────────────────────┤
│  树侧栏     │  文件网格                            │
│  (300px)   │  (flex:1)                           │
│            │                                     │
│  📁 FZH共享 │  ┌──────┐ ┌──────┐ ┌──────┐       │
│    📁 产品  │  │📁子目录│ │🖼️图片│ │🖼️图片│       │
│    📁 设计  │  └──────┘ └──────┘ └──────┘       │
│    📁 运营  │                                     │
│            │  点击文件夹→导航进入                   │
│            │  点击图片→灯箱预览                     │
└────────────┴─────────────────────────────────────┘
```

### 2.2 适配到 DAM 原型

**后端适配** (`dam-prototype/main.py`):
- 将 `SynologyNAS` 类移植过来
- 凭证改用 `.env` 变量（而非 Frappe PIM Settings）:
  ```env
  NAS_URL=https://your-nas:5001
  NAS_USERNAME=your_username
  NAS_PASSWORD=your_password
  ```
- 提供 REST API:
  - `GET /api/nas/browse?path=` → 调用 `nas.get_file_list()`
  - `GET /api/nas/file/thumbnail?path=` → 调用 `nas.get_thumbnail_content()`，返回图片
  - `POST /api/nas/import` → 复制选中文件到 DAM

**前端适配** (`dam-prototype/static/index.html`):
- 替换当前的假 `Browse NAS` 模态框
- 使用 vilavi_pim 的树+网格布局（已验证可行）
- 点击图片→灯箱预览
- 选中复选框 + 导入按钮

---

## 三、存储模式对比

| 方案 | 物理结构 | 层级关系 | 适用阶段 |
|------|---------|---------|---------|
| **当前原型** | `files/{path}/{uuid}.ext` (子目录) | 物理目录树 | 原型验证 |
| **ERPNext 原生** | `files/{hash}.ext` (扁平) | DB `File.folder` 字段 | 迁入 Frappe |
| **dfp_external_storage** | S3 bucket (扁平 key-value) | Frappe folder → S3 bucket 映射 | 生产云存储 |
| **NAS 直连** | NAS 文件系统 (原始目录树) | 物理目录树 | 浏览导入源 |

**演进路径**:
```
原型 (物理子目录) → 迁入 Frappe (DB 层级 + 扁平文件) → 生产 (dfp_external_storage → S3)
                                                        ↘ 保留 NAS 浏览作为导入源
```

---

## 四、NAS 凭证配置

vilavi_pim 从 `PIM Settings` DocType 读取。DAM 原型改用 `.env`:

```bash
# NAS Integration (Synology FileStation API)
NAS_URL=https://192.168.x.x:5001
NAS_USERNAME=your_nas_user
NAS_PASSWORD=your_nas_password
# Optional: NAS root folder for browsing
NAS_ROOT_FOLDER=/FZH共享文件夹
```

**注意**: 真实凭证不应硬编码，`.env` 已在 `.gitignore` 中。

---

> 持续更新。下次调研: NAS 性能优化、缩略图缓存策略。
