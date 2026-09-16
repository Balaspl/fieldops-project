"""
FieldOps MFA service.

Security model:
- TOTP is used as the second authentication factor.
- TOTP secrets are encrypted at rest using MFA_ENCRYPTION_KEY.
- Recovery codes are stored only as SHA-256 hashes.
- MFA challenges are short-lived and stored in Redis.
- MFA challenges are single-use and tenant-scoped.
- MFA is required only for protected FieldOps roles.
- MFA challenges are invalidated after too many failed attempts.
"""

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.models import MFA, MFARecoveryCode
from app.redis_client import get_redis_client


# ---------------------------------------------------------------------------
# MFA policy
# ---------------------------------------------------------------------------

MFA_REQUIRED_ROLES = {
    "TECHNICIAN",
    "DISPATCHER",
    "SUPER_ADMIN",
}

MFA_CHALLENGE_TTL_SECONDS = 300
MFA_MAX_ATTEMPTS = 5
RECOVERY_CODE_COUNT = 10


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    """
    Create the Fernet encryption handler from MFA_ENCRYPTION_KEY.

    The encryption key must come from the environment.
    It must never be hard-coded in source code.
    """
    key = os.getenv("MFA_ENCRYPTION_KEY")

    if not key:
        raise RuntimeError(
            "MFA_ENCRYPTION_KEY is not configured"
        )

    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError(
            "MFA_ENCRYPTION_KEY is invalid"
        ) from exc


def encrypt_secret(secret: str) -> str:
    """Encrypt a TOTP secret before database storage."""
    return _get_fernet().encrypt(
        secret.encode("utf-8")
    ).decode("utf-8")


def decrypt_secret(encrypted_secret: str) -> str:
    """Decrypt a stored TOTP secret."""
    try:
        return _get_fernet().decrypt(
            encrypted_secret.encode("utf-8")
        ).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Unable to decrypt MFA secret"
        ) from exc


# ---------------------------------------------------------------------------
# Role policy
# ---------------------------------------------------------------------------

def normalize_role(role: Any) -> str:
    """
    Normalize role values so both enum-style and string-style roles work.
    """
    if role is None:
        return ""

    value = getattr(role, "value", role)

    return str(value).strip().upper()


def is_mfa_required_for_role(role: Any) -> bool:
    """Return whether the user's role is protected by MFA."""
    return normalize_role(role) in MFA_REQUIRED_ROLES


