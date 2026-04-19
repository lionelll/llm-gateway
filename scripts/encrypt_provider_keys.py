"""
One-time migration script: encrypt any plaintext provider API keys in the database.

Usage:
    python -m scripts.encrypt_provider_keys

This reads all providers, checks if their stored api_key looks like a Fernet
token (starts with 'gAAAAA'), and re-encrypts any that don't match.
Safe to run multiple times — already-encrypted keys are skipped.
"""
import asyncio

from sqlalchemy import select

from app.core.encryption import encrypt_value
from app.db import AsyncSessionLocal
from app.models.provider import Provider


def _is_fernet_token(value: str) -> bool:
    """Heuristic: Fernet tokens are base64 and start with 'gAAAAA'."""
    return value.startswith("gAAAAA")


async def migrate_keys() -> None:
    async with AsyncSessionLocal() as session:
        providers = list((await session.scalars(select(Provider))).all())
        migrated = 0
        for provider in providers:
            raw = provider._api_key_encrypted
            if raw and not _is_fernet_token(raw):
                provider._api_key_encrypted = encrypt_value(raw)
                migrated += 1
                print(f"  Encrypted key for provider '{provider.name}'")
        if migrated:
            await session.commit()
            print(f"\nDone: {migrated} provider key(s) encrypted.")
        else:
            print("No plaintext keys found — nothing to migrate.")


def main() -> None:
    asyncio.run(migrate_keys())


if __name__ == "__main__":
    main()
