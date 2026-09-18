"""
DingTalk Stream mode event listener for user offboarding.

Connects to DingTalk Stream (WebSocket), listens for `user_leave_org` events,
and disables the departed employee's new-api account + sellfox-proxy keys.

The `user_leave_org` event is authoritative — we never re-check DingTalk's
`active` field. To survive "user already removed from org" (which breaks live
UserId→unionId resolution), we resolve unionId from the local
`dingtalk_identity_map` table first, and only fall back to a live DingTalk call.

Usage: runs as a background thread inside the FastAPI bridge process.
"""

import logging
import os
import sqlite3
import threading
import time

import dingtalk_stream
import httpx
import pymysql

logger = logging.getLogger("dingtalk_stream")


# ── Config from env ──────────────────────────────────────────────────

DINGTALK_CLIENT_ID = os.getenv("DINGTALK_CLIENT_ID", "")
DINGTALK_CLIENT_SECRET = os.getenv("DINGTALK_CLIENT_SECRET", "")

MYSQL_HOST = os.getenv("MYSQL_HOST", "new-api-mysql")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = (
    os.getenv("MYSQL_PASSWORD")
    or os.getenv("MYSQL_ROOT_PASSWORD")   # 与 offboarding-check.py / .secrets.env 保持一致
    or "new-api-root-pwd"
)
MYSQL_DB = os.getenv("MYSQL_DB", "new_api")

PROXY_DB_PATH = os.getenv(
    "PROXY_DB_PATH",
    "/data/sellfox-proxy/sellfox-proxy.db",
)

# ── Schema (幂等，bridge 容器启动/首次事件时自动建) ─────────────────────

