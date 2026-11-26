"""PKCE (RFC 7636) S256 만 쓴다. plain 은 받지 않는다."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
_CHALLENGE = re.compile(r"^[A-Za-z0-9\-_]{43}$")


def new_verifier() -> str:
    return secrets.token_urlsafe(64)  # 86자


def s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def valid_verifier(verifier: str | None) -> bool:
    return bool(verifier) and bool(_VERIFIER.match(verifier))


def valid_challenge(challenge: str | None) -> bool:
    return bool(challenge) and bool(_CHALLENGE.match(challenge))


def verify(verifier: str | None, challenge: str) -> bool:
    if not valid_verifier(verifier):
        return False
    return hmac.compare_digest(s256(verifier), challenge)
