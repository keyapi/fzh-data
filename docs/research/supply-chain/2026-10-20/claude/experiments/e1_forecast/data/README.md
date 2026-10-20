# E1 本地数据目录

`wedge_raw.csv` 与 `wedge_monthly.csv` 含 SKU 级发货明细，**不入库**（仓库规则禁止提交数据文件）。

重新生成：

```bash
cd ..
uv run python pull_data.py
```

`pull_log.txt` 只含月表名与命中行数，可入库。
