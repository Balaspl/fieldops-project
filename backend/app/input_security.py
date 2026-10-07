"""
Centralized input-security utilities.

Purpose:
    - Normalize user-controlled text safely.
    - Reject dangerous control characters.
    - Enforce context-specific length limits.
    - Validate URLs without modifying their meaning.
    - Validate HTTP/header values.
    - Validate uploaded filenames/metadata.

Important:
    - Do NOT use these helpers for passwords, JWTs, API keys,
      cryptographic values, or other opaque secrets.
    - Do NOT globally strip HTML from user input.
    - HTML escaping belongs at the HTML/template output boundary.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath, PureWindowsPath
from typing import Iterable
from urllib.parse import urlsplit


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_TEXT_LENGTH = 10_000
DEFAULT_MAX_HEADER_LENGTH = 8_192
DEFAULT_MAX_FILENAME_LENGTH = 255

# ASCII control characters except TAB (\t) and NEWLINE (\n).
# Carriage return (\r) is deliberately rejected because it can participate
# in HTTP header injection and log manipulation.
_CONTROL_CHAR_RE = re.compile(
    r"[\x00-\x08\x0B\x0C\x0D\x0E-\x1F\x7F]"
)

# HTTP header names follow the RFC token grammar.
_HEADER_NAME_RE = re.compile(
    r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$"
)

# Characters that should never occur in filenames supplied by users.
_FILENAME_CONTROL_RE = re.compile(
    r"[\x00-\x1F\x7F]"
)

# Windows reserved device names.
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InputSecurityError(ValueError):
    """Base exception for unsafe user-controlled input."""


class UnsafeControlCharacterError(InputSecurityError):
    """Raised when forbidden control characters are detected."""


class InputTooLongError(InputSecurityError):
    """Raised when input exceeds its context-specific maximum length."""


class InvalidURLSchemeError(InputSecurityError):
    """Raised when a URL uses a disallowed scheme."""


class InvalidURLError(InputSecurityError):
    """Raised when a URL is malformed or unsafe."""


class InvalidHeaderError(InputSecurityError):
    """Raised when an HTTP header name/value is unsafe."""


class InvalidFilenameError(InputSecurityError):
    """Raised when an uploaded filename is unsafe."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_string(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    return value


def _check_length(
    value: str,
    *,
    max_length: int,
    field_name: str,
) -> None:
    if max_length < 0:
        raise ValueError("max_length must be non-negative")

    if len(value) > max_length:
        raise InputTooLongError(
            f"{field_name} exceeds the maximum allowed length "
            f"of {max_length} characters"
        )


def _find_control_characters(
    value: str,
    *,
    allow_tab: bool = False,
    allow_newline: bool = False,
) -> list[str]:
    """
    Return forbidden control characters found in value.

    By default all ASCII C0 controls and DEL are rejected.

    TAB and NEWLINE can be explicitly allowed for contexts where they are
    meaningful. Carriage return is never allowed.
    """
    found: list[str] = []

    for char in value:
        code = ord(char)

        if code == 0x09 and allow_tab:
            continue

        if code == 0x0A and allow_newline:
            continue

        if code == 0x0D:
            found.append(char)
            continue

        if 0x00 <= code <= 0x1F or code == 0x7F:
            found.append(char)

    return found


def reject_control_characters(
    value: str,
    *,
    field_name: str = "value",
    allow_tab: bool = False,
    allow_newline: bool = False,
) -> str:
    """
    Reject ASCII control characters.

    Returns the original value unchanged when safe.

    This function does NOT silently remove unsafe characters. Rejection is
    preferable for security-sensitive input because silent modification can
    hide attacks and unexpectedly change business data.
    """
    value = _ensure_string(value, field_name)

    found = _find_control_characters(
        value,
        allow_tab=allow_tab,
        allow_newline=allow_newline,
    )

    if found:
        codes = ", ".join(
            f"U+{ord(char):04X}"
            for char in sorted(set(found), key=ord)
        )

        raise UnsafeControlCharacterError(
            f"{field_name} contains forbidden control character(s): {codes}"
        )

    return value


# ---------------------------------------------------------------------------
# General text normalization
# ---------------------------------------------------------------------------


