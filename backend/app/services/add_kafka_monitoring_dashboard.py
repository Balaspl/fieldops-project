"""
add_kafka_monitoring_dashboard.py

Direct alias module for KafkaMonitoringDashboard service, ensuring exact naming conformity
with the story specification ("Add Kafka monitoring dashboard").
"""

from app.services.kafka_monitoring_dashboard import (
    KafkaMonitoringDashboard,
    DashboardReceipt,
    AddKafkaMonitoringDashboard,
    Add_kafka_monitoring_dashboard,
    ConsumerKafkaMonitoringDashboard,
    KafkaDashboardService,
)

__all__ = [
    "KafkaMonitoringDashboard",
    "DashboardReceipt",
    "AddKafkaMonitoringDashboard",
    "Add_kafka_monitoring_dashboard",
    "ConsumerKafkaMonitoringDashboard",
    "KafkaDashboardService",
]

