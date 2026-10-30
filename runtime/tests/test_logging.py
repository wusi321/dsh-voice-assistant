from voice_runtime.utils.logging import REDACTED, redact


def test_redacts_sensitive_keys_recursively() -> None:
    payload = {
        "token": "secret",
        "text": "hello",
        "nested": {"audio": b"pcm", "ok": 1},
        "items": [{"transcript": "private"}, {"value": 2}],
    }
    cleaned = redact(payload)
    assert cleaned["token"] == REDACTED
    assert cleaned["text"] == REDACTED
    assert cleaned["nested"]["audio"] == REDACTED
    assert cleaned["nested"]["ok"] == 1
    assert cleaned["items"][0]["transcript"] == REDACTED
    assert cleaned["items"][1]["value"] == 2


def test_redacts_case_insensitively() -> None:
    assert redact({"Authorization": "Bearer x"})["Authorization"] == REDACTED
