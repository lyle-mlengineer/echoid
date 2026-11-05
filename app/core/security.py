import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import Settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 310_000
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_token(
    subject: str, token_type: str, settings: Settings, expires: timedelta
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": subject, "type": token_type, "iat": now, "exp": now + expires},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])

