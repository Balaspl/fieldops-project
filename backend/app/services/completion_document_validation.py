from __future__ import annotations

import hashlib
import imghdr
import os
from pathlib import Path
from typing import BinaryIO


class CompletionDocumentValidationError(ValueError):
    """
    Raised when an uploaded completion document is invalid.

    Optional size details are retained for internal callers/tests
    without changing the existing string-based error handling.
    """

    def __init__(
        self,
        message: str,
        *,
        max_size_bytes: int | None = None,
        received_size_bytes: int | None = None,
    ):
        super().__init__(message)

        self.max_size_bytes = max_size_bytes
        self.received_size_bytes = received_size_bytes

        self.details = {
            "max_size_bytes": max_size_bytes,
            "received_size_bytes": received_size_bytes,
        }

class CompletionDocumentValidator:
    """
    Validates completion photos and service documents before
    they reach storage.

    Client-provided MIME types are treated as metadata only.
    The uploaded file content is inspected independently.
    """

    # ---------------------------------------------------------
    # Allowed photo types
    # ---------------------------------------------------------

    ALLOWED_PHOTO_CONTENT_TYPES = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    # ---------------------------------------------------------
    # Allowed service document types
    # ---------------------------------------------------------

    ALLOWED_DOCUMENT_CONTENT_TYPES = {
        "application/pdf": ".pdf",
        (
            "application/"
            "vnd.openxmlformats-officedocument.wordprocessingml.document"
        ): ".docx",
    }

    # Combined allow-list.
    ALLOWED_CONTENT_TYPES = {
        **ALLOWED_PHOTO_CONTENT_TYPES,
        **ALLOWED_DOCUMENT_CONTENT_TYPES,
    }

    # ---------------------------------------------------------
    # Allowed categories
    # ---------------------------------------------------------

    PHOTO_CATEGORIES = {
        "BEFORE",
        "AFTER",
    }

    DOCUMENT_CATEGORIES = {
        "MANUAL",
        "SERVICE_REPORT",
        "CERTIFICATE",
        "OTHER",
    }

    # ---------------------------------------------------------
    # Upload size limit
    # ---------------------------------------------------------

    DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    MAX_FILE_SIZE = int(
        os.getenv(
            "COMPLETION_DOCUMENT_MAX_FILE_SIZE_BYTES",
            str(DEFAULT_MAX_FILE_SIZE),
        )
    )

    if MAX_FILE_SIZE <= 0:
        raise ValueError(
            "COMPLETION_DOCUMENT_MAX_FILE_SIZE_BYTES must be greater than zero."
        )

    # ---------------------------------------------------------
    # MIME validation
    # ---------------------------------------------------------

    @classmethod
    def validate_content_type(
        cls,
        content_type: str,
        document_type: str = "PHOTO",
    ) -> str:
        """
        Validate the client-provided MIME type.

        This is only the first validation layer.
        Actual file content is validated separately.
        """

        normalized_content_type = (
            content_type or ""
        ).strip().lower()

        document_type = (
            document_type or "PHOTO"
        ).strip().upper()

        if document_type == "PHOTO":
            allowed_types = cls.ALLOWED_PHOTO_CONTENT_TYPES

        elif document_type == "DOCUMENT":
            allowed_types = cls.ALLOWED_DOCUMENT_CONTENT_TYPES

        else:
            raise CompletionDocumentValidationError(
                "Document type must be PHOTO or DOCUMENT."
            )

        if normalized_content_type not in allowed_types:
            if document_type == "PHOTO":
                raise CompletionDocumentValidationError(
                    "Unsupported image type. "
                    "Allowed types are JPEG, PNG, and WEBP."
                )

            raise CompletionDocumentValidationError(
                "Unsupported document type. "
                "Allowed types are PDF and DOCX."
            )

        return normalized_content_type

    # ---------------------------------------------------------
    # Filename validation
    # ---------------------------------------------------------

    @classmethod
    def validate_filename(cls, filename: str) -> str:
        filename = Path(filename or "").name.strip()

        if not filename:
            raise CompletionDocumentValidationError(
                "Filename is required."
            )

        if len(filename) > 255:
            raise CompletionDocumentValidationError(
                "Filename must not exceed 255 characters."
            )

        return filename

    # ---------------------------------------------------------
    # Category validation
    # ---------------------------------------------------------

    @classmethod
    def validate_category(
        cls,
        category: str,
        document_type: str = "PHOTO",
    ) -> str:
        category = (category or "").strip().upper()
        document_type = (
            document_type or "PHOTO"
        ).strip().upper()

        if document_type == "PHOTO":
            allowed_categories = cls.PHOTO_CATEGORIES

        elif document_type == "DOCUMENT":
            allowed_categories = cls.DOCUMENT_CATEGORIES

        else:
            raise CompletionDocumentValidationError(
                "Document type must be PHOTO or DOCUMENT."
            )

        if category not in allowed_categories:
            if document_type == "PHOTO":
                raise CompletionDocumentValidationError(
                    "Category must be BEFORE or AFTER."
                )

            raise CompletionDocumentValidationError(
                "Document category must be MANUAL, "
                "SERVICE_REPORT, CERTIFICATE, or OTHER."
            )

        return category

    # ---------------------------------------------------------
    # Extension validation
    # ---------------------------------------------------------

    @classmethod
    def validate_extension(
        cls,
        filename: str,
        content_type: str,
        document_type: str,
    ) -> None:
        extension = Path(filename).suffix.lower()

        expected_extension = cls.ALLOWED_CONTENT_TYPES.get(
            content_type
        )

        if expected_extension is None:
            raise CompletionDocumentValidationError(
                "Unsupported file type."
            )

        if extension != expected_extension:
            raise CompletionDocumentValidationError(
                "Filename extension does not match "
                "the declared file type."
            )

        if document_type == "PHOTO":
            allowed_extensions = {
                ".jpg",
                ".png",
                ".webp",
            }
        else:
            allowed_extensions = {
                ".pdf",
                ".docx",
            }

        if extension not in allowed_extensions:
            raise CompletionDocumentValidationError(
                "File extension is not allowed for this "
                "document type."
            )

    # ---------------------------------------------------------
    # File signature validation
    # ---------------------------------------------------------

    @classmethod
    def validate_file_signature(
        cls,
        file: BinaryIO,
        content_type: str,
        document_type: str,
    ) -> None:
        """
        Inspect the actual file bytes.

        The client-provided MIME type is NOT trusted by itself.
        """

        file.seek(0)

        header = file.read(16)

        if document_type == "PHOTO":
            cls._validate_photo_signature(
                header=header,
                content_type=content_type,
            )

        elif document_type == "DOCUMENT":
            cls._validate_document_signature(
                file=file,
                header=header,
                content_type=content_type,
            )

        else:
            raise CompletionDocumentValidationError(
                "Document type must be PHOTO or DOCUMENT."
            )

        file.seek(0)

    # ---------------------------------------------------------
    # Photo signatures
    # ---------------------------------------------------------

    @classmethod
    def _validate_photo_signature(
        cls,
        header: bytes,
        content_type: str,
    ) -> None:
        if content_type == "image/jpeg":
            # JPEG starts with FF D8 FF.
            if not header.startswith(b"\xff\xd8\xff"):
                raise CompletionDocumentValidationError(
                    "File content does not match JPEG format."
                )

        elif content_type == "image/png":
            # PNG signature.
            if header[:8] != b"\x89PNG\r\n\x1a\n":
                raise CompletionDocumentValidationError(
                    "File content does not match PNG format."
                )

        elif content_type == "image/webp":
            # WEBP = RIFF....WEBP
            if not (
                header[:4] == b"RIFF"
                and header[8:12] == b"WEBP"
            ):
                raise CompletionDocumentValidationError(
                    "File content does not match WEBP format."
                )

        else:
            raise CompletionDocumentValidationError(
                "Unsupported image type."
            )

    # ---------------------------------------------------------
    # Document signatures
    # ---------------------------------------------------------

    @classmethod
    def _validate_document_signature(
        cls,
        file: BinaryIO,
        header: bytes,
        content_type: str,
    ) -> None:
        if content_type == "application/pdf":
            # PDF files begin with %PDF-
            if not header.startswith(b"%PDF-"):
                raise CompletionDocumentValidationError(
                    "File content does not match PDF format."
                )

            return

        if (
            content_type
            == (
                "application/"
                "vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        ):
            # DOCX is an OOXML ZIP package.
            if not header.startswith(b"PK"):
                raise CompletionDocumentValidationError(
                    "File content does not match DOCX format."
                )

            return

        raise CompletionDocumentValidationError(
            "Unsupported document type."
        )

    # ---------------------------------------------------------
    # Complete file validation
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Complete file validation
    # ---------------------------------------------------------

    @classmethod
    def validate_file(
        cls,
        file: BinaryIO,
        content_type: str,
        filename: str,
        document_type: str = "PHOTO",
        category: str | None = None,
    ) -> tuple[str, str, int, str]:
        """
        Validate the upload and return:

        (
            normalized_content_type,
            safe_filename,
            file_size,
            sha256,
        )
        """

        document_type = (
            document_type or "PHOTO"
        ).strip().upper()

        normalized_content_type = cls.validate_content_type(
            content_type,
            document_type=document_type,
        )

        safe_filename = cls.validate_filename(
            filename
        )

        if category is not None:
            cls.validate_category(
                category,
                document_type=document_type,
            )

        cls.validate_extension(
            filename=safe_filename,
            content_type=normalized_content_type,
            document_type=document_type,
        )

        # -----------------------------------------------------
        # Size + checksum
        #
        # Process the upload in bounded chunks.
        # Reject as soon as the configured limit is exceeded.
        # -----------------------------------------------------

        file.seek(0)

        total_size = 0
        digest = hashlib.sha256()

        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            total_size += len(chunk)

            if total_size > cls.MAX_FILE_SIZE:
                raise CompletionDocumentValidationError(
            (
                "File size must not exceed 10 MB. "
                f"Maximum allowed: {cls.MAX_FILE_SIZE} bytes. "
                f"Received: {total_size} bytes."
            ),
            max_size_bytes=cls.MAX_FILE_SIZE,
            received_size_bytes=total_size,
        )

            digest.update(chunk)

        if total_size == 0:
            raise CompletionDocumentValidationError(
                "Uploaded file cannot be empty."
            )

        file.seek(0)

        # -----------------------------------------------------
        # Actual file-content validation
        #
        # This happens only after the size check has passed.
        # -----------------------------------------------------

        cls.validate_file_signature(
            file=file,
            content_type=normalized_content_type,
            document_type=document_type,
        )

        file.seek(0)

        checksum = digest.hexdigest()

        return (
            normalized_content_type,
            safe_filename,
            total_size,
            checksum,
        )
    