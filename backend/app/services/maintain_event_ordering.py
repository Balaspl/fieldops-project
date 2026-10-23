"""
maintain_event_ordering.py

Direct alias module for ConsumerEventOrdering service, ensuring exact naming conformity
with the story specification ("Maintain event ordering").
"""

from app.services.consumer_event_ordering import (
    ConsumerEventOrdering,
    EventOrderingReceipt,
    MaintainEventOrdering,
    Maintain_event_ordering,
    ConsumerEventOrderingService,
    EventOrderingManager,
)

__all__ = [
    "ConsumerEventOrdering",
    "EventOrderingReceipt",
    "MaintainEventOrdering",
    "Maintain_event_ordering",
    "ConsumerEventOrderingService",
    "EventOrderingManager",
]

