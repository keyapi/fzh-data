# -*- coding: utf-8 -*-
"""创建重构用的 Commodities 数据源副本，将分类路径中需要保护的叶子节点替换为 XXX类。

替换规则在 REPLACE_MAP 中配置，每次增加新的叶子节点修复时更新此字典。
"""
import shutil
from pathlib import Path
import pandas as pd

_DIR = Path(__file__).resolve().parent
src = _DIR / "数据源" / "Commodities2026_06_09(1).xlsx"
dst = _DIR / "数据源" / "Commodities2026_06_09_重构版.xlsx"

# ═══════════════════════════════════════════════════════════
# 叶子节点替换映射：需要保护的叶子 → 对应的组节点
# 每次按用户确认的叶子节点逐一添加
# ═══════════════════════════════════════════════════════════
REPLACE_MAP = {
    "三角靠枕": "三角靠枕类",
    "平条靠枕": "平条靠枕类",
}

# 复制原文件
shutil.copy2(src, dst)
print(f"已复制: {dst.name}")

# 修改分类列
df = pd.read_excel(dst, sheet_name=0)
cat_col = df.columns[2]  # 分类列

def replace_path(val):
    if pd.isna(val):
        return val
    s = str(val).strip()
    for old, new in REPLACE_MAP.items():
        s = s.replace(old, new)
    return s

df[cat_col] = df[cat_col].apply(replace_path)
df.to_excel(dst, index=False)

# 验证
paths = df[cat_col].dropna().unique()
print(f"\n替换后分类路径: {len(paths)} 条")
for p in sorted(paths):
    print(f"  {p}")

# 检查是否还有未替换的原名
for old_name in REPLACE_MAP:
    remaining = [p for p in paths if str(p).strip() == old_name]
    if remaining:
        print(f"⚠ 仍有「{old_name}」路径未替换: {remaining}")
    else:
        # 检查是否有旧名出现在路径中的任何位置
        contains_old = [p for p in paths if old_name in str(p)]
        if contains_old:
            print(f"✓ 「{old_name}」已替换，剩余出现: {contains_old}")
        else:
            print(f"✓ 「{old_name}」全部替换完成")
