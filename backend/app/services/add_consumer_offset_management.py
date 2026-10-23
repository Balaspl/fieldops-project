"""
add_consumer_offset_management.py

Direct alias module for ConsumerOffsetManagement service, ensuring exact naming conformity
with the story specification ("Add consumer offset management").
"""

from app.services.consumer_offset_management import (
    ConsumerOffsetManagement,
    OffsetCommitReceipt,
    AddConsumerOffsetManagement,
    Add_consumer_offset_management,
    ConsumerOffsetManager,
    OffsetManagementService,
)

__all__ = [
    "ConsumerOffsetManagement",
    "OffsetCommitReceipt",
    "AddConsumerOffsetManagement",
    "Add_consumer_offset_management",
    "ConsumerOffsetManager",
    "OffsetManagementService",
]

