"""Sealing (local and KMS), object storage (local), passwords, sessions and API keys."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from cryptography.exceptions import InvalidTag

from testforge.core.sealing import KmsSealer, LocalSealer
from testforge.core.security import (
    constant_time_equals,
    decode_session,
    generate_api_key,
    hash_key_secret,
    hash_password,
    issue_session,
    parse_api_key,
    password_problems,
    verify_password,
)
from testforge.core.storage import LocalStorage, ObjectNotFoundError


async def test_local_sealing_is_bound_to_its_record() -> None:
    sealer = LocalSealer("a-master-key-for-tests-only-0123456789")
    sealed = await sealer.seal("s3cret", "connection:1:password")
    assert b"s3cret" not in sealed
    assert await sealer.open(sealed, "connection:1:password") == "s3cret"
    with pytest.raises(InvalidTag):
        await sealer.open(sealed, "connection:2:password")
    with pytest.raises(ValueError, match="unknown sealed format"):
        await sealer.open(b"\x09" + sealed[1:], "connection:1:password")


class FakeKms:
    def encrypt(
        self, KeyId: str, Plaintext: bytes, EncryptionContext: dict[str, str]
    ) -> dict[str, Any]:
        blob = base64.b64encode(Plaintext) + b"|" + EncryptionContext["testforge:record"].encode()
        return {"CiphertextBlob": blob}

    def decrypt(self, CiphertextBlob: bytes, EncryptionContext: dict[str, str]) -> dict[str, Any]:
        data, _, ctx = CiphertextBlob.partition(b"|")
        if ctx.decode() != EncryptionContext["testforge:record"]:
            raise ValueError("context mismatch")
        return {"Plaintext": base64.b64decode(data)}


async def test_kms_sealing_passes_the_record_as_encryption_context() -> None:
    sealer = KmsSealer(FakeKms(), "alias/testforge-local")
    sealed = await sealer.seal("key", "model_provider:9:api_key")
    assert await sealer.open(sealed, "model_provider:9:api_key") == "key"
    with pytest.raises(ValueError, match="context mismatch"):
        await sealer.open(sealed, "model_provider:8:api_key")


async def test_local_storage_round_trip(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path / "objects"))
    await store.put("projects/p/results/r.json", b"{}", "application/json")
    assert await store.get("projects/p/results/r.json") == b"{}"
    src = tmp_path / "in.zip"
    src.write_bytes(b"PK\x03\x04data")
    await store.put_file("snapshots/p/c.zip", src, "application/zip")
    out = tmp_path / "out.zip"
    await store.get_file("snapshots/p/c.zip", out)
    assert out.read_bytes() == src.read_bytes()
    await store.delete("snapshots/p/c.zip")
    with pytest.raises(ObjectNotFoundError):
        await store.get("snapshots/p/c.zip")
    with pytest.raises(ValueError):
        await store.get("../escape")


def test_passwords_sessions_and_keys() -> None:
    h = hash_password("Good-Pass-123")
    assert verify_password("Good-Pass-123", h) and not verify_password("nope", h)
    assert not verify_password("x", None) and not verify_password("x", "not-a-hash")
    assert password_problems("short") == [
        "at least 10 characters",
        "upper and lower case letters",
        "a digit",
    ]
    assert password_problems("Good-Pass-123") == []
    import uuid

    uid = uuid.uuid4()
    token = issue_session(uid, "admin", 3, "a" * 40, 1)
    claims = decode_session(token, "a" * 40)
    assert claims is not None and claims.user_id == uid and claims.session_version == 3
    assert decode_session(token, "b" * 40) is None and decode_session("junk", "a" * 40) is None
    key = generate_api_key("pepper")
    prefix, secret = parse_api_key(key.plaintext) or ("", "")
    assert key.plaintext.startswith("tfk_") and prefix == key.prefix
    assert constant_time_equals(hash_key_secret(secret, "pepper"), key.secret_hash)
    assert parse_api_key("tfk_short_x") is None and parse_api_key("other_0123456789ab_x") is None
