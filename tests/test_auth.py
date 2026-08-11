from app.core.auth import (
    generate_token,
    hash_password,
    hash_token,
    normalize_username,
    validate_password,
    verify_password,
)


def test_password_hash_is_argon2_and_verifies():
    encoded = hash_password("VeryStrongPassword!42")
    assert encoded.startswith("$argon2")
    assert verify_password("VeryStrongPassword!42", encoded)
    assert not verify_password("wrong-password", encoded)


def test_session_tokens_are_random_and_stored_as_hashes():
    first = generate_token()
    second = generate_token()
    assert first != second
    assert hash_token(first) != first
    assert len(hash_token(first)) == 64


def test_username_is_normalized_and_validated():
    assert normalize_username("  Test.User  ") == "test.user"


def test_password_cannot_contain_username():
    try:
        validate_password("admin-very-long-password", "admin")
    except ValueError:
        pass
    else:
        raise AssertionError("username-containing password should fail")
