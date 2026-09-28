import io

import pytest

from app.services.completion_document_validation import (
    CompletionDocumentValidationError,
    CompletionDocumentValidator,
)


Validator = CompletionDocumentValidator


# ---------------------------------------------------------------------------
# Minimal valid file signatures
# ---------------------------------------------------------------------------

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00" * 20
)

WEBP_BYTES = (
    b"RIFF"
    + b"\x00\x00\x00\x00"
    + b"WEBP"
    + b"\x00" * 20
)

PDF_BYTES = b"%PDF-1.7\n" + b"\x00" * 20

DOCX_BYTES = b"PK\x03\x04" + b"\x00" * 20


# ---------------------------------------------------------------------------
# Allowed MIME types
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "content_type,document_type",
    [
        ("image/jpeg", "PHOTO"),
        ("image/png", "PHOTO"),
        ("image/webp", "PHOTO"),
        ("application/pdf", "DOCUMENT"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "DOCUMENT",
        ),
    ],
)
def test_allowed_content_types_pass(content_type, document_type):
    result = Validator.validate_content_type(
        content_type,
        document_type=document_type,
    )

    assert result == content_type


# ---------------------------------------------------------------------------
# Allowed complete files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,content_type,document_type,category,file_bytes",
    [
        (
            "photo.jpg",
            "image/jpeg",
            "PHOTO",
            "AFTER",
            JPEG_BYTES,
        ),
        (
            "photo.png",
            "image/png",
            "PHOTO",
            "BEFORE",
            PNG_BYTES,
        ),
        (
            "photo.webp",
            "image/webp",
            "PHOTO",
            "AFTER",
            WEBP_BYTES,
        ),
        (
            "manual.pdf",
            "application/pdf",
            "DOCUMENT",
            "MANUAL",
            PDF_BYTES,
        ),
        (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "DOCUMENT",
            "SERVICE_REPORT",
            DOCX_BYTES,
        ),
    ],
)
def test_allowed_files_pass(
    filename,
    content_type,
    document_type,
    category,
    file_bytes,
):
    content_type_result, safe_filename, file_size, checksum = (
        Validator.validate_file(
            file=io.BytesIO(file_bytes),
            content_type=content_type,
            filename=filename,
            document_type=document_type,
            category=category,
        )
    )

    assert content_type_result == content_type
    assert safe_filename == filename
    assert file_size == len(file_bytes)
    assert len(checksum) == 64


# ---------------------------------------------------------------------------
# Unsupported MIME types
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "content_type,document_type",
    [
        ("application/octet-stream", "PHOTO"),
        ("application/x-msdownload", "PHOTO"),
        ("text/plain", "PHOTO"),
        ("image/gif", "PHOTO"),
        ("application/zip", "DOCUMENT"),
        ("text/html", "DOCUMENT"),
    ],
)
def test_unsupported_content_types_are_rejected(
    content_type,
    document_type,
):
    with pytest.raises(
        CompletionDocumentValidationError,
        match="Unsupported",
    ):
        Validator.validate_content_type(
            content_type,
            document_type=document_type,
        )


# ---------------------------------------------------------------------------
# Executable/script rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,content_type,document_type",
    [
        ("malicious.exe", "application/octet-stream", "PHOTO"),
        ("script.sh", "text/plain", "PHOTO"),
        ("payload.bat", "application/octet-stream", "PHOTO"),
        ("program.exe", "application/octet-stream", "DOCUMENT"),
    ],
)
def test_executable_or_script_types_are_rejected(
    filename,
    content_type,
    document_type,
):
    with pytest.raises(CompletionDocumentValidationError):
        Validator.validate_file(
            file=io.BytesIO(b"not-a-valid-file"),
            content_type=content_type,
            filename=filename,
            document_type=document_type,
        )


# ---------------------------------------------------------------------------
# MIME / extension mismatch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,content_type,document_type",
    [
        ("photo.png", "image/jpeg", "PHOTO"),
        ("photo.jpg", "image/png", "PHOTO"),
        ("photo.jpg", "image/webp", "PHOTO"),
        ("manual.jpg", "application/pdf", "DOCUMENT"),
        (
            "report.pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "DOCUMENT",
        ),
    ],
)
def test_mime_and_extension_mismatch_is_rejected(
    filename,
    content_type,
    document_type,
):
    with pytest.raises(
        CompletionDocumentValidationError,
        match="extension does not match",
    ):
        Validator.validate_extension(
            filename=filename,
            content_type=content_type,
            document_type=document_type,
        )


# ---------------------------------------------------------------------------
# Filename case variations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,content_type,document_type",
    [
        ("PHOTO.JPG", "image/jpeg", "PHOTO"),
        ("PHOTO.PNG", "image/png", "PHOTO"),
        ("PHOTO.WEBP", "image/webp", "PHOTO"),
        ("MANUAL.PDF", "application/pdf", "DOCUMENT"),
        (
            "SERVICE_REPORT.DOCX",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "DOCUMENT",
        ),
    ],
)
def test_filename_case_variations_are_handled(
    filename,
    content_type,
    document_type,
):
    Validator.validate_extension(
        filename=filename,
        content_type=content_type,
        document_type=document_type,
    )


