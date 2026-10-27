"""
Services Catalog Model.

Represents service types, categories, and specific issues configured by Super Admin
for customer booking intake, with multi-tenant organization isolation.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Boolean,
    Index,
)
from sqlalchemy.sql import func
from ..database import Base


class ServiceCatalogItem(Base):
    """
    Service catalog item configured by Super Admin.
    Hierarchy: Service Type -> Category -> Issue.
    Scoped by tenant_id (organization).
    """
    __tablename__ = "services_catalog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=True, index=True)
    created_by_user_id = Column(String(36), nullable=True)

    service_type = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    issue = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    priority = Column(String(20), default="NORMAL", nullable=True)
    required_skill = Column(String(100), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_sc_tenant", "tenant_id"),
        Index("idx_sc_type_cat", "service_type", "category"),
        Index("idx_sc_active", "is_active"),
        Index("idx_sc_tenant_active", "tenant_id", "is_active"),
    )
