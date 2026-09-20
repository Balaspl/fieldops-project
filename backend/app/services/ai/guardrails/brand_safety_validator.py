"""
brand_safety_validator.py

Deterministic brand-safety validation for FieldOps-generated
communication.

The validator checks recipient-facing content for:

- Configured competitor mentions
- Political promotion
- Off-brand language
- Administrator-blocked phrases

Rules are supplied through BrandSafetyRuleProvider.

The current implementation includes:

- StaticBrandSafetyRuleProvider for default rules and tests
- Dependency injection for a future database/Redis provider

The validator never stores:

- Generated communication content
- The matched phrase
- Customer or technician information

Only audit-safe rule IDs, categories, match types, and counts are
included in guardrail violations.
"""

from __future__ import annotations

import re

from enum import StrEnum
from functools import lru_cache
from time import perf_counter
from typing import Final, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.services.ai.FieldOpsAI.schemas.communication import (
    CommunicationContext,
    CommunicationDecision,
)
from app.services.ai.guardrails.contracts import (
    GuardrailCategory,
    GuardrailCheckResult,
    GuardrailField,
    GuardrailSeverity,
    GuardrailViolation,
)


# ==========================================================
# Brand-Safety Rule Contracts
# ==========================================================


class BrandSafetyRuleCategory(StrEnum):
    """
    Supported brand-safety rule categories.
    """

    COMPETITOR = "COMPETITOR"
    POLITICAL = "POLITICAL"
    OFF_BRAND = "OFF_BRAND"
    BLOCKED_PHRASE = "BLOCKED_PHRASE"


class BrandSafetyMatchType(StrEnum):
    """
    Supported deterministic matching strategies.

    WORD:
        Matches one complete word or term.

    PHRASE:
        Matches a complete phrase while allowing differences in
        whitespace between words.
    """

    WORD = "WORD"
    PHRASE = "PHRASE"


