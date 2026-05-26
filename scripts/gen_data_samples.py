"""
gen_data_samples.py — 从真实数据源生成脱敏样例文件

## 何时执行

以下任一情况发生时，运行此脚本更新 数据源样例/：

1. **首次克隆仓库后** — 把真实数据文件放入各模块的 数据源/，然后运行
2. **数据源的列结构发生变化** — 系统导出的 Excel 加了新列、改了列名
3. **新增了数据源文件** — 某个模块的 数据源/ 多了新类型的输入文件

## 运行方式

    cd fzh-data
    uv run python scripts/gen_data_samples.py

## 行为

- 遍历每个模块的 数据源/*.xlsx（排除 ~$ 临时文件）
- 读取每个文件的全部列 + 前 3 行真实数据
- 数据值脱敏替换（SKU→示例编码、金额→取整、文本→通用描述）
- 输出到 数据源样例/{原文件名}_样例.xlsx
- 保留空单元格（NaN/None 不填假值）
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import re
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MODULES = ["multi_attr_saihu", "category", "item_cost_sx", "item_weight_size", "stock_init", "warehouse_restock", "other_outbound", "EN_API"]

SKU_PATTERN = re.compile(r'^[A-Za-z0-9]+-[A-Za-z0-9\-_]+$')
CN_PATTERN = re.compile(r'[一-鿿]')

def _fake_sku(s: str) -> str:
    """生成格式相似的假 SKU。"""
    parts = s.split("-")
    out = []
    for i, p in enumerate(parts):
        if i == 0:
            out.append(f"KS{abs(hash(p)) % 9999:04d}")
        else:
            out.append(f"X{abs(hash(p)) % 99:02d}")
    return "-".join(out)

def _fake_text(s: str) -> str:
    """生成不泄露真实信息的假文本。"""
    if any('一' <= c <= '鿿' for c in s):
        return f"示例{abs(hash(s)) % 100:02d}"
    return f"sample-{abs(hash(s)) % 1000:03d}"

def _fake_number(n: float) -> float:
    """数值取整扰动，不泄露精确成本。"""
    if abs(n) < 0.01:
        return 0.0
    if abs(n) < 1:
        return round(random.uniform(0.5, 0.99), 2)
    magnitude = 10 ** (len(str(int(abs(n)))) - 1)
    return round(n / magnitude) * magnitude + random.randint(0, int(magnitude) - 1)

def anonymize(val):
    """脱敏单个单元格值。"""
    if pd.isna(val) or val is None or val == "":
        return val

    s = str(val).strip()

    # 数字（整数或浮点）
    try:
        n = float(s)
        if n == int(n) and n == 0:
            return 0
        if n == int(n) and n in (1,):
            return 1  # 保持 0/1 布尔语义
        return _fake_number(n)
    except ValueError:
        pass

    # SKU 类编码
    if SKU_PATTERN.match(s) and len(s) >= 6:
        return _fake_sku(s)

    # 中文文本
    if CN_PATTERN.search(s):
        return _fake_text(s)

    # 普通文本
    return _fake_text(s)

def process_module(module: str) -> int:
    """处理单个模块：读 数据源/ 所有 xlsx → 写 数据源样例/。返回处理的文件数。"""
    src_dir = BASE / module / "数据源"
    dst_dir = BASE / module / "数据源样例"

    if not src_dir.exists():
        print(f"  {module}: 数据源/ 目录不存在，跳过")
        return 0

    xlsx_files = sorted(
        f for f in src_dir.glob("*.xlsx")
        if not f.name.startswith("~$")
    )

    if not xlsx_files:
        print(f"  {module}: 数据源/ 无 xlsx 文件，跳过")
        return 0

    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for f in xlsx_files:
        try:
            df = pd.read_excel(f, nrows=3)
        except Exception as e:
            print(f"  {module}: 读取 {f.name} 失败 — {e}")
            continue

        if df.empty:
            print(f"  {module}: {f.name} 为空，跳过")
            continue

        # 脱敏每个单元格
        df_fake = df.map(anonymize)

        out_name = f"{f.stem}_样例.xlsx"
        out_path = dst_dir / out_name
        df_fake.to_excel(out_path, index=False)
        print(f"  {module}: {out_name} ({len(df_fake.columns)} 列 × {len(df_fake)} 行)")
        count += 1

    return count

def main():
    random.seed(42)
    print("gen_data_samples — 从 数据源/ 生成脱敏样例到 数据源样例/\n")

    total = 0
    for module in MODULES:
        n = process_module(module)
        total += n

    print(f"\n完成: 共生成 {total} 个样例文件。")
    if total == 0:
        print("提示: 请先在各模块的 数据源/ 目录下放入真实 Excel 文件，再运行此脚本。")

if __name__ == "__main__":
    main()
