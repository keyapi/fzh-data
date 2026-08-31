# sps_api — SPS Commerce API 可行性探测

验证 SPS Commerce 能否用 API 自动化 Pottery Barn 的订单/ASN/发票/库存操作。

## 背景结论（来自官方 Dev Center 文档）

- SPS Dev Center 没有"下载订单/生成 ASN"这类门户按钮 API。这些操作本质是 EDI 单据
  （850 订单 / 856 ASN / 810 发票 / 846 库存），通过 **Transaction API**（HTTPS 版 FTP/AS2）
  交换文件，文件多为 RSX XML 格式。
- 供应商目录约定：
  - `out/` 零售商 → 供应商（订单在这里），`in/` 供应商 → 零售商（ASN/发票/库存在这里）
  - `testout/` `testin/` 为沙盒测试目录
- 认证：**Machine-to-Machine（client_credentials）** 流只需 App ID + App Secret，
  **不需要 Redirect URI**，适合 FZH 代表自己连接。若用 Web Service 类型 App（授权码流）
  则必须配 Redirect URI。
- **沙盒可用，生产数据需与 SPS 签约并获实施团队开通。**

## 使用

```bash
cd sps_api
python -m pip install python-dotenv   # 可选，未安装也能跑（.env 用系统环境变量替代）
python oauth.py                       # 用 client_credentials 拿 token，缓存到 token.json
python probe.py                       # 列 Transaction API 根目录
python probe.py out/PO/               # 列沙盒样例订单目录
python probe.py out/PO/ --download    # 下载第一个样例订单到 downloads/
```

## 文件

- `config.py` — 从 `.env` 读凭据与端点
- `oauth.py` — client_credentials 拿 token + 缓存复用
- `probe.py` — Transaction API 目录探测 / 文件下载
- `.env` — 凭据（**不提交 git**）
- `token.json` — 缓存的 token（**不提交 git**）

## 安全

- `.env` 已 gitignore。production 密钥绝不外泄/不提交。
- 若当前 App 的 client_credentials 被拒，需在 Dev Center 新建 Machine-to-Machine 类型 App。
