import pytest

from voice_runtime.transport.authentication import AuthError, TokenAuth


def test_token_is_random_and_verifiable() -> None:
    first = TokenAuth.generate()
    second = TokenAuth.generate()
    assert first.token != second.token
    assert first.verify(first.token)
    assert not first.verify(first.token + "x")


def test_require_raises_for_bad_token() -> None:
    auth = TokenAuth("secret")
    with pytest.raises(AuthError) as exc:
        auth.require("wrong")
    assert exc.value.code == "auth_failed"


def test_empty_candidate_is_rejected() -> None:
    assert TokenAuth("secret").verify("") is False
