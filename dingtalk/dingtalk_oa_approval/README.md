# dingtalk_oa_approval — 钉钉 OA 销售收款确认单附件

从钉钉审批拉取「账期明细」txt/csv/xlsx/pdf（跳过图片、已撤销、拒绝），按 `fileId` 落盘，并对照 DRM 按人名归档的 NAS 账期桶。

**不要改本地 `D:\NAS与我共享\`。** 搬文件只能在 NAS 上操作。

凭证：复制 `.env.example` 为 `.env`，或设置 `DINGTALK_OA_ENV`。人名文件夹映射复制 `person_folders.example.json` 为 `person_folders.local.json`。NAS 账号只放 `NAS_API/.env`。

```text
uv run python dingtalk/dingtalk_oa_approval/fetch_attachments.py --start 2026-07-04
uv run python dingtalk/dingtalk_oa_approval/filter_export_by_period.py --in <xlsx> --period 2026-07 --out <xlsx>
uv run python dingtalk/dingtalk_oa_approval/july_amz_by_account.py
```

详见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md) 与 [docs/index.md](docs/index.md)。7 月 Amazon 对照：[docs/research/2026-09-10-july-amazon-period-reconcile.md](docs/research/2026-09-10-july-amazon-period-reconcile.md)。API + aflow + NAS 流水线：[docs/research/browser-admin-download.md](docs/research/browser-admin-download.md)。
