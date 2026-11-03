# Local secrets (gitignored JSON)

Put machine-local credential files here. JSON files are gitignored; this README is not.

| File | Used by | How to create |
|------|---------|----------------|
| `secrets/gsheets-service-account.json` | `tongtool_order_cost`、`drive_folder_ops`、`colab_kit` | `uv run python tongtool_order_cost/scripts/bootstrap_gsheets_credentials.py` |

Env override: `GSPREAD_SERVICE_ACCOUNT_FILE`（相对路径按当前目录解析）。
`drive_folder_ops` 也会从脚本位置向上查找本文件，所以 worktree 里能直接用父仓库的凭证。

Never commit service-account JSON, private keys, or filled `.env` files.
