"""Structured contracts for customer support responses."""

from pydantic import BaseModel, ConfigDict, Field


class CustomerSupportAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=3000)
    intent: str = Field(min_length=1, max_length=40)
    needs_human_support: bool = False
