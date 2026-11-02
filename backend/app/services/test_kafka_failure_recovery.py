"""
test_kafka_failure_recovery.py

Authoritative alias module for Story 7.20: Test Kafka failure recovery.
Re-exports the core coordinators, receipts, and functions.
"""

from app.services.kafka_failure_recovery import (
    KafkaFailureRecoveryCoordinator,
    KafkaFailureRecoveryReceipt,
    TestKafkaFailureRecovery,
    Test_kafka_failure_recovery,
    KafkaFailureRecovery,
    KafkaFailureRecoveryService,
    KafkaFailureRecoveryManager,
    FailureMode,
)

__all__ = [
    "KafkaFailureRecoveryCoordinator",
    "KafkaFailureRecoveryReceipt",
    "TestKafkaFailureRecovery",
    "Test_kafka_failure_recovery",
    "KafkaFailureRecovery",
    "KafkaFailureRecoveryService",
    "KafkaFailureRecoveryManager",
    "FailureMode",
]

