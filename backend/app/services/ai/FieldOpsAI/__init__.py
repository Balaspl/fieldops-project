"""
FieldOps Commander AI package.

Contains AI agents, schemas, prompts, providers,
repositories, services, and runtime components.
"""

from app.celery_app import (
    AI_QUEUE,
    AI_ROUTING_KEY,
    get_ai_processing_queue_config,
    create_ai_processing_queue,
    CreateAiProcessingQueue,
    Create_ai_processing_queue,
    CreateAiQueue,
    create_ai_queue,
)

__all__ = [
    "AI_QUEUE",
    "AI_ROUTING_KEY",
    "get_ai_processing_queue_config",
    "create_ai_processing_queue",
    "CreateAiProcessingQueue",
    "Create_ai_processing_queue",
    "CreateAiQueue",
    "create_ai_queue",
]
