import pytest
from src.core.security import hash_password, verify_password, create_access_token, decode_access_token
from src.core.exceptions import UnauthorizedError


def test_password_hashing():
    pwd = "StrongAdminPassword123!"
    h = hash_password(pwd)
    assert verify_password(pwd, h) is True
    assert verify_password("WrongPassword!", h) is False


def test_jwt_claims_and_validation():
    user_id = "11111111-2222-3333-4444-555555555555"
    token = create_access_token(user_id, "ADMIN")
    claims = decode_access_token(token)

    assert claims["sub"] == user_id
    assert claims["role"] == "ADMIN"
    assert "exp" in claims


def test_invalid_jwt():
    with pytest.raises(UnauthorizedError):
        decode_access_token("invalid.token.structure")
