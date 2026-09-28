import pytest

from app.services.file_scan_service import (
    FileScanError,
    FileScanService,
)


JPEG_BYTES = (
    b"\xff\xd8\xff\xe0"
    b"\x00\x10JFIF\x00\x01\x01\x00\x00"
    b"\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


class FakeStorage:
    def __init__(self, root_dir):
        self.root_dir = root_dir


def _document(
    *,
    filename="photo.jpg",
    content_type="image/jpeg",
    storage_key="tenant-1/photo.jpg",
    document_type="PHOTO",
    category="AFTER",
    file_size=None,
    checksum=None,
):
    from hashlib import sha256
    from types import SimpleNamespace

    if file_size is None:
        file_size = len(JPEG_BYTES)

    if checksum is None:
        checksum = sha256(JPEG_BYTES).hexdigest()

    return SimpleNamespace(
        original_filename=filename,
        content_type=content_type,
        storage_key=storage_key,
        document_type=document_type,
        category=category,
        file_size=file_size,
        checksum_sha256=checksum,
    )


def test_clean_file_returns_clean(tmp_path):
    storage_dir = tmp_path / "tenant-1"
    storage_dir.mkdir()

    file_path = storage_dir / "photo.jpg"
    file_path.write_bytes(JPEG_BYTES)

    document = _document()

    service = FileScanService(
        FakeStorage(tmp_path)
    )

    result = service.scan(document)

    assert result.scan_status == "CLEAN"
    assert result.scanned_at is not None


def test_executable_signature_is_rejected(tmp_path):
    storage_dir = tmp_path / "tenant-1"
    storage_dir.mkdir()

    file_path = storage_dir / "photo.jpg"

    file_path.write_bytes(
        b"MZ-not-an-image"
    )

    document = _document()

    service = FileScanService(
        FakeStorage(tmp_path)
    )

    result = service.scan(document)

    assert result.scan_status == "REJECTED"
    assert result.scanned_at is not None


def test_invalid_content_is_rejected(tmp_path):
    storage_dir = tmp_path / "tenant-1"
    storage_dir.mkdir()

    file_path = storage_dir / "photo.jpg"

    file_path.write_bytes(
        b"not-a-valid-jpeg"
    )

    document = _document()

    service = FileScanService(
        FakeStorage(tmp_path)
    )

    result = service.scan(document)

    assert result.scan_status == "REJECTED"
    assert result.scanned_at is not None


def test_checksum_mismatch_is_rejected(tmp_path):
    storage_dir = tmp_path / "tenant-1"
    storage_dir.mkdir()

    file_path = storage_dir / "photo.jpg"
    file_path.write_bytes(JPEG_BYTES)

    document = _document(
        checksum="0" * 64
    )

    service = FileScanService(
        FakeStorage(tmp_path)
    )

    result = service.scan(document)

    assert result.scan_status == "REJECTED"


def test_file_size_mismatch_is_rejected(tmp_path):
    storage_dir = tmp_path / "tenant-1"
    storage_dir.mkdir()

    file_path = storage_dir / "photo.jpg"
    file_path.write_bytes(JPEG_BYTES)

    document = _document(
        file_size=len(JPEG_BYTES) + 10
    )

    service = FileScanService(
        FakeStorage(tmp_path)
    )

    result = service.scan(document)

    assert result.scan_status == "REJECTED"


def test_missing_storage_file_is_scan_failure(tmp_path):
    document = _document()

    service = FileScanService(
        FakeStorage(tmp_path)
    )

    with pytest.raises(FileScanError):
        service.scan(document)


def test_storage_path_escape_is_scan_failure(tmp_path):
    document = _document(
        storage_key="../outside.jpg"
    )

    service = FileScanService(
        FakeStorage(tmp_path)
    )

    with pytest.raises(FileScanError):
        service.scan(document)