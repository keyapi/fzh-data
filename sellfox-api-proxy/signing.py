import hashlib
import hmac
import random
import time


def compute_sign(
    access_token: str,
    client_id: str,
    client_secret: str,
    url_path: str,
) -> dict[str, str]:
    """Compute HMAC-SHA256 signature for 赛狐 API.

    Returns only the query params that should appear in the URL:
    access_token, client_id, nonce, timestamp, sign.
    (method and url participate in signing but NOT sent as query params.)
    """
    ts = str(int(time.time() * 1000))
    nonce = str(random.randint(1, 99999))

    sign_params = {
        "access_token": access_token,
        "client_id": client_id,
        "method": "post",
        "nonce": nonce,
        "timestamp": ts,
        "url": url_path,
    }
    sorted_str = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
    sig = hmac.new(
        client_secret.encode(), sorted_str.encode(), hashlib.sha256
    ).hexdigest()

    return {
        "access_token": access_token,
        "client_id": client_id,
        "nonce": nonce,
        "timestamp": ts,
        "sign": sig,
    }
