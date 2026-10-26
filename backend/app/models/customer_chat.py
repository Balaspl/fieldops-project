"""Persisted, tenant scoped customer support chat data."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from ..database import Base


class CustomerChatConversation(Base):
    __tablename__ = "customer_chat_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    customer_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="OPEN", server_default="OPEN")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_customer_chat_conversation_status"),
        Index("ix_customer_chat_conversations_owner_updated", "tenant_id", "customer_user_id", "updated_at"),
    )


class CustomerChatMessage(Base):
    __tablename__ = "customer_chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(36), ForeignKey("customer_chat_conversations.id", ondelete="CASCADE"), nullable=False)
    reply_to_message_id = Column(Integer, ForeignKey("customer_chat_messages.id", ondelete="CASCADE"), nullable=True, unique=True)
    tenant_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    sender_type = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    client_message_id = Column(String(36), nullable=True)
    intent = Column(String(40), nullable=True)
    needs_escalation = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False, default="SUCCEEDED", server_default="SUCCEEDED")
    source_references = Column(JSON, nullable=False, default=list, server_default="[]")
    response_components = Column(JSON, nullable=False, default=list, server_default="[]")
    follow_up_suggestions = Column(JSON, nullable=False, default=list, server_default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("sender_type IN ('customer', 'assistant')", name="ck_customer_chat_message_sender"),
        CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_customer_chat_message_status"),
        CheckConstraint("needs_escalation IN (0, 1)", name="ck_customer_chat_message_escalation"),
        CheckConstraint("length(content) BETWEEN 1 AND 4000", name="ck_customer_chat_message_content_length"),
        UniqueConstraint("conversation_id", "client_message_id", name="uq_customer_chat_client_message"),
        Index("ix_customer_chat_messages_conversation_created", "conversation_id", "created_at", "id"),
        Index("ix_customer_chat_messages_tenant_conversation", "tenant_id", "conversation_id"),
    )


class CustomerSupportFAQ(Base):
    __tablename__ = "customer_support_faqs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    question = Column(String(500), nullable=False)
    faq_key = Column(String(100), nullable=True)
    alternate_questions = Column(JSON, nullable=False, default=list, server_default="[]")
    keywords = Column(JSON, nullable=False, default=list, server_default="[]")
    answer = Column(Text, nullable=False)
    category = Column(String(60), nullable=False)
    language = Column(String(12), nullable=False, default="en", server_default="en")
    is_published = Column(Integer, nullable=False, default=1, server_default="1")
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("is_published IN (0, 1)", name="ck_customer_support_faq_published"),
        Index("ix_customer_support_faq_scope", "tenant_id", "is_published", "category"),
    )
