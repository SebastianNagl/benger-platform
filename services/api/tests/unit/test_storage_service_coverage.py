"""
Unit tests for services/storage/storage_service.py — 0% coverage (182 uncovered lines).

Tests LocalStorageBackend and StorageService using temp directories.
"""

import os
import tempfile

import pytest


class TestLocalStorageBackendInit:
    """Test LocalStorageBackend initialization."""

    def test_creates_base_directory(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "storage", "test")
            backend = LocalStorageBackend(new_dir)
            assert os.path.isdir(new_dir)

    def test_existing_directory(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            assert backend.base_path.exists()


class TestLocalStorageGetFullPath:
    """Test _get_full_path path resolution."""

    def test_simple_key(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            path = backend._get_full_path("test.txt")
            assert str(path).endswith("test.txt")
            assert str(path).startswith(tmpdir)

    def test_nested_key(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            path = backend._get_full_path("subdir/test.txt")
            assert "subdir" in str(path)

    def test_leading_slash_stripped(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            path = backend._get_full_path("/test.txt")
            assert str(path).startswith(tmpdir)

    def test_path_traversal_rejected(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            with pytest.raises(ValueError, match="Invalid key"):
                backend._get_full_path("../../etc/passwd")


class TestLocalStorageUpload:
    """Test file upload to local storage."""

    @pytest.mark.asyncio
    async def test_upload_bytes(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            key = await backend.upload_file(b"hello world", "test.txt")
            assert key == "test.txt"
            assert os.path.exists(os.path.join(tmpdir, "test.txt"))

    @pytest.mark.asyncio
    async def test_upload_with_subdirectory(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            key = await backend.upload_file(b"data", "subdir/file.txt")
            assert os.path.exists(os.path.join(tmpdir, "subdir", "file.txt"))

    @pytest.mark.asyncio
    async def test_upload_with_metadata(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            await backend.upload_file(
                b"data", "test.txt", metadata={"content_type": "text/plain"}
            )
            meta_path = os.path.join(tmpdir, "test.txt.meta")
            assert os.path.exists(meta_path)

    @pytest.mark.asyncio
    async def test_upload_fileobj(self):
        import io
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            file_obj = io.BytesIO(b"file object data")
            key = await backend.upload_file(file_obj, "obj.txt")
            assert os.path.exists(os.path.join(tmpdir, "obj.txt"))


class TestLocalStorageDownload:
    """Test file download from local storage."""

    @pytest.mark.asyncio
    async def test_download_existing_file(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            await backend.upload_file(b"test content", "dl.txt")
            data = await backend.download_file("dl.txt")
            assert data == b"test content"

    @pytest.mark.asyncio
    async def test_download_nonexistent_file(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            with pytest.raises(FileNotFoundError):
                await backend.download_file("nonexistent.txt")


class TestLocalStorageDelete:
    """Test file deletion from local storage."""

    @pytest.mark.asyncio
    async def test_delete_existing_file(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            await backend.upload_file(b"data", "del.txt")
            result = await backend.delete_file("del.txt")
            assert result is True
            assert not os.path.exists(os.path.join(tmpdir, "del.txt"))

    @pytest.mark.asyncio
    async def test_delete_with_metadata(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            await backend.upload_file(
                b"data", "meta.txt", metadata={"key": "val"}
            )
            result = await backend.delete_file("meta.txt")
            assert result is True
            assert not os.path.exists(os.path.join(tmpdir, "meta.txt.meta"))

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            result = await backend.delete_file("nonexistent.txt")
            assert result is True  # No error for nonexistent files


class TestLocalStoragePresignedUrl:
    """Test presigned URL generation."""

    @pytest.mark.asyncio
    async def test_generate_url(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            url = await backend.generate_presigned_url("test.txt")
            assert url.startswith("file://")
            assert "test.txt" in url


class TestLocalStorageFileExists:
    """Test file existence check."""

    @pytest.mark.asyncio
    async def test_existing_file(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            await backend.upload_file(b"data", "exists.txt")
            assert await backend.file_exists("exists.txt") is True

    @pytest.mark.asyncio
    async def test_nonexistent_file(self):
        from services.storage.storage_service import LocalStorageBackend
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            assert await backend.file_exists("nope.txt") is False


class TestStorageService:
    """Test StorageService wrapper."""

    @pytest.mark.asyncio
    async def test_upload_and_download(self):
        from services.storage.storage_service import LocalStorageBackend, StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            service = StorageService(backend)
            result = await service.upload_file(
                b"via service", "svc.txt", user_id="user-1"
            )
            assert "key" in result
            assert "url" in result
            assert result["size"] == len(b"via service")
            data = await service.download_file(result["key"])
            assert data == b"via service"

    @pytest.mark.asyncio
    async def test_upload_with_file_type(self):
        from services.storage.storage_service import LocalStorageBackend, StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            service = StorageService(backend)
            result = await service.upload_file(
                b"data", "test.pdf", user_id="u1", file_type="document"
            )
            assert result["key"].startswith("document/u1/")

    @pytest.mark.asyncio
    async def test_upload_fileobj(self):
        import io
        from services.storage.storage_service import LocalStorageBackend, StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            service = StorageService(backend)
            file_obj = io.BytesIO(b"file object content")
            result = await service.upload_file(
                file_obj, "obj.txt", user_id="u1"
            )
            assert result["hash"] is not None
            assert result["size"] == len(b"file object content")

    @pytest.mark.asyncio
    async def test_delete_via_service(self):
        from services.storage.storage_service import LocalStorageBackend, StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            service = StorageService(backend)
            result = await service.upload_file(
                b"data", "del_svc.txt", user_id="u1"
            )
            deleted = await service.delete_file(result["key"])
            assert deleted is True

    @pytest.mark.asyncio
    async def test_get_file_url(self):
        from services.storage.storage_service import LocalStorageBackend, StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            service = StorageService(backend)
            url = await service.get_file_url("test.txt")
            assert "test.txt" in url

    @pytest.mark.asyncio
    async def test_upload_sanitizes_filename(self):
        from services.storage.storage_service import LocalStorageBackend, StorageService
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalStorageBackend(tmpdir)
            service = StorageService(backend)
            result = await service.upload_file(
                b"data", "file with spaces!@#.txt", user_id="u1"
            )
            # Special chars should be stripped
            assert "!" not in result["key"]
            assert "@" not in result["key"]


class TestCreateStorageService:
    """Test the factory function."""

    def test_create_local(self):
        from services.storage.storage_service import create_storage_service
        with tempfile.TemporaryDirectory() as tmpdir:
            svc = create_storage_service("local", base_path=tmpdir)
            assert svc is not None

    def test_create_unknown_raises(self):
        from services.storage.storage_service import create_storage_service
        with pytest.raises(ValueError, match="Unknown storage type"):
            create_storage_service("unknown_type")
