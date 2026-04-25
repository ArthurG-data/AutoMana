"""
Tests for src/automana/api/services/auth/auth.py

Pure-logic module — no mocks required. All tests are synchronous.
Coverage target: >= 95% line + branch.

Functions under test:
  - verify_password(plain, hashed) -> bool
  - get_hash_password(password) -> str
  - create_access_token(data, secret_key, algorithm, expires_delta) -> str
  - decode_access_token(token, secret_key, algorithm) -> dict
"""
import pytest
from datetime import timedelta

pytestmark = pytest.mark.unit

from automana.api.services.auth.auth import (
    create_access_token,
    decode_access_token,
    get_hash_password,
    verify_password,
)

# ---------------------------------------------------------------------------
# Test constants — intentionally distinct from any production keys
# ---------------------------------------------------------------------------
_SECRET = "unit-test-secret-not-for-production"
_ALGO = "HS256"
_PAYLOAD = {"sub": "alice", "user_id": "00000000-0000-0000-0000-000000000001"}


# ---------------------------------------------------------------------------
# verify_password
# ---------------------------------------------------------------------------

class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        hashed = get_hash_password("hunter2")
        assert verify_password("hunter2", hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = get_hash_password("hunter2")
        assert verify_password("wrong-password", hashed) is False

    def test_empty_plain_against_nonempty_hash_returns_false(self):
        hashed = get_hash_password("nonempty")
        assert verify_password("", hashed) is False


# ---------------------------------------------------------------------------
# get_hash_password
# ---------------------------------------------------------------------------

class TestGetHashPassword:
    def test_hash_is_not_plaintext(self):
        hashed = get_hash_password("mypassword")
        assert hashed != "mypassword"

    def test_hash_round_trips_via_verify(self):
        plain = "P@ssw0rd!"
        hashed = get_hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_two_hashes_of_same_password_differ(self):
        # bcrypt uses random salt — same input must not produce identical output
        h1 = get_hash_password("samepassword")
        h2 = get_hash_password("samepassword")
        assert h1 != h2


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------

class TestCreateAccessToken:
    def test_valid_token_decodes_to_expected_sub(self):
        token = create_access_token(
            data=_PAYLOAD.copy(),
            secret_key=_SECRET,
            algorithm=_ALGO,
            expires_delta=timedelta(hours=1),
        )
        decoded = decode_access_token(token, _SECRET, _ALGO)
        assert decoded["sub"] == "alice"
        assert decoded["user_id"] == _PAYLOAD["user_id"]

    def test_token_contains_exp_claim(self):
        token = create_access_token(
            data={"sub": "bob"},
            secret_key=_SECRET,
            algorithm=_ALGO,
            expires_delta=timedelta(minutes=5),
        )
        decoded = decode_access_token(token, _SECRET, _ALGO)
        assert "exp" in decoded

    def test_default_expiry_used_when_no_delta_given(self):
        # Should not raise — default is 15 minutes, so token is still valid
        token = create_access_token(
            data={"sub": "charlie"},
            secret_key=_SECRET,
            algorithm=_ALGO,
        )
        decoded = decode_access_token(token, _SECRET, _ALGO)
        assert decoded["sub"] == "charlie"

    def test_expired_token_raises_value_error_on_decode(self):
        token = create_access_token(
            data={"sub": "expireduser"},
            secret_key=_SECRET,
            algorithm=_ALGO,
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(ValueError, match="Token expired"):
            decode_access_token(token, _SECRET, _ALGO)


# ---------------------------------------------------------------------------
# decode_access_token
# ---------------------------------------------------------------------------

class TestDecodeAccessToken:
    def test_valid_token_returns_payload_dict(self):
        token = create_access_token(
            data=_PAYLOAD.copy(),
            secret_key=_SECRET,
            algorithm=_ALGO,
            expires_delta=timedelta(hours=1),
        )
        result = decode_access_token(token, _SECRET, _ALGO)
        assert isinstance(result, dict)
        assert result["sub"] == "alice"

    def test_tampered_signature_raises_invalid_token(self):
        token = create_access_token(
            data={"sub": "victim"},
            secret_key=_SECRET,
            algorithm=_ALGO,
            expires_delta=timedelta(hours=1),
        )
        # Corrupt the signature segment
        parts = token.split(".")
        parts[2] = parts[2][:-4] + "XXXX"
        bad_token = ".".join(parts)
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token(bad_token, _SECRET, _ALGO)

    def test_wrong_secret_raises_invalid_token(self):
        token = create_access_token(
            data={"sub": "dave"},
            secret_key=_SECRET,
            algorithm=_ALGO,
            expires_delta=timedelta(hours=1),
        )
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token(token, "completely-different-secret", _ALGO)

    def test_garbage_string_raises_invalid_token(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token("not.a.jwt", _SECRET, _ALGO)

    def test_expired_token_raises_token_expired(self):
        token = create_access_token(
            data={"sub": "past"},
            secret_key=_SECRET,
            algorithm=_ALGO,
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(ValueError, match="Token expired"):
            decode_access_token(token, _SECRET, _ALGO)
