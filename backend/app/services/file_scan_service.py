"""
Completion document scanning service.

This service performs a deterministic security scan over files
already persisted to the configured completion-document storage.

The scanner:
- verifies that the stored file exists
- verifies that the file stays inside the configured storage root
- re-validates filename, MIME type, and file signature
- re-validates file size
- re-validates SHA-256 checksum
- rejects common executable/script signatures

A future antivirus provider can be integrated here without
changing the upload route contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.services.completion_document_validation import (
    CompletionDocumentValidationError,
    CompletionDocumentValidator,
)


ScanStatus = Literal[
    "CLEAN",
    "REJECTED",
]


class FileScanError(RuntimeError):
    """Raised when the scanner cannot safely complete a scan."""


@dataclass(frozen=True)
class FileScanResult:
    """Result returned by the completion document scanner."""

    scan_status: ScanStatus
    scanned_at: datetime


class FileScanService:
    """
    Scan a stored completion document before it enters
    the trusted/downloadable flow.
    """

    def __init__(self, storage):
        self.storage = storage

    def scan(self, document) -> FileScanResult:
        """
        Scan one stored completion document.

        Validation failures are treated as REJECTED.

        Storage/path/I/O failures raise FileScanError so the
        caller can safely leave the document in PENDING state.
        """

        file_path = self._resolve_storage_path(
            document.storage_key
        )

        if not file_path.is_file():
            raise FileScanError(
                "Stored completion document does not exist."
            )

        try:
            with file_path.open("rb") as stored_file:
                header = stored_file.read(4)

                # Reject common executable/script signatures.
                if self._is_forbidden_signature(header):
                    return FileScanResult(
                        scan_status="REJECTED",
                        scanned_at=datetime.now(timezone.utc),
                    )

                stored_file.seek(0)

                (
                    content_type,
                    filename,
                    file_size,
                    checksum,
                ) = CompletionDocumentValidator.validate_file(
                    file=stored_file,
                    content_type=document.content_type,
                    filename=document.original_filename,
                    document_type=document.document_type,
                    category=document.category,
                )

        except CompletionDocumentValidationError:
            return FileScanResult(
                scan_status="REJECTED",
                scanned_at=datetime.now(timezone.utc),
            )

        except OSError as exc:
            raise FileScanError(
                "Unable to read stored completion document."
            ) from exc

        # -----------------------------------------------------
        # Verify stored metadata still matches DB metadata
        # -----------------------------------------------------

        if content_type != document.content_type:
            return FileScanResult(
                scan_status="REJECTED",
                scanned_at=datetime.now(timezone.utc),
            )

        if filename != document.original_filename:
            return FileScanResult(
                scan_status="REJECTED",
                scanned_at=datetime.now(timezone.utc),
            )

        if file_size != document.file_size:
            return FileScanResult(
                scan_status="REJECTED",
                scanned_at=datetime.now(timezone.utc),
            )

        if checksum != document.checksum_sha256:
            return FileScanResult(
                scan_status="REJECTED",
                scanned_at=datetime.now(timezone.utc),
            )

        # -----------------------------------------------------
        # File passed all checks
        # -----------------------------------------------------

        return FileScanResult(
            scan_status="CLEAN",
            scanned_at=datetime.now(timezone.utc),
        )

    def _resolve_storage_path(
        self,
        storage_key: str,
    ) -> Path:
        """
        Resolve a storage key safely inside the configured
        storage root.
        """

        root_dir = Path(
            self.storage.root_dir
        ).resolve()

        file_path = (
            root_dir / storage_key
        ).resolve()

        try:
            file_path.relative_to(root_dir)
        except ValueError as exc:
            raise FileScanError(
                "Completion document storage path is outside "
                "the configured storage root."
            ) from exc

        return file_path

    @staticmethod
    def _is_forbidden_signature(
        header: bytes,
    ) -> bool:
        """
        Reject common executable/script file signatures.
        """

        # Windows executable
        if header.startswith(b"MZ"):
            return True

        # Linux ELF executable
        if header.startswith(b"\x7fELF"):
            return True

        # Script with shebang
        if header.startswith(b"#!"):
            return True

        return False