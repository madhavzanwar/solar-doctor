"""Object storage clients for /track file uploads.

The Azure VM disk is ephemeral across redeploys — anything written locally can
be lost. When AZURE_STORAGE_CONNECTION_STRING is set, track files live in an
Azure Blob Storage container instead; failing that, Supabase Storage is used
if configured; without either we fall back to local disk so dev and CI keep
working with zero configuration.
"""
from __future__ import annotations

import os
from typing import BinaryIO, Iterator

import requests

DEFAULT_BUCKET = "track-files"
_CHUNK = 1024 * 1024
_TIMEOUT = 60  # seconds — STL uploads can be tens of MB


class AzureBlobStorageStore:
    """Minimal wrapper around azure-storage-blob for one container."""

    def __init__(self, connection_string: str, container: str = DEFAULT_BUCKET):
        from azure.storage.blob import BlobServiceClient

        self._client = BlobServiceClient.from_connection_string(connection_string)
        self.container = container
        try:
            self._client.create_container(container)
        except Exception:
            pass  # already exists

    def upload(self, name: str, fileobj: BinaryIO, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        blob = self._client.get_blob_client(container=self.container, blob=name)
        blob.upload_blob(
            fileobj,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=content_type or "application/octet-stream"
            ),
        )

    def download(self, name: str) -> Iterator[bytes] | None:
        blob = self._client.get_blob_client(container=self.container, blob=name)
        try:
            stream = blob.download_blob()
        except Exception:
            return None
        return stream.chunks()

    def delete(self, name: str) -> None:
        blob = self._client.get_blob_client(container=self.container, blob=name)
        try:
            blob.delete_blob()
        except Exception:
            pass  # missing objects are not an error


class SupabaseStorage:
    """Minimal REST client for one Supabase Storage bucket (service-role auth)."""

    def __init__(self, url: str, service_key: str, bucket: str = DEFAULT_BUCKET):
        self.url = url.rstrip("/")
        self.bucket = bucket
        self._auth = {"Authorization": f"Bearer {service_key}"}

    def _object_url(self, name: str) -> str:
        return f"{self.url}/storage/v1/object/{self.bucket}/{name}"

    def upload(self, name: str, fileobj: BinaryIO, content_type: str) -> None:
        """Store an object; raises RuntimeError on any non-2xx response."""
        resp = requests.post(
            self._object_url(name),
            headers={
                **self._auth,
                "Content-Type": content_type or "application/octet-stream",
                # idempotent re-upload of the same stored_name
                "x-upsert": "true",
            },
            data=fileobj,
            timeout=_TIMEOUT,
        )
        if resp.status_code >= 300:
            raise RuntimeError(
                f"Supabase Storage upload failed ({resp.status_code}): {resp.text[:200]}"
            )

    def download(self, name: str) -> Iterator[bytes] | None:
        """Yield object content in chunks, or None when the object is missing."""
        resp = requests.get(
            self._object_url(name), headers=self._auth, stream=True, timeout=_TIMEOUT
        )
        if resp.status_code != 200:
            return None
        return resp.iter_content(chunk_size=_CHUNK)

    def delete(self, name: str) -> None:
        """Remove an object; missing objects are not an error."""
        resp = requests.delete(self._object_url(name), headers=self._auth, timeout=_TIMEOUT)
        if resp.status_code >= 300 and resp.status_code != 404:
            raise RuntimeError(
                f"Supabase Storage delete failed ({resp.status_code}): {resp.text[:200]}"
            )


def get_track_store() -> AzureBlobStorageStore | SupabaseStorage | None:
    """Build the store from env, preferring Azure Blob, then Supabase, then
    None to use the local-disk fallback."""
    azure_conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if azure_conn:
        container = os.environ.get("AZURE_TRACK_CONTAINER", DEFAULT_BUCKET).strip() or DEFAULT_BUCKET
        return AzureBlobStorageStore(connection_string=azure_conn, container=container)

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        return None
    bucket = os.environ.get("AXALON_TRACK_BUCKET", DEFAULT_BUCKET).strip() or DEFAULT_BUCKET
    return SupabaseStorage(url=url, service_key=key, bucket=bucket)
