"""
Symmetric encryption helpers for storing secrets (e.g. provider API keys).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` library.
The key is derived from the configured `provider_key_encryption_secret` via
SHA-256 → base64, so any passphrase length works.
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def _get_fernet() -> Fernet:
    secret = get_settings().provider_key_encryption_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string and return the Fernet token as a UTF-8 string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet token back to the original string."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
