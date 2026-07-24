"""
DingTalk Stream mode event listener for user offboarding.

Connects to DingTalk Stream (WebSocket), listens for `user_leave_org` events,
and disables the departed employee's new-api account.

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
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "new-api-root-pwd")
MYSQL_DB = os.getenv("MYSQL_DB", "new_api")

PROXY_DB_PATH = os.getenv(
    "PROXY_DB_PATH",
    "/data/sellfox-proxy/sellfox-proxy.db",
)


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
    """Look up a DingTalk user by userId via old API. Returns user info dict or None."""
    resp = httpx.post(
        f"https://oapi.dingtalk.com/topapi/v2/user/get?access_token={access_token}",
        json={"userid": user_id},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        return None
    return data.get("result", {})


# ── MySQL helpers ─────────────────────────────────────────────────────

def _get_db() -> pymysql.Connection:
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset="utf8mb4",
        connect_timeout=10,
    )


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


def disable_new_api_user(user_id: int):
    """Disable a new-api user account (sets status=2)."""
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
    Returns the number of keys disabled.
    """
    try:
        db = sqlite3.connect(PROXY_DB_PATH)
        cur = db.execute(
            "UPDATE api_keys SET is_active = 0 "
            "WHERE dingtalk_union_id = ? AND is_active = 1",
            (union_id,),
        )
        count = cur.rowcount
        db.commit()
        db.close()
        if count:
            logger.info(
                "disabled %d proxy key(s) for union_id=%s",
                count, union_id[:16],
            )
        return count
    except Exception as e:
        logger.warning("Failed to disable proxy keys for %s: %s", union_id[:16], e)
        return 0


# ── Event Handler ─────────────────────────────────────────────────────

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

        user_ids = event_data.get("UserId", [])
        if not user_ids:
            return dingtalk_stream.AckMessage.STATUS_OK, "no user_ids"

        try:
            access_token = get_app_access_token()
        except Exception as e:
            logger.error("failed to get app access token: %s", e)
            return dingtalk_stream.AckMessage.STATUS_LATER, "token_error"

        for uid in user_ids:
            try:
                user_info = get_user_by_id(uid, access_token)
                if user_info is None:
                    logger.warning("user %s not found in DingTalk", uid)
                    continue

                union_id = user_info.get("unionId")
                if not union_id:
                    logger.warning("no unionId for userId=%s", uid)
                    continue

                new_api_user_id = find_user_by_unionid(union_id)
                if new_api_user_id is None:
                    logger.info(
                        "dingtalk user %s (unionId=%s) not linked to any new-api account",
                        uid, union_id,
                    )
                    continue

                disable_new_api_user(new_api_user_id)
                disable_proxy_keys(union_id)
            except Exception as e:
                logger.error("error processing userId=%s: %s", uid, e)

        return dingtalk_stream.AckMessage.STATUS_OK, "OK"


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
