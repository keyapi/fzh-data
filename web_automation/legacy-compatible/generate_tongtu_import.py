#!/usr/bin/env python3
"""
通途库存导入文件生成器
从库存结存清单提取 SKU、头程运费、其他费用，按模板格式生成可导入通途的 Excel。
"""

import sys, os
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

TEMPLATE_COLS = ['SKU/SKU别名(必填)', '安全库存', '头程报关费（CNY）', '头程运费（CNY）', '其他费用（CNY）']

def read_inventory(path):
    """读取库存结存清单，返回 (sku_list, first_leg_list, other_fee_list)"""
    df = pd.read_excel(path, header=None)
    
    # 找到真正表头行（第1列为'SKU'的行）
    header_idx = df[df.iloc[:, 0].astype(str).str.strip() == 'SKU'].index[0]
    df.columns = df.iloc[header_idx].astype(str).str.replace('\n', '').str.strip()
    df = df.iloc[header_idx + 1:]  # 数据从表头下一行开始
    
    # 找到目标列
    sku_col = 'SKU'
    freight_col = [c for c in df.columns if '头程运费' in c][0]
    other_col = [c for c in df.columns if '头程其它费' in c or '其他费用' in c or '其它费用' in c][0]
    
    # 提取数据，跳过汇总行
    df = df[~df[sku_col].astype(str).str.strip().isin(['数量总计', '金额总计', '', 'nan'])]
    df = df[df[sku_col].notna()]
    
    return df[sku_col].tolist(), df[freight_col].tolist(), df[other_col].tolist()


def generate_import(skus, freights, others, output_path):
    """生成符合模板的导入文件"""
    out = pd.DataFrame({
        TEMPLATE_COLS[0]: skus,
        TEMPLATE_COLS[1]: None,       # 安全库存 → 留空
        TEMPLATE_COLS[2]: None,       # 头程报关费 → 留空
        TEMPLATE_COLS[3]: freights,
        TEMPLATE_COLS[4]: others,
    })
    out.to_excel(output_path, index=False, sheet_name='Sheet1')
    print(f"[完成] 已保存: {output_path}  ({len(skus)} 行)")


def main():
    folder = os.path.dirname(os.path.abspath(__file__))
    inv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(folder, "库存结存清单2026-04-2911_36_40.xlsx")
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(folder, "通途导入_头程运费_其他费用.xlsx")
    
    skus, freights, others = read_inventory(inv_path)
    
    print(f"共 {len(skus)} 个 SKU")
    for s, f, o in zip(skus[:5], freights[:5], others[:5]):
        print(f"  {s}  运费={f}  其他={o}")
    
    generate_import(skus, freights, others, out_path)
    
    # 快速校验
    check = pd.read_excel(out_path)
    assert list(check.columns) == TEMPLATE_COLS, "表头不匹配！"
    assert check[TEMPLATE_COLS[1]].isna().all(), "安全库存有值！"
    assert check[TEMPLATE_COLS[2]].isna().all(), "头程报关费有值！"
    assert check[TEMPLATE_COLS[0]].notna().all(), "SKU有空值！"
    print("[OK] 校验全部通过")


if __name__ == '__main__':
    main()
