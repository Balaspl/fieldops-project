"""
prevent_duplicate_event_processing.py

Direct alias module for ConsumerIdempotency service, ensuring exact naming conformity
with the story specification ("Prevent duplicate event processing").
"""

from app.services.consumer_idempotency import (
    ConsumerIdempotency,
    IdempotencyReceipt,
    PreventDuplicateEventProcessing,
    Prevent_duplicate_event_processing,
    ConsumerIdempotencyService,
    EventIdempotencyManager,
    IdempotentConsumer,
)

__all__ = [
    "ConsumerIdempotency",
    "IdempotencyReceipt",
    "PreventDuplicateEventProcessing",
    "Prevent_duplicate_event_processing",
    "ConsumerIdempotencyService",
    "EventIdempotencyManager",
    "IdempotentConsumer",
]

