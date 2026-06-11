# -*- coding: utf-8 -*-
"""创建重构用的 Commodities 数据源副本，将分类路径中「三角靠枕」替换为「三角靠枕类」。"""
import shutil
from pathlib import Path
import pandas as pd

_DIR = Path(__file__).resolve().parent
src = _DIR / "数据源" / "Commodities2026_06_09(1).xlsx"
dst = _DIR / "数据源" / "Commodities2026_06_09_重构版.xlsx"

# 复制原文件
shutil.copy2(src, dst)
print(f"已复制: {dst.name}")

# 修改分类列
df = pd.read_excel(dst, sheet_name=0)
cat_col = df.columns[2]  # 分类列
df[cat_col] = df[cat_col].apply(
    lambda x: str(x).strip().replace("三角靠枕", "三角靠枕类") if pd.notna(x) else x
)
df.to_excel(dst, index=False)

# 验证
paths = df[cat_col].dropna().unique()
print(f"\n替换后分类路径: {len(paths)} 条")
for p in sorted(paths):
    if '三角' in str(p) or '靠枕' in str(p):
        print(f"  {p}")

# 不含"三角靠枕"结尾的路径
has_old = any(str(p).strip().endswith("三角靠枕") for p in paths)
print(f"\n仍含「三角靠枕」结尾: {'是' if has_old else '否 ✓'}")
