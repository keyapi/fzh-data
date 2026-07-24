# NAS — Synology FileStation API 参考资料

> 记录时间: 2026-06-11 | 最后验证: 2026-06-11 (全部链接可用)

## 官方文档

| 资源 | 链接 | 说明 |
|------|------|------|
| **Synology File Station API Guide (PDF)** | https://global.download.synology.com/download/Document/Software/DeveloperGuide/Package/FileStation/All/enu/Synology_File_Station_API_Guide.pdf | 官方 API 完整文档 |
| **Synology Developer Center** | https://developer.synology.com | 开发者入口 |

## 开源 Python 库

| 项目 | 链接 | Stars | 说明 |
|------|------|-------|------|
| **N4S4/synology-api** | https://github.com/N4S4/synology-api | ~332 | ⭐ 最活跃 Python 封装，覆盖 FileStation/DownloadStation 等 300+ API |
| **N4S4 API 文档** | https://n4s4.github.io/synology-api/docs/apis/classes/filestation | — | `get_file()` 下载、`get_file_list()` 列表、`upload_file()` 上传 |
| **matthiasbock/python-synology-dsm** | https://github.com/matthiasbock/python-synology-dsm | — | 底层绑定，基于官方 API Guide PDF，适合学习原始调用 |

## 关键 API 调用方式

### Auth (登录获取 SID)

```
GET /webapi/auth.cgi
  ?api=SYNO.API.Auth&version=3&method=login
  &account={user}&passwd={pass}&session=FileStation&format=sid
→ { "success": true, "data": { "sid": "..." } }
```

### FileStation.List (列出目录)

```
GET /webapi/entry.cgi
  ?api=SYNO.FileStation.List&version=2&method=list
  &folder_path=/shared/folder
  &additional=thumbnail,size,time
  &_sid={sid}
→ { "success": true, "data": { "files": [...] } }
```

### FileStation.Thumb (获取缩略图)

```
GET /webapi/entry.cgi
  ?api=SYNO.FileStation.Thumb&version=2&method=get
  &path="{path}"           ← 注意: path 必须用双引号包裹!
  &size=small|medium|large
  &_sid={sid}
→ 直接返回图片二进制 (image/jpeg)
```

> ⚠️ **Synology API 特殊性**: `FileStation.Thumb` 的 `path` 必须用双引号包裹 `f'"{path}"'`，
> 与 `FileStation.List` 的 `folder_path` (不需要引号) 不同。
> 参考: vilavi_pim `nas.py:132` 注释 "Path must be wrapped in quotes per Synology API spec"

### FileStation.Download (下载文件)

```
GET /webapi/entry.cgi
  ?api=SYNO.FileStation.Download&version=2&method=download
  &path=["/shared/folder/file.jpg"]     ← JSON 数组格式 (单文件也如此)
  &mode=download                        ← "download" = 强制下载, "open" = 浏览器打开
  &_sid={sid}
→ 单个文件: 直接返回文件二进制
→ 多个文件: 返回 ZIP 压缩包
```

## 参考实现

| 项目 | 文件 | 行数 | 说明 |
|------|------|------|------|
| **vilavi_pim** (item_group_browser 分支) | `vilavi_pim/api/nas.py` | 180 行 | SynologyNAS 类: 登录/列表/缩略图 |
| **vilavi_pim** (item_group_browser 分支) | `vilavi_pim/public/js/item_group_nas.js` | 440 行 | 前端 NAS 浏览器: 左侧树+右侧网格/列表+灯箱预览 |
| **DAM 原型** | `dam-prototype/main.py:135-221` | — | 移植的 SynologyNAS 类 (基于 vilavi_pim) |
| **DAM 原型** | `dam-prototype/main.py:579-` | — | NAS API 端点 (browse/tree/thumbnail/import) |

## 凭证

| 字段 | 值 | 来源 |
|------|-----|------|
| NAS URL | `https://fzh.myds.me:11024` | `.env` (`NAS_URL`) |
| Username | `fzh.test` | `.env` (`NAS_USERNAME`) |
| Root Folder | `/FZH共享文件夹` | `.env` (`NAS_ROOT_FOLDER`) |

## Synology 文件扩展名支持 (缩略图)

来源: vilavi_pim `item_group_nas.js:331-332` (Synology FileStation API 官方文档)

```
jpg|jpeg|jpe|bmp|png|tif|tiff|gif|
arw|srf|sr2|dcr|k25|kdc|cr2|crw|nef|mrw|ptx|pef|raf|3fr|erf|mef|mos|orf|rw2|dng|x3f|heic|raw
```

## 经验教训

1. **Synology API 参数格式不一致**: 同一个 `/webapi/entry.cgi` 端点，不同 API 对 path 参数格式要求不同
2. **`has_thumbnail` 字段不可靠**: 不要依赖它判断是否加载缩略图，用文件扩展名判断
3. **`size=original` 可能不被支持**: 下载原图用 `SYNO.FileStation.Download`，不用 Thumb
4. **path 必须含 shared folder**: 如 `/FZH共享文件夹/...`，不能省略根路径
