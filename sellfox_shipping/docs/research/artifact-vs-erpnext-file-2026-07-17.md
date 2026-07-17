---
okf: v0.1
type: Research
title: Artifact 存储与 ERPNext File 对照
description: 说明本模块 shipping_artifacts 与 ERPNext File doctype 的异同（扁平路径、private/files、content_hash）；含 SHA-256 vs MD5 取舍
timestamp: 2026-07-17
tags: [sellfox-shipping, artifact, erpnext, file, content-hash]
---

# Artifact 存储 ↔ ERPNext File

## ERPNext File（用户观察 / 生产习惯）

| 点 | ERPNext |
|----|---------|
| 布局 | **扁平**：`/private/files/…` 或公开 `/files/…` |
| URL 名 | 可读文件名（可含中文、空格）；例 `/private/files/EN系统订单模板c9d39c.xlsx`、`/files/泰迪熊.jpg` |
| content_hash | 多为 **MD5**（32 hex），不是 SHA-256；例 `7191dfa6e28d8ca6162ea35854dabdd7` |
| 去重 | 同 hash 往往共用底层对象；多条 File 可用不同 `file_name` 挂到不同单据 |
| folder | **虚拟**目录，不必然等于真实磁盘路径 |

## 本模块 `shipping_artifacts`（现行）

| 点 | sellfox_shipping |
|----|------------------|
| 布局 | `data/artifacts/private/files/{stem}_{hash8}{ext}`（扁平；旧版曾用 `by-hash/xx/sha256`） |
| 显示名 | `file_name` 字段；下载时用此名 |
| content_hash | **SHA-256**（64 hex） |
| 去重 | 同 `content_hash` → 同一 `storage_relpath` blob；多条 Artifact 可不同 `file_name` / `virtual_folder` |
| virtual_folder | 如 `lizard/export`、`lizard/import`，仅分类，不改物理路径 |
| 可见性 | 本地 Web `/lizard/artifacts`；尚无公网 `/files` vs `/private` 分流（单机内网） |

## content_hash：为何当前用 SHA-256、为何没硬对齐 EN MD5

### 先澄清：64 hex ≠「比 32 位更强」的笼统说法

- **32 hex / 64 hex 只是摘要长度的十六进制写法**：MD5 = 128 bit → 32 hex；SHA-256 = 256 bit → 64 hex。
- 优势来自**算法性质**（抗碰撞、抗预镜像），不是「位数多就一定更好用」。
- 对本模块的主用途——**同内容只存一份 blob、核对下载是否同一文件**——在信任操作员、无公网对抗场景下，**MD5 实务上通常也够用**。

### 当初选 SHA-256 的理由（偏保守，非硬需求）

1. Python 标准库一行即可；Excel/PDF 体积小，算力可忽略。
2. 行业默认：新系统做内容指纹时更常选 SHA-256，避免日后被问「为何用已破 MD5」。
3. 当时没有「必须与 ERPNext `content_hash` 字段逐字比对」的需求。

### 硬对齐 EN MD5 的代价与收益

| | 对齐 MD5 | 保持 SHA-256 |
|--|----------|--------------|
| 与 EN File 同值比对 | 可直接比 `content_hash` | 需另算 MD5 或存双 hash |
| 碰撞抗性 | 弱（理论可构造碰撞） | 强 |
| 本模块去重够不够 | **够**（内网、操作员可控） | 够，且余量更大 |
| 运维习惯 | 与 EN 一致 | 需在文档标明「本系统 SHA-256」 |

**结论（2026-07-17）：**

- **64 不一定「一定」优于 32**——对我们当前威胁模型，MD5 去重足够。
- **不对齐不是技术禁忌**，是「尚无跨系统 hash 对账」下的默认；若后续要把 EN 附件与打单制品按 hash 互认，**应改存 MD5，或同时存 `content_hash_md5` + `content_hash_sha256`**。
- 用户若明确要求与 EN 对齐，优先改 MD5（或双写），不要为对齐而假装 SHA-256「必须」。

## 设计取舍（路径 / 权限）

- **保留扁平 private/files**：便于人肉在磁盘上辨认；短 hash 后缀防同名撞车。
- **不做完整 EN File 权限模型**：P1 无对外 CDN；一律按私有制品处理。
- **`/files` 公开分流**：暂不做；全部走本机 Web 鉴权前的内网访问。
