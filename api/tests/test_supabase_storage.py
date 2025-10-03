from types import SimpleNamespace
from unittest.mock import Mock

from app.data.supabase import SupabaseStorage, sanitize_headers


def test_store_pdf_uses_file_options():
    upload_mock = Mock()
    list_mock = Mock(return_value=[])
    bucket = SimpleNamespace(upload=upload_mock, list=list_mock)
    storage_attr = SimpleNamespace(from_=Mock(return_value=bucket))
    client = SimpleNamespace(storage=storage_attr)

    storage = SupabaseStorage(client, "papers")

    artifact = storage.store_pdf("foo/bar.pdf", b"data")

    upload_mock.assert_called_once()
    kwargs = upload_mock.call_args.kwargs
    assert kwargs["path"] == "foo/bar.pdf"
    assert kwargs["file"] == b"data"
    assert kwargs["file_options"] == {"contentType": "application/pdf"}
    assert isinstance(kwargs["file_options"]["contentType"], str)
    assert artifact.path == "foo/bar.pdf"


def test_sanitize_headers_casts_non_strings():
    headers = {"contentType": "application/pdf", "upsert": True, "retries": 2}
    sanitized = sanitize_headers(headers)
    assert set(sanitized.keys()) == {"contentType", "upsert", "retries"}
    for value in sanitized.values():
        assert isinstance(value, str)
    assert sanitized["upsert"] == "True"
    assert sanitized["retries"] == "2"


def test_store_text_uses_utf8():
    upload_mock = Mock()
    bucket = SimpleNamespace(upload=upload_mock, list=Mock(return_value=[]))
    storage_attr = SimpleNamespace(from_=Mock(return_value=bucket))
    client = SimpleNamespace(storage=storage_attr)
    storage = SupabaseStorage(client, "plans")

    artifact = storage.store_text("plans/abc.txt", "hello")

    upload_mock.assert_called_once()
    kwargs = upload_mock.call_args.kwargs
    assert kwargs["path"] == "plans/abc.txt"
    assert kwargs["file"] == b"hello"
    assert kwargs["file_options"] == {"contentType": "text/plain"}
    assert artifact.path == "plans/abc.txt"
