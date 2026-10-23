"""
add_event_schema_versioning.py

Direct alias module for EventSchemaVersioning service, ensuring exact naming conformity
with the story specification ("Add event schema versioning").
"""

from app.services.event_schema_versioning import (
    EventSchemaVersioning,
    SchemaVersioningReceipt,
    CompatibilityMode,
    AddEventSchemaVersioning,
    Add_event_schema_versioning,
    ConsumerEventSchemaVersioning,
    SchemaCompatibilityManager,
    SchemaVersioningService,
    upcast_v1_to_v2,
    downcast_v2_to_v1,
)

__all__ = [
    "EventSchemaVersioning",
    "SchemaVersioningReceipt",
    "CompatibilityMode",
    "AddEventSchemaVersioning",
    "Add_event_schema_versioning",
    "ConsumerEventSchemaVersioning",
    "SchemaCompatibilityManager",
    "SchemaVersioningService",
    "upcast_v1_to_v2",
    "downcast_v2_to_v1",
]