# ---------------------------------------------------------------------------
# TOTP enrollment
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Generate a cryptographically secure TOTP secret."""
    return pyotp.random_base32()


def build_totp_provisioning_uri(
    secret: str,
    user_email: str,
    issuer: str = "FieldOps",
) -> str:
    """
    Build an otpauth URI for authenticator applications.

    This URI contains the secret and therefore MUST NOT be logged.
    """
    return pyotp.TOTP(secret).provisioning_uri(
        name=user_email,
        issuer_name=issuer,
    )


def create_enrollment_secret(
    user_email: str,
) -> Tuple[str, str, str]:
    """
    Generate temporary enrollment information.

    Returns:
        raw_secret
        encrypted_secret
        provisioning_uri

    The raw secret should only be returned to the enrollment flow so the
    user can configure their authenticator application.

    It must never be persisted or logged in plaintext.
    """
    secret = generate_totp_secret()

    encrypted_secret = encrypt_secret(secret)

    provisioning_uri = build_totp_provisioning_uri(
        secret=secret,
        user_email=user_email,
    )

    return secret, encrypted_secret, provisioning_uri


def verify_totp(
    secret: str,
    code: str,
) -> bool:
    """
    Verify a six-digit TOTP code.

    A small clock-drift window is allowed.
    """
    if not code:
        return False

    normalized_code = str(code).strip()

    if not normalized_code.isdigit():
        return False

    if len(normalized_code) != 6:
        return False

    totp = pyotp.TOTP(secret)

    return bool(
        totp.verify(
            normalized_code,
            valid_window=1,
        )
    )


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------

def _hash_recovery_code(code: str) -> str:
    """
    Hash a recovery code before database storage.

    Recovery codes are generated with high entropy, so SHA-256 is suitable
    for these random, single-use secrets.
    """
    normalized = code.strip().upper()

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def generate_recovery_codes(
    count: int = RECOVERY_CODE_COUNT,
) -> List[str]:
    """
    Generate one-time recovery codes.

    The plaintext codes are returned only once to the enrollment flow.
    """
    codes: List[str] = []

    for _ in range(count):
        # 16 random hexadecimal characters = 64 bits of randomness.
        raw = secrets.token_hex(8).upper()

        # Make the code easier to read.
        code = (
            f"{raw[:4]}-"
            f"{raw[4:8]}-"
            f"{raw[8:12]}-"
            f"{raw[12:]}"
        )

        codes.append(code)

    return codes


def hash_recovery_codes(
    codes: List[str],
) -> List[str]:
    """Return hashes for a collection of recovery codes."""
    return [
        _hash_recovery_code(code)
        for code in codes
    ]


# ---------------------------------------------------------------------------
# MFA database helpers
# ---------------------------------------------------------------------------

def get_user_mfa(
    db,
    user_id: str,
    tenant_id: str,
) -> Optional[MFA]:
    """
    Get MFA configuration with explicit tenant scoping.
    """
    return (
        db.query(MFA)
        .filter(
            MFA.user_id == user_id,
            MFA.tenant_id == tenant_id,
        )
        .first()
    )


def create_mfa_record(
    db,
    user_id: str,
    tenant_id: str,
    encrypted_secret: str,
) -> MFA:
    """
    Create an MFA record.

    MFA remains disabled until enrollment is successfully verified.
    """
    existing = get_user_mfa(
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    if existing:
        raise ValueError(
            "MFA configuration already exists"
        )

    mfa = MFA(
        user_id=user_id,
        tenant_id=tenant_id,
        secret_encrypted=encrypted_secret,
        enabled=False,
    )

    db.add(mfa)
    db.flush()

    return mfa


def save_recovery_codes(
    db,
    mfa: MFA,
    tenant_id: str,
    recovery_codes: List[str],
) -> None:
    """
    Replace recovery codes for an MFA configuration.

    Only hashes are stored.
    """
    # Delete existing recovery codes.
    for existing_code in list(mfa.recovery_codes):
        db.delete(existing_code)

    # Store only hashes.
    for code in recovery_codes:
        recovery = MFARecoveryCode(
            mfa_id=mfa.id,
            tenant_id=tenant_id,
            code_hash=_hash_recovery_code(code),
            used=False,
        )

        db.add(recovery)

    mfa.recovery_codes_generated_at = datetime.now(
        timezone.utc
    )

    db.flush()


def verify_recovery_code(
    db,
    mfa: MFA,
    tenant_id: str,
    supplied_code: str,
) -> bool:
    """
    Verify and consume a recovery code.

    A recovery code can only be used once.
    """
    if not supplied_code:
        return False

    code_hash = _hash_recovery_code(
        supplied_code
    )

    recovery = (
        db.query(MFARecoveryCode)
        .filter(
            MFARecoveryCode.mfa_id == mfa.id,
            MFARecoveryCode.tenant_id == tenant_id,
            MFARecoveryCode.code_hash == code_hash,
            MFARecoveryCode.used.is_(False),
        )
        .first()
    )

    if recovery is None:
        return False

    recovery.used = True
    recovery.used_at = datetime.now(
        timezone.utc
    )

    db.flush()

    return True


# ---------------------------------------------------------------------------
# Redis MFA challenges
# ---------------------------------------------------------------------------

def _challenge_key(challenge_id: str) -> str:
    return f"mfa:challenge:{challenge_id}"


def _challenge_attempts_key(challenge_id: str) -> str:
    return f"{_challenge_key(challenge_id)}:attempts"


def create_mfa_challenge(
    user_id: str,
    tenant_id: str,
) -> str:
    """
    Create a short-lived MFA challenge.

    The challenge contains only identity/context information.
    It does NOT contain the TOTP secret.
    """
    challenge_id = secrets.token_urlsafe(32)

    payload = {
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "attempts": 0,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    redis = get_redis_client()

    success = redis.setex(
        _challenge_key(challenge_id),
        MFA_CHALLENGE_TTL_SECONDS,
        json.dumps(payload),
    )

    if not success:
        raise RuntimeError(
            "Unable to create MFA challenge"
        )

    return challenge_id


def get_mfa_challenge(
    challenge_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve an MFA challenge from Redis.
    """
    if not challenge_id:
        return None

    redis = get_redis_client()

    raw = redis.get(
        _challenge_key(challenge_id)
    )

    if not raw:
        return None

    try:
        return json.loads(raw)
    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return None


