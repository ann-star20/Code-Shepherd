"""TDD: JWT 발급/검증 라운드트립, 만료·위조 토큰 거부."""

from datetime import timedelta

import pytest

from shared.auth import create_access_token, create_refresh_token, decode_token


class TestCreateAndDecodeAccessToken:
    def test_access_token_roundtrip(self):
        token = create_access_token(subject=42)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_extra_claims_included(self):
        token = create_access_token(subject=1, extra_claims={"role": "lead"})
        payload = decode_token(token)
        assert payload["role"] == "lead"

    def test_string_subject(self):
        token = create_access_token(subject="user-uuid")
        payload = decode_token(token)
        assert payload["sub"] == "user-uuid"


class TestCreateAndDecodeRefreshToken:
    def test_refresh_token_roundtrip(self):
        token = create_refresh_token(subject=7)
        payload = decode_token(token)
        assert payload["sub"] == "7"
        assert payload["type"] == "refresh"


class TestDecodeTokenRejectsInvalid:
    def test_expired_token_raises(self):
        token = create_access_token(subject=1, expires_delta=timedelta(seconds=-1))
        with pytest.raises(ValueError, match="expired"):
            decode_token(token)

    def test_tampered_token_raises(self):
        token = create_access_token(subject=1)
        tampered = token[:-4] + "xxxx"
        with pytest.raises(ValueError):
            decode_token(tampered)

    def test_wrong_secret_raises(self):
        import jwt as pyjwt
        from datetime import datetime, UTC

        bad_token = pyjwt.encode(
            {"sub": "1", "exp": datetime.now(UTC).timestamp() + 3600},
            "wrong-secret",
            algorithm="HS256",
        )
        with pytest.raises(ValueError):
            decode_token(bad_token)

    def test_completely_invalid_string_raises(self):
        with pytest.raises(ValueError):
            decode_token("not.a.jwt")
