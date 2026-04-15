import hashlib
import hmac
import secrets


def hash_api_key(api_key: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_api_key(prefix: str = "gw") -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"