def increment_challenge_attempts(
    challenge_id: str,
) -> Optional[int]:
    """
    Increment failed-attempt counter.

    The attempts counter is stored in a separate Redis key with
    the same TTL as the MFA challenge.
    """
    if not challenge_id:
        return None

    redis = get_redis_client()

    challenge_key = _challenge_key(
        challenge_id
    )

    attempts_key = _challenge_attempts_key(
        challenge_id
    )

    # Verify that the actual challenge still exists.
    if not redis.get(challenge_key):
        return None

    attempts = redis.incr(
        attempts_key,
        1,
    )

    if attempts is None:
        return None

    # Keep the counter alive only for the lifetime
    # of the MFA challenge.
    redis.expire(
        attempts_key,
        MFA_CHALLENGE_TTL_SECONDS,
    )

    return attempts


def get_challenge_attempts(
    challenge_id: str,
) -> int:
    """
    Return the current number of failed attempts.
    """
    if not challenge_id:
        return 0

    redis = get_redis_client()

    raw = redis.get(
        _challenge_attempts_key(
            challenge_id
        )
    )

    if raw is None:
        return 0

    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def consume_mfa_challenge(
    challenge_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Atomically consume an MFA challenge.

    Once consumed, the same challenge cannot be used again.
    """
    if not challenge_id:
        return None

    redis = get_redis_client()

    raw = redis.get_and_delete(
        _challenge_key(challenge_id)
    )

    # Clean up the attempts counter as well.
    redis.delete(
        _challenge_attempts_key(
            challenge_id
        )
    )

    if not raw:
        return None

    try:
        return json.loads(raw)
    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return None


def delete_mfa_challenge(
    challenge_id: str,
) -> bool:
    """
    Delete a challenge and its attempt counter.
    """
    if not challenge_id:
        return False

    redis = get_redis_client()

    challenge_deleted = redis.delete(
        _challenge_key(challenge_id)
    )

    redis.delete(
        _challenge_attempts_key(
            challenge_id
        )
    )

    return challenge_deleted


# ---------------------------------------------------------------------------
# MFA verification
# ---------------------------------------------------------------------------

def verify_mfa_challenge(
    db,
    challenge_id: str,
    code: str,
    tenant_id: str,
) -> Tuple[bool, Optional[str]]:
    """
    Verify an MFA challenge.

    Returns:
        (success, user_id)

    Security properties:
    - Challenge must exist.
    - Challenge must belong to the supplied tenant.
    - Maximum failed attempts are enforced.
    - Challenge is consumed only after successful verification.
    - TOTP secret is never returned.
    - Replay of a consumed challenge is rejected.
    """
    challenge = get_mfa_challenge(
        challenge_id
    )

    if challenge is None:
        return False, None

    challenge_user_id = str(
        challenge.get("user_id", "")
    )

    challenge_tenant_id = str(
        challenge.get("tenant_id", "")
    )

    if not challenge_user_id:
        return False, None

    if challenge_tenant_id != str(tenant_id):
        return False, None

    # Check the failed-attempt limit before verifying.
    current_attempts = get_challenge_attempts(
        challenge_id
    )

    if current_attempts >= MFA_MAX_ATTEMPTS:
        delete_mfa_challenge(
            challenge_id
        )
        return False, None

    mfa = get_user_mfa(
        db=db,
        user_id=challenge_user_id,
        tenant_id=challenge_tenant_id,
    )

    if mfa is None or not mfa.enabled:
        return False, None

    try:
        secret = decrypt_secret(
            mfa.secret_encrypted
        )
    except ValueError:
        return False, None

    # Verify TOTP.
    if not verify_totp(
        secret,
        code,
    ):
        attempts = increment_challenge_attempts(
            challenge_id
        )

        # Invalidate challenge after maximum failures.
        if (
            attempts is not None
            and attempts >= MFA_MAX_ATTEMPTS
        ):
            delete_mfa_challenge(
                challenge_id
            )

        return False, None

    # Atomically consume only after successful
    # TOTP verification.
    consumed = consume_mfa_challenge(
        challenge_id
    )

    if consumed is None:
        # Another request already consumed it.
        return False, None

    # Verify the consumed challenge still belongs
    # to the expected tenant/user.
    if (
        str(consumed.get("user_id", ""))
        != challenge_user_id
        or
        str(consumed.get("tenant_id", ""))
        != challenge_tenant_id
    ):
        return False, None

    mfa.last_used_at = datetime.now(
        timezone.utc
    )

    db.flush()

    return True, challenge_user_id


# ---------------------------------------------------------------------------
# Recovery verification
# ---------------------------------------------------------------------------

def verify_mfa_recovery(
    db,
    challenge_id: str,
    recovery_code: str,
    tenant_id: str,
) -> Tuple[bool, Optional[str]]:
    """
    Verify MFA using a one-time recovery code.

    Recovery codes are single-use.

    The MFA challenge is consumed only after the recovery
    code succeeds.
    """
    challenge = get_mfa_challenge(
        challenge_id
    )

    if challenge is None:
        return False, None

    user_id = str(
        challenge.get("user_id", "")
    )

    challenge_tenant_id = str(
        challenge.get("tenant_id", "")
    )

    if not user_id:
        return False, None

    if challenge_tenant_id != str(tenant_id):
        return False, None

    # Enforce the same failed-attempt limit for
    # recovery-code authentication.
    current_attempts = get_challenge_attempts(
        challenge_id
    )

    if current_attempts >= MFA_MAX_ATTEMPTS:
        delete_mfa_challenge(
            challenge_id
        )
        return False, None

    mfa = get_user_mfa(
        db=db,
        user_id=user_id,
        tenant_id=challenge_tenant_id,
    )

    if mfa is None or not mfa.enabled:
        return False, None

    success = verify_recovery_code(
        db=db,
        mfa=mfa,
        tenant_id=challenge_tenant_id,
        supplied_code=recovery_code,
    )

    if not success:
        attempts = increment_challenge_attempts(
            challenge_id
        )

        if (
            attempts is not None
            and attempts >= MFA_MAX_ATTEMPTS
        ):
            delete_mfa_challenge(
                challenge_id
            )

        return False, None

    # Atomically consume the challenge after
    # successful recovery-code verification.
    consumed = consume_mfa_challenge(
        challenge_id
    )

    if consumed is None:
        return False, None

    if (
        str(consumed.get("user_id", ""))
        != user_id
        or
        str(consumed.get("tenant_id", ""))
        != challenge_tenant_id
    ):
        return False, None

    mfa.last_used_at = datetime.now(
        timezone.utc
    )

    db.flush()

    return True, user_id