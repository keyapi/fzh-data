#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON API 的统一错误结构。"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        hint: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details


def error_body(code: str, message: str, hint: str | None = None,
               details: Any = None, request_id: str = "") -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if hint:
        error["hint"] = hint
    if details is not None:
        error["details"] = details
    if request_id:
        error["request_id"] = request_id
    return {"error": error}
