from enum import Enum


class AITask(str, Enum):
    PLANNING = "planning"
    DISPATCH = "dispatch"
    MONITORING = "monitoring"
    COMMUNICATION = "communication"
    CLOSURE = "closure"
    SENTIMENT = "sentiment"
    INTENT = "intent"
    INTAKE = "intake"