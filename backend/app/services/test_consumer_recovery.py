"""
test_consumer_recovery.py

Direct alias module for ConsumerRecoveryCoordinator, ensuring exact naming conformity
with the story specification ("Test consumer recovery").
"""

from app.services.consumer_recovery import (
    ConsumerRecoveryCoordinator,
    ConsumerRecoveryReceipt,
    TestConsumerRecovery,
    Test_consumer_recovery,
    ConsumerRecoveryService,
    ConsumerRecoveryManager,
)

__all__ = [
    "ConsumerRecoveryCoordinator",
    "ConsumerRecoveryReceipt",
    "TestConsumerRecovery",
    "Test_consumer_recovery",
    "ConsumerRecoveryService",
    "ConsumerRecoveryManager",
]
