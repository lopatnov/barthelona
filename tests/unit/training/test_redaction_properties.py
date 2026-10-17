"""Property tests for the training-data redactor (invariant 10): no secret survives redaction."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from barthelona.training.redaction import MIN_SECRET_LENGTH, Redactor

# Lowercase and digits only, so a secret can never be spelled by the uppercase `REDACTED` marker.
_SECRET_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
secrets = st.text(alphabet=_SECRET_ALPHABET, min_size=MIN_SECRET_LENGTH, max_size=24)
_KEY_ALPHABET = _SECRET_ALPHABET + "ABCDEFGHIJKLMNOPQRSTUVWXYZ_-"
# One strategy per provider key shape the redactor knows (Anthropic, OpenAI-style, Google).
api_keys = st.one_of(
    st.text(alphabet=_KEY_ALPHABET, min_size=16, max_size=40).map(lambda tail: f"sk-ant-{tail}"),
    st.text(alphabet=_KEY_ALPHABET, min_size=20, max_size=40).map(lambda tail: f"sk-{tail}"),
    st.text(alphabet=_KEY_ALPHABET, min_size=35, max_size=35).map(lambda tail: f"AIza{tail}"),
)


@given(st.lists(st.text(max_size=20)), st.lists(secrets, min_size=1, max_size=3))
def test_no_known_secret_survives(chunks: list[str], known: list[str]) -> None:
    text = "".join(chunk + secret for chunk, secret in zip(chunks, known * len(chunks), strict=False))
    text += "".join(known)
    redacted = Redactor.of(known)(text)
    assert all(secret not in redacted for secret in known)


@given(st.text(max_size=40), api_keys, st.text(max_size=40))
def test_key_shaped_tokens_are_redacted_without_being_passed_in(before: str, key: str, after: str) -> None:
    redacted = Redactor()(f"{before} {key} {after}")
    assert key not in redacted


@given(st.text(max_size=80), st.lists(secrets, max_size=3))
def test_redaction_is_idempotent(text: str, known: list[str]) -> None:
    redact = Redactor.of(known)
    once = redact(text)
    assert redact(once) == once