class BrandSafetyRule(BaseModel):
    """
    One configurable brand-safety rule.

    Actual competitor names or blocked phrases remain inside the
    rule provider. They are not copied into guardrail violations.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        frozen=True,
    )

    rule_id: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description=(
            "Stable uppercase machine-readable rule ID."
        ),
    )

    category: BrandSafetyRuleCategory = Field(
        ...,
        description="Business category for the rule.",
    )

    match_type: BrandSafetyMatchType = Field(
        ...,
        description="How the configured pattern is matched.",
    )

    pattern: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description=(
            "Configured word or phrase. This value must not be "
            "copied into violation metadata."
        ),
    )

    severity: GuardrailSeverity = Field(
        default=GuardrailSeverity.ERROR,
        description="Severity returned when the rule matches.",
    )

    active: bool = Field(
        default=True,
        description="Whether this rule should currently run.",
    )

    case_sensitive: bool = Field(
        default=False,
        description="Whether matching should respect case.",
    )

    # ------------------------------------------------------

    @field_validator(
        "pattern"
    )
    @classmethod
    def validate_pattern_contains_text(
        cls,
        value: str,
    ) -> str:
        """
        Reject patterns containing only punctuation or symbols.
        """

        if not any(
            character.isalnum()
            for character in value
        ):
            raise ValueError(
                "Brand-safety pattern must contain at least "
                "one letter or number."
            )

        return value

    # ------------------------------------------------------

    @model_validator(
        mode="after"
    )
    def validate_match_type(
        self,
    ) -> BrandSafetyRule:
        """
        WORD rules must contain one term without whitespace.
        """

        if (
            self.match_type
            == BrandSafetyMatchType.WORD
            and any(
                character.isspace()
                for character in self.pattern
            )
        ):
            raise ValueError(
                "WORD brand-safety rules cannot contain "
                "whitespace. Use PHRASE instead."
            )

        return self


# ==========================================================
# Rule Provider
# ==========================================================


@runtime_checkable
class BrandSafetyRuleProvider(
    Protocol
):
    """
    Interface used to retrieve active brand-safety rules.

    A future implementation may load tenant-specific rules from:

    - Database
    - Redis cache
    - Administrator configuration service
    """

    def get_rules(
        self,
        *,
        context: CommunicationContext,
    ) -> tuple[
        BrandSafetyRule,
        ...,
    ]:
        """
        Return rules applicable to the current communication.
        """

        ...


class StaticBrandSafetyRuleProvider:
    """
    In-memory rule provider.

    Used for:

    - Default platform rules
    - Unit testing
    - Local development
    - Dependency-injected competitor rules
    """

    def __init__(
        self,
        rules: tuple[
            BrandSafetyRule,
            ...,
        ]
        | list[
            BrandSafetyRule
        ],
    ) -> None:
        """
        Store an immutable copy of the supplied rules.
        """

        self._rules = tuple(
            rules
        )

    # ------------------------------------------------------

    def get_rules(
        self,
        *,
        context: CommunicationContext,
    ) -> tuple[
        BrandSafetyRule,
        ...,
    ]:
        """
        Return the configured static rules.

        The context argument is accepted so this provider follows
        the same interface as future tenant-aware providers.
        """

        _ = context

        return self._rules


# ==========================================================
# Default Platform Rules
# ==========================================================


@lru_cache(
    maxsize=1
)
def default_brand_safety_rules() -> tuple[
    BrandSafetyRule,
    ...,
]:
    """
    Return default platform-level brand-safety rules.

    Competitor names are intentionally not included here because
    they must be configured by an administrator or tenant.

    These defaults cover obvious political, off-brand, and
    unsupported-promise phrases.
    """

    return (
        BrandSafetyRule(
            rule_id="POLITICAL_VOTE_FOR",
            category=BrandSafetyRuleCategory.POLITICAL,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="vote for",
        ),
        BrandSafetyRule(
            rule_id="POLITICAL_VOTE_AGAINST",
            category=BrandSafetyRuleCategory.POLITICAL,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="vote against",
        ),
        BrandSafetyRule(
            rule_id="POLITICAL_ELECTION_CAMPAIGN",
            category=BrandSafetyRuleCategory.POLITICAL,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="election campaign",
        ),
        BrandSafetyRule(
            rule_id="OFF_BRAND_NOT_OUR_PROBLEM",
            category=BrandSafetyRuleCategory.OFF_BRAND,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="not our problem",
        ),
        BrandSafetyRule(
            rule_id="OFF_BRAND_YOUR_FAULT",
            category=BrandSafetyRuleCategory.OFF_BRAND,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="your fault",
        ),
        BrandSafetyRule(
            rule_id="OFF_BRAND_STOP_COMPLAINING",
            category=BrandSafetyRuleCategory.OFF_BRAND,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="stop complaining",
        ),
        BrandSafetyRule(
            rule_id="OFF_BRAND_WE_DO_NOT_CARE",
            category=BrandSafetyRuleCategory.OFF_BRAND,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="we do not care",
        ),
        BrandSafetyRule(
            rule_id="BLOCKED_GUARANTEED_REFUND",
            category=BrandSafetyRuleCategory.BLOCKED_PHRASE,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="guaranteed refund",
        ),
        BrandSafetyRule(
            rule_id="BLOCKED_FULL_COMPENSATION",
            category=BrandSafetyRuleCategory.BLOCKED_PHRASE,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="full compensation",
        ),
        BrandSafetyRule(
            rule_id="BLOCKED_FREE_SERVICE",
            category=BrandSafetyRuleCategory.BLOCKED_PHRASE,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="free service",
        ),
        BrandSafetyRule(
            rule_id="BLOCKED_GUARANTEED_FIX",
            category=BrandSafetyRuleCategory.BLOCKED_PHRASE,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="guaranteed fix",
        ),
        BrandSafetyRule(
        rule_id="OFF_BRAND_CANCEL_SERVICE_THREAT",
        category=BrandSafetyRuleCategory.OFF_BRAND,
        match_type=BrandSafetyMatchType.PHRASE,
        pattern="cancel your service",
        ),
        BrandSafetyRule(
            rule_id="OFF_BRAND_COLLECTIONS_THREAT",
            category=BrandSafetyRuleCategory.OFF_BRAND,
            match_type=BrandSafetyMatchType.PHRASE,
            pattern="report you to collections",
        ),
            )


# ==========================================================
# Compiled Rule Helper
# ==========================================================


@lru_cache(
    maxsize=512
)
def _compile_rule_pattern(
    pattern: str,
    match_type: BrandSafetyMatchType,
    case_sensitive: bool,
) -> re.Pattern[str]:
    """
    Compile and cache one safe word or phrase pattern.

    Arbitrary administrator regex is intentionally not accepted.
    This avoids unsafe or expensive regular expressions.

    WORD example:
        Acme

    PHRASE example:
        Acme Services

    Phrase matching allows one or more whitespace characters
    between words.
    """

    flags = (
        0
        if case_sensitive
        else re.IGNORECASE
    )

    if (
        match_type
        == BrandSafetyMatchType.WORD
    ):
        expression = (
            r"(?<![A-Za-z0-9_])"
            + re.escape(
                pattern
            )
            + r"(?![A-Za-z0-9_])"
        )

        return re.compile(
            expression,
            flags,
        )

    words = pattern.split()

    phrase_expression = (
        r"\s+".join(
            re.escape(
                word
            )
            for word in words
        )
    )

    expression = (
        r"(?<![A-Za-z0-9_])"
        + phrase_expression
        + r"(?![A-Za-z0-9_])"
    )

    return re.compile(
        expression,
        flags,
    )


# ==========================================================
# Brand Safety Validator
# ==========================================================


class BrandSafetyValidator:
    """
    Detect configured brand-safety violations in generated
    communication.
    """

    checker_name: Final[str] = (
        "brand_safety_validator"
    )



    PLACEHOLDER_PATTERN: Final[
        re.Pattern[str]
    ] = re.compile(
        r"\{\{[A-Za-z][A-Za-z0-9_]*\}\}"
    )

    VIOLATION_CODES: Final[
        dict[
            BrandSafetyRuleCategory,
            str,
        ]
    ] = {
        BrandSafetyRuleCategory.COMPETITOR: (
            "BRAND_COMPETITOR_MENTION"
        ),
        BrandSafetyRuleCategory.POLITICAL: (
            "BRAND_POLITICAL_CONTENT"
        ),
        BrandSafetyRuleCategory.OFF_BRAND: (
            "BRAND_OFF_BRAND_LANGUAGE"
        ),
        BrandSafetyRuleCategory.BLOCKED_PHRASE: (
            "BRAND_BLOCKED_PHRASE"
        ),
    }

    SAFE_MESSAGES: Final[
        dict[
            BrandSafetyRuleCategory,
            str,
        ]
    ] = {
        BrandSafetyRuleCategory.COMPETITOR: (
            "Generated communication contains a configured "
            "competitor reference."
        ),
        BrandSafetyRuleCategory.POLITICAL: (
            "Generated communication contains prohibited "
            "political content."
        ),
        BrandSafetyRuleCategory.OFF_BRAND: (
            "Generated communication contains language that "
            "does not follow FieldOps brand standards."
        ),
        BrandSafetyRuleCategory.BLOCKED_PHRASE: (
            "Generated communication contains an "
            "administrator-blocked phrase."
        ),
    }

    # ------------------------------------------------------

    def __init__(
        self,
        rule_provider: (
            BrandSafetyRuleProvider
            | None
        ) = None,
    ) -> None:
        """
        Initialize the validator.

        When no provider is supplied, platform default rules are
        used.

        A custom provider can later supply tenant-specific rules
        from Redis or the database.
        """

        self._rule_provider = (
            rule_provider
            or StaticBrandSafetyRuleProvider(
                default_brand_safety_rules()
            )
        )

    # ------------------------------------------------------

    def check(
        self,
        *,
        context: CommunicationContext,
        decision: CommunicationDecision,
    ) -> GuardrailCheckResult:
        """
        Scan generated title, subject, and message.

        Each matching rule creates one audit-safe violation for
        the affected field.

        Multiple occurrences of the same rule in one field are
        represented by one violation containing a safe count.
        """

        from app.services.ai.FieldOpsAI.schemas.communication import output_text_for_validation

        started_at = perf_counter()

        rules = tuple(
            rule
            for rule in self._rule_provider.get_rules(
                context=context
            )
            if rule.active
        )

        violations: list[
            GuardrailViolation
        ] = []

        validation_text = output_text_for_validation(decision.output)
        
        if validation_text:
            safe_scannable_text = (
                self.PLACEHOLDER_PATTERN.sub(
                    " ",
                    validation_text,
                )
            )

            for rule in rules:
                compiled_pattern = (
                    _compile_rule_pattern(
                        rule.pattern,
                        rule.match_type,
                        rule.case_sensitive,
                    )
                )

                match_count = sum(
                    1
                    for _ in compiled_pattern.finditer(
                        safe_scannable_text
                    )
                )

                if match_count == 0:
                    continue

                violations.append(
                    GuardrailViolation(
                        code=(
                            self.VIOLATION_CODES[
                                rule.category
                            ]
                        ),
                        category=(
                            GuardrailCategory.BRAND_SAFETY
                        ),
                        severity=rule.severity,
                        message=(
                            self.SAFE_MESSAGES[
                                rule.category
                            ]
                        ),
                        field="output",
                        safe_metadata={
                            "rule_id": rule.rule_id,
                            "rule_category": (
                                rule.category.value
                            ),
                            "match_type": (
                                rule.match_type.value
                            ),
                            "match_count": match_count,
                        },
                    )
                )

        latency_ms = (
            perf_counter()
            - started_at
        ) * 1000

        return GuardrailCheckResult(
            checker_name=self.checker_name,
            passed=not violations,
            violations=tuple(
                violations
            ),
            latency_ms=latency_ms,
        )