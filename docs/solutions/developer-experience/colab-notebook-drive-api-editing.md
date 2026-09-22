---
okf: v0.1
type: Reference
title: 用 Drive API 改同事的 Colab notebook（.ipynb）——cell 插入、回读比对、并发守卫
date: 2026-09-22
category: developer-experience
module: google_drive_permissions
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "要改一个放在 Google Drive 上的 Colab notebook 代码，而不是让用户手点"
  - "要给 notebook 里的某个 cell「先备份再改」"
  - "改完要证明「只动了我该动的那一格，没顺手改坏别的」"
tags: [colab, ipynb, google-drive-api, notebook-editing, backup]
---

# 用 Drive API 改 Colab notebook

## Context

业务同事的 Colab notebook（例如「通途订单 → UPS/FedEx 批量面单 csv + 背贴 PDF」这类流水线）是**登录墙后面的 Web UI**：`colab.research.google.com/drive/<id>` 用 WebFetch 只能拿到 Google 登录页。要可复现地读它的代码、或做「先备份 cell 再改」这类操作，只能走 Drive API。

关键认知：**`.ipynb` 在 Drive 里就是一个 JSON 文件，没有专门 API**（同 `google_drive_permissions/docs/lessons.md` Lesson 2：改内容才分家，spreadsheet → Sheets API，`.ipynb` → Drive `files.get/update`）。

## Guidance（本学习沉淀的做法）

**1. 读要 `alt=media`，不要 `/export`。**

```
GET https://www.googleapis.com/drive/v3/files/{id}?alt=media&supportsAllDrives=true
```

`/export?mimeType=application/x-ipynb+json` 对 Colab 文件返回 `403 Export only supports Docs editors files` —— 因为 Colab 的 mimeType 是 `application/vnd.google.colaboratory`，不算 Docs Editors 文件。

**2. 写要用 multipart 并显式带 mimeType**，否则可能被改掉文件类型：

```python
MediaIoBaseUpload(io.BytesIO(nb_json.encode("utf-8")), mimetype="application/json", resumable=False)
svc.files().update(fileId=NB, body={"mimeType": "application/vnd.google.colaboratory"},
                   media_body=media, supportsAllDrives=True).execute()
```

**3. 定位 cell 用「断言唯一命中」，不要用行号硬编码。**
notebook 的 `source` 是**行列表**。按 `strip()` 等值或前缀匹配找锚点，并且**断言只命中一次**（commented-out 的老代码常与生效代码只差一个 `#`，很容易误伤）：

```python
hits = [i for i, l in enumerate(src) if l.strip() == "merged_sku = ', '.join(sku_qty_list)"]
assert len(hits) == 1, hits
```

插入新 cell 要补齐 nbformat 4.5+ 要求的字段：`id`（唯一）、`metadata`、`execution_count`、`outputs`。

**4. 写完必须回读比对 —— 这是最便宜的保险。**
重新下载一次，逐段断言「除了我要改的那一格，其余 cell 的 JSON 字符串逐字相等」：

```python
assert json.dumps(nb2["cells"][:5], ensure_ascii=False) == json.dumps(old["cells"][:5], ensure_ascii=False)
assert json.dumps(nb2["cells"][6:], ensure_ascii=False) == json.dumps(old["cells"][6:], ensure_ascii=False)
assert nb2["cells"][5]["source"] == new_src
```

一句话证明「只改了 cell 5，另外 30 格一字未动」——比肉眼看 diff 可靠。

**5. 并发守卫：写前先比 `modifiedTime`。**
用户很可能**同时开着 Colab 标签页**。写前 `files.get(fields="modifiedTime")` 与上次读到的值比对，不等就中止并让用户刷新。实测会动：用户跑一次 cell，Colab 把**执行输出**存回文件 —— `modifiedTime` 就变了，即使代码没改。

**6. 语法自检要中和 IPython 魔法行，且保留缩进。**
整格 `compile()` 之前，把 `!cmd` 这类魔法行换成 `pass  # !cmd`，**注意保留原有缩进**：

```python
def neutral(l):
    return l[:len(l) - len(l.lstrip())] + "pass  # " + l.lstrip() if l.lstrip().startswith("!") else l
compile(neutralized_src, "<cell>", "exec")
```

丢掉缩进会得到假的 `IndentationError`（实测踩过，白折腾一轮）。

**7. 「先备份再改」的落点：notebook 自己的约定。**
很多业务 notebook 底部有 `## 下面老代码，不用运行` 这类区块。把改动前那格的**全文逐字复制**成一个新 cell 放在那里（前面再加一个 markdown 说明），既符合原作者的收纳习惯，也比"存到本地"更让人看得见。实测一次：29 → 31 cells。

**8. ⚠️ 私钥风险：notebook 常把凭证内嵌在某个 cell 里。**
业务 notebook 通病 —— 顶部「必点！安装依赖」那个 cell 里塞着 `credentials` 字典（服务账号私钥）。因此：

- 本地兜底备份**必须放在仓库外**（本次放 `~/.claude/backups/<topic>/`），绝不进 git；
- 别把 notebook 原文贴进任何提交的文档。

## Why This Matters

- 这是**别人的活文档**：改坏一个 cell，用户下次点运行就直接报错，而且他不知道为什么。
- 「只动了我该动的」这个断言是唯一能自证清白的证据 —— 尤其在用户同时编辑、notebook 被反复保存的情况下。
- 内嵌私钥这一点如果忽略，一次"顺手备份到仓库"就是凭证泄露。

## When to Apply

- 要改的是 Colab notebook 代码而不是自建脚本。
- 用户明确要求「改之前先备份那一格」。
- 需要给一个非工程的业务 notebook 做**外科手术式**改动（改一格、留痕、可回溯）。

## Examples

一次真实改动（29 → 31 cells）：

1. 下载 JSON + 存仓库外兜底备份 + 记下 `modifiedTime`；
2. 在 `## 下面老代码` 之后插入 markdown 说明 + 原 cell 全文副本；
3. 写回 → 重新下载 → 断言「31 格、另外 29 格逐字未变、备份格 == 原 cell」；
4. 第二轮再改原 cell（加长度截断），守卫比对 `modifiedTime` —— 发现**已被用户的运行改动**，说明开着的标签页在回写执行输出 ⇒ 改完提示用户先 F5 刷新再跑。

配套坑：notebook 里的打包代码用 `!zip`（shell）在文件名含空格时静默失败，见 `developer-experience/colab-shell-out-filename-spaces.md`。

## 参考

- `google_drive_permissions/docs/lessons.md` —— Lesson 2（权限接口 vs 内容接口）、Lesson 6（PII 治理）
- `google_drive_permissions/scripts/check_colab_capabilities.py` —— 业务 Colab notebook 的 name → id 登记表
- 同批学习：`integration-issues/carrier-label-batch-field-length-limits.md`
- `sellfox_shipping/docs/research/colab-notebook-legacy-summary-2026-07-17.md` —— 另一个 Colab notebook 的逻辑摘要（含迁移到仓库的先例）
