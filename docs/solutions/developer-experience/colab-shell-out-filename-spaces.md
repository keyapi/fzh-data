---
okf: v0.1
type: Reference
title: notebook 里别用 !shell 做文件操作——文件名含空格会让 !zip 静默失败
date: 2026-09-22
category: developer-experience
module: colab_kit
problem_type: developer_experience
component: tooling
severity: medium
symptoms:
  - "zip error: Nothing to do! （但生成的文件明明就在当前目录）"
  - "FileNotFoundError: Cannot find file: xxx.zip（上一个 !zip 明明'跑过了'）"
  - "打包下载这一步失败，前面 CSV / PDF 都生成成功了"
root_cause: "IPython 的 !cmd 是把字符串原样交给 shell，文件名里的空格被当作参数分隔符"
resolution_type: code_fix
tags: [colab, ipython, shell-quoting, zip, filename-with-spaces]
---

# notebook 里别用 `!shell` 做文件操作

## Problem

Colab/notebook 末尾那句 `!zip -q {zip_name} {" ".join(generated_files)}`，在上游产出的文件名**含空格**时必然失败：zip 收不到任何真实文件，于是不生成压缩包，紧接着的 `files.download(zip_name)` 抛 `FileNotFoundError`。

失败点离根因很远（报错在 download，原因在 zip），很容易误判成「下载坏了」。

## Symptoms

```
zip error: Nothing to do! (Overstock_CSV_背贴.zip)
---------------------------------------------------------------------------
FileNotFoundError: Cannot find file: Overstock_CSV_背贴.zip
```

- 前面几步全都打印了 ✅（csv 生成、背贴 PDF 生成、合并报告正常）；
- 只有最后的打包下载这一步崩；
- 手工 `ls` 能看到那些文件**确实存在**。

## What Didn't Work

- 怀疑 zip 没装 → 不成立，报错信息是 zip 自己发的（说明它跑起来了）；
- 怀疑文件名编码（中文）→ 不成立，去掉空格的中文名一直没事；
- 怀疑 `files.download` → 它只是受害者，找不到文件所以抛错。

## Solution

把 shell 调用换成 Python API，从根上消除分词问题：

```python
import zipfile

with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in generated_files:
        zf.write(f, arcname=os.path.basename(f))
```

（想保留 shell 就得逐个 `shlex.quote`，但 Python API 更短也更稳。）

**复现与验证**（不需要 Colab，纯本地就能证）：

```python
names = ["Overstock-...-351 每货品一行_UPS_....csv", "Overstock-...-351 每货品一行_背贴_....pdf"]
cmd = 'zip -q out_old.zip ' + " ".join(names)   # 模拟 !zip 展开
print(len(cmd.split()))                          # 7 个 token → zip 收到 5 个"文件名"，全是假的
```

换成上面的 `zipfile` 写法，两个含空格的文件都能进包。

## Why This Works

`!cmd` 是 IPython 魔法：它把整行**原样交给 shell**，shell 再按空白分词。文件名里的空格在 shell 看来和参数分隔符没有区别 —— 于是 `Overstock-20260922103049-351 每货品一行_UPS_....csv` 被切成 `Overstock-20260922103049-351` 和 `每货品一行_UPS_....csv` 两个不存在的路径。zip 找不到任何匹配的文件，就打印 `Nothing to do!` 并以非零码退出（但**不抛异常**，所以 `!` 那行看起来"过了"）。

Python 的 `zipfile` 直接收字符串列表，没有 shell 这一层，空格与原样字符串等价。

## Prevention

- **notebook 里凡是「把变量拼进 shell 命令」的地方，先问：这个变量的值可能含空格/引号/中文吗？** 会的话就别用 `!`，改用 Python API（`zipfile` / `shutil` / `pathlib`）。
- 业务同事**保存导出文件时会顺手加中文后缀**（`... 每包裹一行.xls`、`... 每货品一行.xls`）—— 这正是本次踩坑的来源。别假设上游文件名是「干净」的。
- 上游产出的文件名如果可以和业务命名解耦，把空格去掉也能顺带消除这一整类问题（本次没做，因为用户要靠中文后缀区分导出模板）。
- 排查此类问题的通用思路：**当报错点离根因很远时，先怀疑「上一步静默失败了」**，而不是怀疑报错的那一步。

## Related

- `developer-experience/colab-notebook-drive-api-editing.md` —— 同批改动同一个 notebook 的经验
- `colab_kit/`（`.agents/skills/colab-kit/`）—— Colab notebook 读写改工具箱（本坑是在改那个 notebook 时踩到的）
- `integration-issues/carrier-label-batch-field-length-limits.md` —— 同一条流水线里的另一个「长度/格式」坑
