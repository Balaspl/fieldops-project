"""add completion documents

Revision ID: ad0f8cad1a9a
Revises: 621b2ee94385
Create Date: 2026-09-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ad0f8cad1a9a"
down_revision: Union[str, Sequence[str], None] = "621b2ee94385"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "completion_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_closure_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("storage_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("uploaded_by", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('BEFORE', 'AFTER')",
            name="ck_completion_documents_category",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'AVAILABLE', 'REJECTED')",
            name="ck_completion_documents_status",
        ),
        sa.CheckConstraint(
            "file_size > 0",
            name="ck_completion_documents_file_size_positive",
        ),
        sa.ForeignKeyConstraint(
            ["job_closure_id"],
            ["job_closures.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )

    op.create_index(
        "ix_completion_documents_id",
        "completion_documents",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_completion_documents_job_closure_id",
        "completion_documents",
        ["job_closure_id"],
        unique=False,
    )

    op.create_index(
        "ix_completion_documents_job_id",
        "completion_documents",
        ["job_id"],
        unique=False,
    )

    op.create_index(
        "ix_completion_documents_tenant_id",
        "completion_documents",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        "idx_completion_documents_tenant_job",
        "completion_documents",
        ["tenant_id", "job_id"],
        unique=False,
    )

    op.create_index(
        "idx_completion_documents_closure_category",
        "completion_documents",
        ["job_closure_id", "category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_completion_documents_closure_category",
        table_name="completion_documents",
    )

    op.drop_index(
        "idx_completion_documents_tenant_job",
        table_name="completion_documents",
    )

    op.drop_index(
        "ix_completion_documents_tenant_id",
        table_name="completion_documents",
    )

    op.drop_index(
        "ix_completion_documents_job_id",
        table_name="completion_documents",
    )

    op.drop_index(
        "ix_completion_documents_job_closure_id",
        table_name="completion_documents",
    )

    op.drop_index(
        "ix_completion_documents_id",
        table_name="completion_documents",
    )

    op.drop_table("completion_documents")