"""Tests for the Supabase Storage object store used by /track files."""
import io
from unittest.mock import MagicMock, patch

import pytest

from axalon.core.object_store import SupabaseStorage, get_track_store


@pytest.fixture
def store() -> SupabaseStorage:
    return SupabaseStorage(
        url="https://example.supabase.co",
        service_key="test-service-key",
        bucket="track-files",
    )


def test_get_track_store_returns_none_without_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert get_track_store() is None


def test_get_track_store_builds_from_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key123")
    s = get_track_store()
    assert s is not None
    assert s.bucket == "track-files"
    assert s.url == "https://example.supabase.co"  # trailing slash stripped


def test_upload_posts_to_object_endpoint(store):
    with patch("axalon.core.object_store.requests") as req:
        req.post.return_value = MagicMock(status_code=200)
        store.upload("abc_bracket.stl", io.BytesIO(b"solid"), "model/stl")
        url = req.post.call_args[0][0]
        assert url == "https://example.supabase.co/storage/v1/object/track-files/abc_bracket.stl"
        headers = req.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-service-key"
        assert headers["Content-Type"] == "model/stl"


def test_upload_raises_on_error(store):
    with patch("axalon.core.object_store.requests") as req:
        req.post.return_value = MagicMock(status_code=403, text="denied")
        with pytest.raises(RuntimeError):
            store.upload("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")


def test_download_streams_object(store):
    with patch("axalon.core.object_store.requests") as req:
        resp = MagicMock(status_code=200)
        resp.iter_content.return_value = iter([b"so", b"lid"])
        req.get.return_value = resp
        chunks = list(store.download("abc_bracket.stl"))
        assert b"".join(chunks) == b"solid"


def test_download_missing_returns_none(store):
    with patch("axalon.core.object_store.requests") as req:
        req.get.return_value = MagicMock(status_code=404)
        assert store.download("nope.pdf") is None


def test_delete_ignores_missing(store):
    with patch("axalon.core.object_store.requests") as req:
        req.delete.return_value = MagicMock(status_code=404)
        store.delete("nope.pdf")  # must not raise
        assert req.delete.call_args[0][0].endswith("/storage/v1/object/track-files/nope.pdf")


# ── Azure Blob backend (SDK mocked) ──────────────────────────────────────────

def _azure_store():
    """Build an AzureBlobStorageStore with the SDK fully mocked."""
    from axalon.core.object_store import AzureBlobStorageStore
    return AzureBlobStorageStore(connection_string="UseDevelopmentStorage=true",
                                 container="track-files")


def test_azure_store_upload_calls_blob_client():
    with patch("azure.storage.blob.BlobServiceClient"):
        store = _azure_store()
        blob = store._client.get_blob_client.return_value
        store.upload("part.stl", io.BytesIO(b"solid"), "model/stl")
        blob.upload_blob.assert_called_once()


def test_azure_store_download_returns_chunks():
    with patch("azure.storage.blob.BlobServiceClient"):
        store = _azure_store()
        blob = store._client.get_blob_client.return_value
        blob.download_blob.return_value.chunks.return_value = iter([b"so", b"lid"])
        result = store.download("part.stl")
        assert b"".join(result) == b"solid"


def test_azure_store_download_missing_returns_none():
    with patch("azure.storage.blob.BlobServiceClient"):
        store = _azure_store()
        blob = store._client.get_blob_client.return_value
        blob.download_blob.side_effect = RuntimeError("404")
        assert store.download("missing.stl") is None


def test_azure_store_delete_ignores_missing():
    with patch("azure.storage.blob.BlobServiceClient"):
        store = _azure_store()
        blob = store._client.get_blob_client.return_value
        blob.delete_blob.side_effect = RuntimeError("not found")
        store.delete("missing.stl")  # must not raise


def test_get_track_store_prefers_azure(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    with patch("azure.storage.blob.BlobServiceClient"):
        from axalon.core.object_store import AzureBlobStorageStore
        s = get_track_store()
        assert isinstance(s, AzureBlobStorageStore)