def normalize_text(
    value: str,
    *,
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
    field_name: str = "value",
    collapse_whitespace: bool = False,
    strip: bool = True,
    unicode_form: str = "NFC",
    reject_controls: bool = True,
    allow_newlines: bool = False,
) -> str:
    """
    Normalize ordinary user-controlled business text.

    Behavior:
        1. Validate string type.
        2. Unicode-normalize using NFC.
        3. Reject dangerous control characters.
        4. Optionally normalize whitespace.
        5. Optionally strip surrounding whitespace.
        6. Enforce final length.

    HTML is intentionally NOT stripped.
    """
    value = _ensure_string(value, field_name)

    if unicode_form not in {"NFC", "NFKC"}:
        raise ValueError(
            "unicode_form must be either 'NFC' or 'NFKC'"
        )

    # NFC is the default because it preserves the semantic appearance of
    # ordinary business text without aggressive compatibility conversion.
    normalized = unicodedata.normalize(unicode_form, value)

    if reject_controls:
        reject_control_characters(
            normalized,
            field_name=field_name,
            allow_tab=allow_newlines,
            allow_newline=allow_newlines,
        )

    if strip:
        normalized = normalized.strip()

    if collapse_whitespace:
        if allow_newlines:
            # Preserve line boundaries while collapsing repeated spaces/tabs.
            normalized = re.sub(r"[ \t]+", " ", normalized)
        else:
            normalized = re.sub(r"\s+", " ", normalized)

    _check_length(
        normalized,
        max_length=max_length,
        field_name=field_name,
    )

    return normalized


def validate_plain_text(
    value: str,
    *,
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
    field_name: str = "value",
    allow_newlines: bool = False,
) -> str:
    """
    Validate ordinary plain text without HTML sanitization.

    Useful for:
        - names
        - descriptions
        - addresses
        - SMS content
        - notes
        - customer messages
    """
    return normalize_text(
        value,
        max_length=max_length,
        field_name=field_name,
        collapse_whitespace=False,
        strip=True,
        unicode_form="NFC",
        reject_controls=True,
        allow_newlines=allow_newlines,
    )


# ---------------------------------------------------------------------------
# Identifier-like values
# ---------------------------------------------------------------------------


def normalize_identifier(
    value: str,
    *,
    max_length: int = 255,
    field_name: str = "identifier",
) -> str:
    """
    Normalize an identifier where surrounding whitespace is not meaningful.

    Use only for identifiers that are expected to be human-readable.

    Do NOT use for passwords, JWTs, API keys, signatures, or opaque tokens.
    """
    return normalize_text(
        value,
        max_length=max_length,
        field_name=field_name,
        collapse_whitespace=True,
        strip=True,
        unicode_form="NFC",
        reject_controls=True,
        allow_newlines=False,
    )


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def validate_url(
    value: str,
    *,
    field_name: str = "url",
    allowed_schemes: Iterable[str] = ("http", "https"),
    max_length: int = 2048,
    require_hostname: bool = True,
    allow_credentials: bool = False,
) -> str:
    """
    Validate a user-controlled URL.

    Default policy:
        - only HTTP/HTTPS
        - hostname required
        - credentials forbidden
        - control characters forbidden
        - length limited

    This function does not perform DNS resolution or SSRF protection by
    itself. Server-side URL fetching requires additional destination
    validation.
    """
    value = _ensure_string(value, field_name)

    # IMPORTANT:
    # Check the raw input BEFORE stripping or parsing it.
    # urlsplit() may remove CR/LF characters, which could otherwise make
    # malicious input appear safe.
    reject_control_characters(
        value,
        field_name=field_name,
    )

    value = unicodedata.normalize("NFC", value).strip()

    _check_length(
        value,
        max_length=max_length,
        field_name=field_name,
    )

    if not value:
        raise InvalidURLError(
            f"{field_name} cannot be empty"
        )

    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise InvalidURLError(
            f"{field_name} is malformed"
        ) from exc

    schemes = {
        scheme.lower()
        for scheme in allowed_schemes
    }

    if parsed.scheme.lower() not in schemes:
        raise InvalidURLSchemeError(
            f"{field_name} must use one of: "
            f"{', '.join(sorted(schemes))}"
        )

    if require_hostname and not parsed.hostname:
        raise InvalidURLError(
            f"{field_name} must contain a hostname"
        )

    if not allow_credentials and (
        parsed.username is not None
        or parsed.password is not None
    ):
        raise InvalidURLError(
            f"{field_name} must not contain embedded credentials"
        )

    try:
        _ = parsed.port
    except ValueError as exc:
        raise InvalidURLError(
            f"{field_name} contains an invalid port"
        ) from exc

    return value

