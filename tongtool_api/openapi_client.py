# -*- coding: utf-8 -*-
"""通途 ERP2 OpenAPI 最小客户端（MCP 停用时的替代路径）。

2026-11-03 起通途 MCP 网关对所有 app_key 返回 524；同一凭证的 OpenAPI 正常。

认证（open-platform-service）：
  1. GET {auth}/devApp/appToken?accessKey&secretAccessKey → datas = app_token
  2. GET {auth}/partnerOpenInfo/getAppBuyerList?app_token&timestamp&sign
     sign = md5("app_token{token}timestamp{ts}{secret}") → datas[0].partnerOpenId = merchantId

业务（api-service）：
  POST {base}/openapi/tongtool/{method}
      query: app_token / sign / timestamp；body 追加 merchantId

限制：商户级 5 次/分钟（多 App 共享）。默认每次调用间隔 min_interval 秒；业务码 526 指数退避重试，
其余非 200（524 未授权 / 525 参数错…）直接抛 `TongToolApiError`，不重试。
"""

from __future__ import annotations

import hashlib
import time

import requests

AUTH_URL = "https://open.tongtool.com/open-platform-service"
API_BASE = "https://open.tongtool.com/api-service"

CODE_OK = 200
CODE_RATE_LIMIT = 526


class TongToolApiError(Exception):
    """通途业务错误（带业务码）。"""

    def __init__(self, code: int, message: str, payload: dict | None = None):
        self.code = code
        self.message = message
        self.payload = payload
        super().__init__(f"通途 API {code}: {message}")


def make_sign(app_token: str, timestamp: int, app_secret: str) -> str:
    """通途签名：md5("app_token{token}timestamp{ts}{secret}")。"""
    return hashlib.md5(
        f"app_token{app_token}timestamp{timestamp}{app_secret}".encode()
    ).hexdigest()


class TongtoolOpenApiClient:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        base_url: str = API_BASE,
        auth_url: str = AUTH_URL,
        min_interval: float = 13.0,
        max_retries: int = 3,
        sleep=time.sleep,
        session=None,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.auth_url = auth_url.rstrip("/")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._sleep = sleep
        self.session = session or requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "api_version": "3.0",
        })
        self.app_token: str | None = None
        self.merchant_id: str | None = None
        self.sign: str | None = None
        self.timestamp: int | None = None
        self._last_call = 0.0

    def authenticate(self) -> str:
        """取得 app_token 与 merchantId；返回 merchantId。"""
        resp = self.session.get(
            f"{self.auth_url}/devApp/appToken",
            params={"accessKey": self.app_key, "secretAccessKey": self.app_secret},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise TongToolApiError(data.get("code") or 0, data.get("message") or "认证失败", data)
        self.app_token = data["datas"]
        self.timestamp = int(time.time())
        self.sign = make_sign(self.app_token, self.timestamp, self.app_secret)

        mresp = self.session.get(
            f"{self.auth_url}/partnerOpenInfo/getAppBuyerList",
            params={"app_token": self.app_token, "timestamp": self.timestamp, "sign": self.sign},
            timeout=30,
        )
        mresp.raise_for_status()
        mdata = mresp.json()
        if not mdata.get("success") or not mdata.get("datas"):
            raise TongToolApiError(mdata.get("code") or 0, mdata.get("message") or "没有商户信息", mdata)
        self.merchant_id = mdata["datas"][0]["partnerOpenId"]
        return self.merchant_id

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def request(self, method_path: str, body: dict | None = None) -> dict:
        """POST 一个业务接口，返回业务 payload（code=200）。526 退避重试。"""
        if not self.app_token:
            self.authenticate()
        params = {
            "app_token": self.app_token,
            "sign": self.sign,
            "timestamp": str(self.timestamp),
        }
        payload = dict(body or {})
        payload.setdefault("merchantId", self.merchant_id)

        delay = 60.0
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = self.session.post(
                    f"{self.base_url}{method_path}", params=params, json=payload, timeout=60
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise TongToolApiError(0, f"请求失败: {exc}") from exc
                self._sleep(delay)
                delay = min(delay * 2, 300)
                continue

            code = data.get("code")
            if code == CODE_OK:
                return data
            if code == CODE_RATE_LIMIT:
                last_error = TongToolApiError(code, data.get("message") or "接口请求超频", data)
                if attempt >= self.max_retries:
                    break
                self._sleep(delay)
                delay = min(delay * 2, 300)
                continue
            raise TongToolApiError(code or 0, data.get("message") or "未知错误", data)
        raise last_error or TongToolApiError(CODE_RATE_LIMIT, "超频重试失败")

    def stocks(self, warehouse_name: str, page_no: int = 1, page_size: int = 100) -> dict:
        return self.request(
            "/openapi/tongtool/stocksQuery",
            {"warehouseName": warehouse_name, "pageNo": page_no, "pageSize": page_size},
        )

    def warehouses(self, page_no: int = 1, page_size: int = 200) -> dict:
        return self.request(
            "/openapi/tongtool/warehouseQuery",
            {"pageNo": page_no, "pageSize": page_size},
        )