DDL_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS dingtalk_identity_map (
      union_id         VARCHAR(128) PRIMARY KEY,
      dingtalk_user_id VARCHAR(128) NOT NULL,
      display_name     VARCHAR(255),
      last_verified_ts INT NOT NULL,
      created_at       INT NOT NULL,
      KEY idx_dtmap_userid (dingtalk_user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS offboarding_audit (
      id INT AUTO_INCREMENT PRIMARY KEY,
      ts INT NOT NULL,
      channel ENUM('stream','daily','dryrun','manual') NOT NULL,
      union_id VARCHAR(128),
      new_api_user_id INT,
      username VARCHAR(128),
      dingtalk_user_id VARCHAR(128),
      proxy_keys_disabled INT NOT NULL DEFAULT 0,
      result VARCHAR(32) NOT NULL
    )
    """,
]


# ── DingTalk API helpers ─────────────────────────────────────────────

def get_app_access_token() -> str:
    """Obtain an app-level access token (client_credentials grant)."""
    resp = httpx.post(
        "https://api.dingtalk.com/v1.0/oauth2/accessToken",
        json={
            "appKey": DINGTALK_CLIENT_ID,
            "appSecret": DINGTALK_CLIENT_SECRET,
            "grantType": "client_credentials",
        },
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    data = resp.json()
    token = data.get("accessToken")
    if not token:
        raise RuntimeError(f"Failed to get app access token: {data}")
    return token


def get_user_by_id(user_id: str, access_token: str) -> dict | None:
    """Look up a DingTalk user by userId via old API.

    Returns user info dict, None if the user is gone (60121/60111),
    and raises on transient / permission errors so the event is redelivered.
    """
    resp = httpx.post(
        f"https://oapi.dingtalk.com/topapi/v2/user/get?access_token={access_token}",
        json={"userid": user_id},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    data = resp.json()
    errcode = data.get("errcode")
    try:
        errcode_i = int(errcode)
    except (TypeError, ValueError):
        raise RuntimeError(f"user/get bad errcode={errcode!r}") from None
    if errcode_i == 0:
        return data.get("result") or {}
    if errcode_i in (60121, 60111):
        return None
    raise RuntimeError(f"user/get errcode={errcode_i} {data.get('errmsg')}")


def get_user_id_by_union_id(union_id: str, access_token: str) -> str | None:
    """Resolve numeric DingTalk userId from a unionId (needs qyapi_get_member)."""
    resp = httpx.post(
        f"https://oapi.dingtalk.com/topapi/user/getbyunionid?access_token={access_token}",
        json={"unionid": union_id},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        return None
    return (data.get("result") or {}).get("userid")


def record_login_identity(union_id: str, display_name: str | None):
    """Best-effort: persist unionId↔numeric-userId mapping after a successful login.

    Stream `user_leave_org` events only carry the numeric userId; our accounts are
    keyed by unionId. Capturing the pair while the user is certainly still in the
    org lets the event handler disable them even if DingTalk no longer resolves
    the userId later. Never raises — login flow must not depend on this.
    """
    try:
        access_token = get_app_access_token()
        user_id = get_user_id_by_union_id(union_id, access_token)
        if not user_id:
            logger.warning("record_login_identity: no userId resolved for %s", union_id[:16])
            return
        ensure_schema()
        upsert_identity_map(union_id, user_id, display_name)
        logger.info("recorded identity map union_id=%s user_id=%s", union_id[:16], user_id)
    except Exception as e:
        logger.warning("record_login_identity failed (non-fatal): %s", e)


# ── MySQL helpers ─────────────────────────────────────────────────────

def _get_db() -> pymysql.Connection:
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset="utf8mb4",
        connect_timeout=10,
    )


def ensure_schema():
    """Create identity_map / audit tables if absent (idempotent)."""
    db = _get_db()
    try:
        with db.cursor() as cur:
            for ddl in DDL_TABLES:
                cur.execute(ddl.strip())
        db.commit()
    finally:
        db.close()


def find_user_by_unionid(union_id: str) -> int | None:
    """Return new-api user_id for a given DingTalk unionId, or None."""
    db = _get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM user_oauth_bindings "
                "WHERE provider_id = (SELECT id FROM custom_oauth_providers WHERE slug='dingtalk') "
                "AND provider_user_id = %s",
                (union_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        db.close()


def find_username_by_unionid(union_id: str) -> str | None:
    """Return new-api username for a unionId, or None (used for audit rows)."""
    db = _get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT u.username FROM users u "
                "JOIN user_oauth_bindings b ON u.id = b.user_id "
                "WHERE b.provider_id = (SELECT id FROM custom_oauth_providers WHERE slug='dingtalk') "
                "AND b.provider_user_id = %s",
                (union_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        db.close()


def lookup_union_id_by_user_id(dingtalk_user_id: str) -> str | None:
    """Resolve unionId from local identity map (no DingTalk call)."""
    db = _get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT union_id FROM dingtalk_identity_map "
                "WHERE dingtalk_user_id = %s",
                (dingtalk_user_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        db.close()


def upsert_identity_map(union_id: str, dingtalk_user_id: str, display_name: str | None):
    db = _get_db()
    now = int(time.time())
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO dingtalk_identity_map "
                "(union_id, dingtalk_user_id, display_name, last_verified_ts, created_at) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "dingtalk_user_id=VALUES(dingtalk_user_id), "
                "display_name=VALUES(display_name), "
                "last_verified_ts=VALUES(last_verified_ts)",
                (union_id, dingtalk_user_id, display_name, now, now),
            )
        db.commit()
    finally:
        db.close()


def delete_identity_map(union_id: str):
    db = _get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "DELETE FROM dingtalk_identity_map WHERE union_id = %s",
                (union_id,),
            )
        db.commit()
    finally:
        db.close()


def insert_audit(union_id: str | None, new_api_user_id: int | None, username: str | None,
                 dingtalk_user_id: str | None, proxy_keys_disabled: int, result: str):
    db = _get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO offboarding_audit "
                "(ts, channel, union_id, new_api_user_id, username, dingtalk_user_id, "
                " proxy_keys_disabled, result) "
                "VALUES (%s, 'stream', %s, %s, %s, %s, %s, %s)",
                (int(time.time()), union_id, new_api_user_id, username,
                 dingtalk_user_id, proxy_keys_disabled, result),
            )
        db.commit()
    finally:
        db.close()


def disable_new_api_user(user_id: int) -> bool:
    """Disable a new-api user account (sets status=2). Idempotent."""
    db = _get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE users SET status = 2 WHERE id = %s AND status = 1",
                (user_id,),
            )
            affected = cur.rowcount
            db.commit()
            if affected:
                logger.info(
                    "disabled new-api user_id=%d (dingtalk employee departed)",
                    user_id,
                )
            return affected > 0
    finally:
        db.close()


def disable_proxy_keys(union_id: str) -> int:
    """Disable all active proxy API keys for a departed DingTalk user.
    Returns the number of keys disabled. Raises if the proxy DB is unreachable,
    so the caller can return STATUS_LATER (DingTalk redelivers the event).
    """
    if not os.path.exists(PROXY_DB_PATH):
        raise RuntimeError(f"proxy DB not found: {PROXY_DB_PATH}")
    db = sqlite3.connect(PROXY_DB_PATH)
    try:
        cur = db.execute(
            "UPDATE api_keys SET is_active = 0 "
            "WHERE dingtalk_union_id = ? AND is_active = 1",
            (union_id,),
        )
        count = cur.rowcount
        db.commit()
        if count:
            logger.info(
                "disabled %d proxy key(s) for union_id=%s",
                count, union_id[:16],
            )
        return count
    finally:
        db.close()


# ── Event Handler ─────────────────────────────────────────────────────

class ProxyDisableError(Exception):
    """Proxy DB unreachable / api_keys missing — event must be redelivered."""


class OffboardingHandler(dingtalk_stream.EventHandler):
    """Handles DingTalk Stream events for employee offboarding."""

    async def process(self, event: dingtalk_stream.EventMessage):
        event_type = event.headers.event_type
        event_data = event.data

        logger.info(
            "stream event: type=%s, corpId=%s, data=%s",
            event_type,
            event.headers.event_corp_id,
            event_data,
        )

        if event_type != "user_leave_org":
            return dingtalk_stream.AckMessage.STATUS_OK, "ignored"

        user_ids = event_data.get("UserId") or event_data.get("userId") or []
        if not user_ids:
            return dingtalk_stream.AckMessage.STATUS_OK, "no user_ids"

        try:
            access_token = get_app_access_token()
        except Exception as e:
            logger.error("failed to get app access token: %s", e)
            return dingtalk_stream.AckMessage.STATUS_LATER, "token_error"

        try:
            ensure_schema()
        except Exception as e:
            # new-api 封号依赖 MySQL，DB 不可用则整体重投，而不是吞掉
            logger.error("ensure_schema failed: %s", e)
            return dingtalk_stream.AckMessage.STATUS_LATER, "schema_error"

        needs_retry = False
        for uid in user_ids:
            try:
                self._process_user(uid, access_token)
            except ProxyDisableError as e:
                # new-api 已封（幂等），但 proxy key 未封 → 整包重投直到 proxy 也成功
                logger.error("proxy disable needs redelivery for userId=%s: %s", uid, e)
                needs_retry = True
            except Exception as e:
                logger.error("error processing userId=%s: %s", uid, e)
                needs_retry = True

        if needs_retry:
            return dingtalk_stream.AckMessage.STATUS_LATER, "proxy_retry"
        return dingtalk_stream.AckMessage.STATUS_OK, "OK"

    def _process_user(self, user_id: str, access_token: str):
        """Disable a single departed user. Resolves unionId locally first.

        new-api 封号无条件先做（最关键的权限收回）；proxy 封号失败只触发重投。
        """
        union_id = lookup_union_id_by_user_id(user_id)
        display_name = None
        if union_id is None:
            # 本地映射缺失：尽量实时解析（事件到达早于移除时可成功）；命中则回填
            user_info = get_user_by_id(user_id, access_token)
            if user_info is None:
                logger.error(
                    "leave event userId=%s has no local mapping and DingTalk no "
                    "longer resolves it; depends on daily 60121 sweep",
                    user_id,
                )
                return
            union_id = user_info.get("unionId") or user_info.get("unionid")
            display_name = user_info.get("name")
            if not union_id:
                logger.warning("no unionId for userId=%s", user_id)
                return
            upsert_identity_map(union_id, user_id, display_name)

        new_api_user_id = find_user_by_unionid(union_id)
        username = find_username_by_unionid(union_id)
        if new_api_user_id is None:
            logger.info(
                "dingtalk user %s (unionId=%s) not linked to any new-api account",
                user_id, union_id,
            )
            insert_audit(union_id, None, username, user_id, 0, "departed")
            return

        disable_new_api_user(new_api_user_id)
        try:
            proxy_count = disable_proxy_keys(union_id)
        except Exception as e:
            insert_audit(union_id, new_api_user_id, username, user_id, 0, "proxy_pending")
            raise ProxyDisableError(str(e)) from e
        insert_audit(union_id, new_api_user_id, username, user_id, proxy_count, "disabled")
        delete_identity_map(union_id)


# ── Thread wrapper ────────────────────────────────────────────────────

def start_stream_listener():
    """Start DingTalk Stream listener in a background thread. Blocks until connected."""

    if not DINGTALK_CLIENT_ID or not DINGTALK_CLIENT_SECRET:
        logger.warning("DINGTALK_CLIENT_ID/CLIENT_SECRET not set, stream listener disabled")
        return

    credential = dingtalk_stream.Credential(DINGTALK_CLIENT_ID, DINGTALK_CLIENT_SECRET)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_all_event_handler(OffboardingHandler())

    logger.info("Starting DingTalk Stream listener...")

    def _run():
        while True:
            try:
                client.start_forever()
            except Exception as e:
                logger.error("Stream connection lost: %s, reconnecting in 30s...", e)
                time.sleep(30)

    thread = threading.Thread(target=_run, daemon=True, name="dingtalk-stream")
    thread.start()
    logger.info("DingTalk Stream listener started in background thread")