# ---------------------------------------------------------------------------
# HTTP header validation
# ---------------------------------------------------------------------------


def validate_header_name(
    value: str,
    *,
    field_name: str = "header_name",
    max_length: int = 256,
) -> str:
    """
    Validate an HTTP header name.
    """
    value = _ensure_string(value, field_name)

    if not value:
        raise InvalidHeaderError(
            f"{field_name} cannot be empty"
        )

    _check_length(
        value,
        max_length=max_length,
        field_name=field_name,
    )

    if not _HEADER_NAME_RE.fullmatch(value):
        raise InvalidHeaderError(
            f"{field_name} contains invalid HTTP header characters"
        )

    return value


def validate_header_value(
    value: str,
    *,
    field_name: str = "header_value",
    max_length: int = DEFAULT_MAX_HEADER_LENGTH,
) -> str:
    """
    Validate an HTTP header value.

    CR/LF are always rejected to prevent header injection.
    Other ASCII control characters are also rejected.
    """
    value = _ensure_string(value, field_name)

    _check_length(
        value,
        max_length=max_length,
        field_name=field_name,
    )

    reject_control_characters(
        value,
        field_name=field_name,
    )

    return value


# ---------------------------------------------------------------------------
# Uploaded filename validation
# ---------------------------------------------------------------------------


def validate_filename(
    value: str,
    *,
    field_name: str = "filename",
    max_length: int = DEFAULT_MAX_FILENAME_LENGTH,
) -> str:
    """
    Validate an uploaded filename.

    This function validates the filename only. It does not decide whether
    an extension/content type is allowed for a particular upload endpoint.
    """
    value = _ensure_string(value, field_name)

    value = unicodedata.normalize("NFC", value)

    _check_length(
        value,
        max_length=max_length,
        field_name=field_name,
    )

    if not value:
        raise InvalidFilenameError(
            f"{field_name} cannot be empty"
        )

    if _FILENAME_CONTROL_RE.search(value):
        raise InvalidFilenameError(
            f"{field_name} contains control characters"
        )

    # Reject both POSIX and Windows separators.
    if "/" in value or "\\" in value:
        raise InvalidFilenameError(
            f"{field_name} must not contain path separators"
        )

    # Reject traversal-style names.
    if value in {".", ".."}:
        raise InvalidFilenameError(
            f"{field_name} is not a valid filename"
        )

    # Check Windows reserved device names.
    stem = value.split(".", 1)[0].upper()

    if stem in _WINDOWS_RESERVED_NAMES:
        raise InvalidFilenameError(
            f"{field_name} uses a reserved filename"
        )

    # Reject trailing dots/spaces because Windows filesystem semantics
    # can normalize these unexpectedly.
    if value.endswith((" ", ".")):
        raise InvalidFilenameError(
            f"{field_name} must not end with a space or dot"
        )

    return value


# ---------------------------------------------------------------------------
# Generic safe-field helper
# ---------------------------------------------------------------------------


def validate_user_text(
    value: str,
    *,
    max_length: int,
    field_name: str,
    allow_newlines: bool = False,
    collapse_whitespace: bool = False,
) -> str:
    """
    Convenience wrapper for normal user-controlled business text.
    """
    return normalize_text(
        value,
        max_length=max_length,
        field_name=field_name,
        collapse_whitespace=collapse_whitespace,
        strip=True,
        unicode_form="NFC",
        reject_controls=True,
        allow_newlines=allow_newlines,
    )


__all__ = [
    "InputSecurityError",
    "UnsafeControlCharacterError",
    "InputTooLongError",
    "InvalidURLSchemeError",
    "InvalidURLError",
    "InvalidHeaderError",
    "InvalidFilenameError",
    "normalize_text",
    "normalize_identifier",
    "validate_plain_text",
    "validate_user_text",
    "reject_control_characters",
    "validate_url",
    "validate_header_name",
    "validate_header_value",
    "validate_filename",
]