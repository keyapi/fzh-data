# Local secrets (gitignored JSON)

Put machine-local credential files here. JSON files are gitignored; this README is not.

| File | Used by | How to create |
|------|---------|----------------|
| `secrets/gsheets-service-account.json` | `tongtool_order_cost` Google Sheet 读写 | `uv run python tongtool_order_cost/scripts/bootstrap_gsheets_credentials.py` |

Never commit service-account JSON, private keys, or filled `.env` files.
