from app.utils.redaction import redact_vector_store_id


def test_redact_vector_store_id_none():
    assert redact_vector_store_id(None) == "unknown***"


def test_redact_vector_store_id_short():
    assert redact_vector_store_id("abc") == "abc***"


def test_redact_vector_store_id_long():
    assert redact_vector_store_id("abcdefghijk") == "abcdefgh***"
