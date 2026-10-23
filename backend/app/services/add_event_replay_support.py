"""
add_event_replay_support.py

Direct alias module for ConsumerEventReplay service, ensuring exact naming conformity
with the story specification ("Add event replay support").
"""

from app.services.consumer_event_replay import (
    ConsumerEventReplay,
    EventReplayReceipt,
    AddEventReplaySupport,
    Add_event_replay_support,
    EventReplayService,
    ControlledEventReplay,
)

__all__ = [
    "ConsumerEventReplay",
    "EventReplayReceipt",
    "AddEventReplaySupport",
    "Add_event_replay_support",
    "EventReplayService",
    "ControlledEventReplay",
]

