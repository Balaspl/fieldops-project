from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO


class CompletionDocumentValidationError(ValueError):
    """Raised when an uploaded completion document is invalid."""


class CompletionDocumentValidator:
    """
    Validates completion photo uploads before they reach storage.
    """

    ALLOWED_CONTENT_TYPES = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    @classmethod
    def validate_content_type(cls, content_type: str) -> str:
        content_type = (content_type or "").strip().lower()

        if content_type not in cls.ALLOWED_CONTENT_TYPES:
            raise CompletionDocumentValidationError(
                "Unsupported image type. Allowed types are JPEG, PNG, and WEBP."
            )

        return content_type

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

    @classmethod
    def validate_category(cls, category: str) -> str:
        category = (category or "").strip().upper()

        if category not in {"BEFORE", "AFTER"}:
            raise CompletionDocumentValidationError(
                "Category must be BEFORE or AFTER."
            )

        return category

    @classmethod
    def validate_file(
        cls,
        file: BinaryIO,
        content_type: str,
        filename: str,
    ) -> tuple[str, str, int, str]:
        """
        Validate the upload and return:

        (normalized_content_type, safe_filename, file_size, sha256)
        """

        normalized_content_type = cls.validate_content_type(
            content_type
        )

        safe_filename = cls.validate_filename(filename)

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
                    "Image size must not exceed 10 MB."
                )

            digest.update(chunk)

        if total_size == 0:
            raise CompletionDocumentValidationError(
                "Uploaded image cannot be empty."
            )

        file.seek(0)

        return (
            normalized_content_type,
            safe_filename,
            total_size,
            digest.hexdigest(),
        )