"""
response_parser.py

Purpose
-------
Convert raw LLM responses into validated Pydantic models.

The parser guarantees that only valid AI decisions
enter the FieldOps backend.
"""

import json
import logging
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError


# Generic Pydantic model type
T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class ResponseParser:
    """
    Parses AI responses into validated schema objects.
    """

    @staticmethod
    def parse(
        response: str,
        schema: Type[T],
        *,
        correlation_id: str | None = None,
    ) -> T:
        """
        Convert an LLM JSON response into a validated
        Pydantic model.

        Parameters
        ----------
        response
            Raw JSON string returned by the LLM.

        schema
            Target Pydantic schema.

        Returns
        -------
        T
            Validated Pydantic model.

        Raises
        ------
        ValueError
            If the AI returned invalid JSON.

        ValueError
            If the JSON does not match the expected schema.
        """

        # -------------------------------------------------
        # Step 1: Parse JSON
        # -------------------------------------------------

        try:
            data = json.loads(response)

        except json.JSONDecodeError as exc:
            logger.error(
                "AI_RESPONSE_JSON_INVALID schema=%s correlation_id=%s "
                "error_type=JSONDecodeError position=%s",
                schema.__name__,
                correlation_id,
                exc.pos,
                extra={
                    "schema": schema.__name__,
                    "correlation_id": correlation_id,
                    "error_type": "JSONDecodeError",
                    "position": exc.pos,
                },
            )
            raise ValueError("AI returned invalid JSON.") from exc

        # -------------------------------------------------
        # Step 2: Validate Schema
        # -------------------------------------------------

        try:
            return schema.model_validate(data)

        except ValidationError as exc:
            safe_fields = {
                "channel", "output", "title", "body", "tone", "confidence",
                "subject", "message", "text", "text_body", "html_body",
                "content_format", "actions", "payload",
            }
            error_details = exc.errors(include_input=False)
            fields = sorted(
                {
                    ".".join(str(part) for part in item.get("loc", ()) if str(part) in safe_fields)
                    for item in error_details
                }
                - {""}
            )
            error_types = sorted({str(item.get("type", "unknown")) for item in error_details})
            logger.error(
                "AI_RESPONSE_SCHEMA_INVALID schema=%s correlation_id=%s "
                "error_count=%s error_types=%s fields=%s",
                schema.__name__,
                correlation_id,
                len(error_details),
                ",".join(error_types[:8]),
                ",".join(fields[:12]),
                extra={
                    "schema": schema.__name__,
                    "correlation_id": correlation_id,
                    "error_count": len(error_details),
                    "error_types": error_types[:8],
                    "fields": fields[:12],
                },
            )
            raise ValueError(
                f"AI response does not match schema {schema.__name__}."
            ) from exc
