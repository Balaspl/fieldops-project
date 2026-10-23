"""
add_failed_event_storage.py

Direct alias module for FailedEventStorage service, ensuring exact naming conformity
with the story specification ("Add failed-event storage").
"""

from app.services.failed_event_storage import (
    FailedEventStorage,
    FailedEventReceipt,
    AddFailedEventStorage,
    Add_failed_event_storage,
    ConsumerFailedEventStorage,
    FailedEventStorageService,
)

__all__ = [
    "FailedEventStorage",
    "FailedEventReceipt",
    "AddFailedEventStorage",
    "Add_failed_event_storage",
    "ConsumerFailedEventStorage",
    "FailedEventStorageService",
]

