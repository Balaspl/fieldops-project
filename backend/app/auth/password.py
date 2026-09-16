"""
Password hashing and verification using bcrypt.

Enterprise-grade password security:
- bcrypt with automatic salt generation
- Configurable work factor (default 12 rounds)
- Password strength validation
"""

from passlib.context import CryptContext
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

REQUIRE_UPPERCASE = True
REQUIRE_LOWERCASE = True
REQUIRE_DIGIT = True
REQUIRE_SPECIAL = True

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


class PasswordValidationError(Exception):
    """Raised when a password does not meet strength requirements."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_password_strength(password: str) -> None:
    """
    Validate password meets enterprise security requirements.

    Rules:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    
    Raises PasswordValidationError if any rule fails.
    """
    errors = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(
            f"Password must not exceed {MAX_PASSWORD_LENGTH} characters"
        )

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        errors.append("Password must contain at least one special character")

    if errors:
        raise PasswordValidationError(errors)
