# other_outbound — 赛狐其他出库导入

从赛狐库存明细导出生成其他出库单，清零库存。

## 快速运行

```bash
cd other_outbound
uv run python build_saihu_other_outbound.py
```

## 管道

```
赛狐库存明细导出 → 过滤非零库存 → 过滤组合商品(-ALL后缀)
    → 填入出库模板 → 输出 3 仓文件
```

## 前置条件

**操作前必须从赛狐重新导出库存明细**（库存会因出入库变化），放入 `数据源/`。

## 输出

- `赛狐_其他出库_导入_CENTRADE_{stamp}.xlsx`
- `赛狐_其他出库_导入_DANEEY_{stamp}.xlsx`
- `赛狐_其他出库_导入_POLAND_{stamp}.xlsx`

## 注意事项

- 组合商品（-ALL 后缀）不支持其他出库，自动跳过
- 导入后需去赛狐页面手动"确认出库"
- 出库后库存归零，赛狐"隐藏0数据"开时看不到
