import pytest

from app.input_security import (
    InputTooLongError,
    InvalidFilenameError,
    InvalidURLError,
    InvalidURLSchemeError,
    UnsafeControlCharacterError,
    normalize_text,
    validate_filename,
    validate_header_name,
    validate_header_value,
    validate_plain_text,
    validate_url,
)


# ============================================================================
# normalize_text
# ============================================================================


def test_normalize_text_strips_outer_whitespace():
    result = normalize_text("   Hello World   ")

    assert result == "Hello World"


def test_normalize_text_preserves_legitimate_business_text():
    value = """Customer's AC unit – requires inspection & repair."""

    result = normalize_text(value)

    assert result == value


def test_normalize_text_preserves_unicode():
    values = [
        "José",
        "தமிழ்",
        "日本語",
        "हिन्दी",
        "Café",
    ]

    for value in values:
        assert normalize_text(value) == value


def test_normalize_text_normalizes_unicode_to_nfc():
    value = "Cafe\u0301"

    result = normalize_text(value)

    assert result == "Café"


def test_normalize_text_rejects_null_character():
    with pytest.raises(UnsafeControlCharacterError):
        normalize_text("hello\x00world")


def test_normalize_text_rejects_carriage_return():
    with pytest.raises(UnsafeControlCharacterError):
        normalize_text("hello\rworld")


def test_normalize_text_rejects_escape_character():
    with pytest.raises(UnsafeControlCharacterError):
        normalize_text("hello\x1bworld")


def test_normalize_text_rejects_tab_by_default():
    with pytest.raises(UnsafeControlCharacterError):
        normalize_text("hello\tworld")


def test_normalize_text_allows_newlines_when_explicitly_enabled():
    value = "line one\nline two"

    result = normalize_text(
        value,
        allow_newlines=True,
    )

    assert result == value


def test_normalize_text_enforces_max_length():
    with pytest.raises(InputTooLongError):
        normalize_text(
            "A" * 101,
            max_length=100,
        )


def test_normalize_text_does_not_strip_html():
    value = "<b>Hello</b>"

    result = normalize_text(value)

    assert result == value


def test_normalize_text_can_collapse_whitespace():
    value = "Hello     World"

    result = normalize_text(
        value,
        collapse_whitespace=True,
    )

    assert result == "Hello World"


# ============================================================================
# validate_plain_text
# ============================================================================


def test_validate_plain_text_accepts_normal_text():
    value = "Customer needs AC service"

    assert validate_plain_text(value) == value


def test_validate_plain_text_accepts_business_punctuation():
    value = """Customer's unit is near the "main entrance"."""

    assert validate_plain_text(value) == value


def test_validate_plain_text_rejects_script_payload_control_characters():
    value = "<script>alert('xss')</script>\x00"

    with pytest.raises(UnsafeControlCharacterError):
        validate_plain_text(value)


# ============================================================================
# URL validation
# ============================================================================


def test_validate_url_accepts_https():
    value = "https://example.com"

    assert validate_url(value) == value


def test_validate_url_accepts_http():
    value = "http://example.com"

    assert validate_url(value) == value


def test_validate_url_rejects_javascript_scheme():
    with pytest.raises(InvalidURLSchemeError):
        validate_url("javascript:alert(1)")


def test_validate_url_rejects_data_scheme():
    with pytest.raises(InvalidURLSchemeError):
        validate_url("data:text/html,<script>alert(1)</script>")


def test_validate_url_rejects_file_scheme():
    with pytest.raises(InvalidURLSchemeError):
        validate_url("file:///etc/passwd")


def test_validate_url_rejects_empty_url():
    with pytest.raises(InvalidURLError):
        validate_url("")


def test_validate_url_rejects_missing_hostname():
    with pytest.raises(InvalidURLError):
        validate_url("https://")


def test_validate_url_rejects_embedded_credentials():
    with pytest.raises(InvalidURLError):
        validate_url("https://user:password@example.com")


def test_validate_url_rejects_control_characters():
    with pytest.raises(UnsafeControlCharacterError):
        validate_url("https://example.com/\r\n")


def test_validate_url_rejects_excessively_long_url():
    with pytest.raises(Exception):
        validate_url(
            "https://example.com/" + ("a" * 3000),
            max_length=2048,
        )


# ============================================================================
# Header validation
# ============================================================================


def test_validate_header_name_accepts_valid_name():
    assert validate_header_name("X-Custom-Header") == "X-Custom-Header"


def test_validate_header_name_rejects_spaces():
    with pytest.raises(Exception):
        validate_header_name("X Custom Header")


def test_validate_header_name_rejects_newline():
    with pytest.raises(Exception):
        validate_header_name("X-Test\nInjected")


def test_validate_header_value_accepts_normal_value():
    value = "application/json"

    assert validate_header_value(value) == value


def test_validate_header_value_rejects_crlf():
    with pytest.raises(UnsafeControlCharacterError):
        validate_header_value(
            "normal-value\r\nX-Injected: true"
        )


def test_validate_header_value_rejects_null_character():
    with pytest.raises(UnsafeControlCharacterError):
        validate_header_value("hello\x00world")


# ============================================================================
# Filename validation
# ============================================================================


def test_validate_filename_accepts_normal_filename():
    value = "job-report.pdf"

    assert validate_filename(value) == value


def test_validate_filename_accepts_unicode_filename():
    value = "rapport-équipement.pdf"

    assert validate_filename(value) == value


def test_validate_filename_rejects_path_separator():
    with pytest.raises(InvalidFilenameError):
        validate_filename("../../secret.txt")


def test_validate_filename_rejects_windows_path():
    with pytest.raises(InvalidFilenameError):
        validate_filename(r"..\..\secret.txt")


def test_validate_filename_rejects_absolute_windows_path():
    with pytest.raises(InvalidFilenameError):
        validate_filename(r"C:\Windows\secret.txt")


def test_validate_filename_rejects_absolute_unix_path():
    with pytest.raises(InvalidFilenameError):
        validate_filename("/etc/passwd")


def test_validate_filename_rejects_control_character():
    with pytest.raises(InvalidFilenameError):
        validate_filename("report\x00.pdf")


def test_validate_filename_rejects_dot():
    with pytest.raises(InvalidFilenameError):
        validate_filename(".")


def test_validate_filename_rejects_double_dot():
    with pytest.raises(InvalidFilenameError):
        validate_filename("..")


def test_validate_filename_rejects_reserved_windows_name():
    with pytest.raises(InvalidFilenameError):
        validate_filename("CON.txt")


def test_validate_filename_rejects_trailing_dot():
    with pytest.raises(InvalidFilenameError):
        validate_filename("report.pdf.")


def test_validate_filename_rejects_trailing_space():
    with pytest.raises(InvalidFilenameError):
        validate_filename("report.pdf ")


def test_validate_filename_rejects_excessively_long_name():
    with pytest.raises(InputTooLongError):
        validate_filename(
            "a" * 300 + ".pdf",
            max_length=255,
        )