# ---------------------------------------------------------------------------
# MIME case and whitespace normalization
# ---------------------------------------------------------------------------

def test_content_type_is_normalized():
    result = Validator.validate_content_type(
        " IMAGE/JPEG ",
        document_type="PHOTO",
    )

    assert result == "image/jpeg"


def test_document_type_is_normalized():
    result = Validator.validate_content_type(
        " APPLICATION/PDF ",
        document_type=" document ",
    )

    assert result == "application/pdf"


# ---------------------------------------------------------------------------
# Filename normalization
# ---------------------------------------------------------------------------

def test_filename_is_normalized_to_basename():
    result = Validator.validate_filename(
        "C:\\fake\\path\\photo.jpg"
    )

    assert result == "photo.jpg"


def test_filename_whitespace_is_trimmed():
    result = Validator.validate_filename(
        "  photo.jpg  "
    )

    assert result == "photo.jpg"


def test_empty_filename_is_rejected():
    with pytest.raises(
        CompletionDocumentValidationError,
        match="Filename is required",
    ):
        Validator.validate_filename("")


# ---------------------------------------------------------------------------
# Actual content/signature mismatch
# ---------------------------------------------------------------------------

def test_invalid_jpeg_signature_is_rejected():
    with pytest.raises(
        CompletionDocumentValidationError,
        match="does not match JPEG",
    ):
        Validator.validate_file(
            file=io.BytesIO(b"this-is-not-a-jpeg"),
            content_type="image/jpeg",
            filename="photo.jpg",
            document_type="PHOTO",
            category="AFTER",
        )


def test_invalid_png_signature_is_rejected():
    with pytest.raises(
        CompletionDocumentValidationError,
        match="does not match PNG",
    ):
        Validator.validate_file(
            file=io.BytesIO(b"this-is-not-a-png"),
            content_type="image/png",
            filename="photo.png",
            document_type="PHOTO",
            category="AFTER",
        )


def test_invalid_pdf_signature_is_rejected():
    with pytest.raises(
        CompletionDocumentValidationError,
        match="does not match PDF",
    ):
        Validator.validate_file(
            file=io.BytesIO(b"this-is-not-a-pdf"),
            content_type="application/pdf",
            filename="manual.pdf",
            document_type="DOCUMENT",
            category="MANUAL",
        )


# ---------------------------------------------------------------------------
# Filename length
# ---------------------------------------------------------------------------

def test_filename_over_255_characters_is_rejected():
    filename = ("a" * 252) + ".jpg"

    with pytest.raises(
        CompletionDocumentValidationError,
        match="255 characters",
    ):
        Validator.validate_filename(filename)


# ---------------------------------------------------------------------------
# File size validation
# ---------------------------------------------------------------------------

def test_file_under_maximum_size_succeeds():
    size = Validator.MAX_FILE_SIZE - 1

    file_bytes = (
        JPEG_BYTES
        + b"x" * (size - len(JPEG_BYTES))
    )

    result = Validator.validate_file(
        file=io.BytesIO(file_bytes),
        content_type="image/jpeg",
        filename="under-limit.jpg",
        document_type="PHOTO",
        category="AFTER",
    )

    assert result[2] == Validator.MAX_FILE_SIZE - 1


def test_file_exactly_at_maximum_size_succeeds():
    size = Validator.MAX_FILE_SIZE

    file_bytes = (
        JPEG_BYTES
        + b"x" * (size - len(JPEG_BYTES))
    )

    result = Validator.validate_file(
        file=io.BytesIO(file_bytes),
        content_type="image/jpeg",
        filename="exact-limit.jpg",
        document_type="PHOTO",
        category="AFTER",
    )

    assert result[2] == Validator.MAX_FILE_SIZE


def test_file_over_maximum_size_is_rejected():
    size = Validator.MAX_FILE_SIZE + 1

    file_bytes = (
        JPEG_BYTES
        + b"x" * (size - len(JPEG_BYTES))
    )

    with pytest.raises(
        CompletionDocumentValidationError
    ) as exc_info:
        Validator.validate_file(
            file=io.BytesIO(file_bytes),
            content_type="image/jpeg",
            filename="over-limit.jpg",
            document_type="PHOTO",
            category="AFTER",
        )

    error = exc_info.value

    assert error.max_size_bytes == Validator.MAX_FILE_SIZE
    assert error.received_size_bytes == Validator.MAX_FILE_SIZE + 1

    assert error.details["max_size_bytes"] == (
        Validator.MAX_FILE_SIZE
    )

    assert error.details["received_size_bytes"] == (
        Validator.MAX_FILE_SIZE + 1
    )


def test_configured_maximum_file_size_has_expected_default():
    assert Validator.MAX_FILE_SIZE == 10 * 1024 * 1024