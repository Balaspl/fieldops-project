from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "219895425dee"
down_revision = "1a02f91166b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # Add document_type to existing completion documents.
    #
    # Existing records were photo uploads, so initialize them
    # as PHOTO.
    # ---------------------------------------------------------
    op.add_column(
        "completion_documents",
        sa.Column(
            "document_type",
            sa.String(length=20),
            nullable=True,
            server_default="PHOTO",
        ),
    )

    # Make document_type mandatory after existing rows have
    # received the PHOTO value.
    op.alter_column(
        "completion_documents",
        "document_type",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default=None,
    )

    # ---------------------------------------------------------
    # Remove old category constraint.
    # ---------------------------------------------------------
    op.drop_constraint(
        "ck_completion_documents_category",
        "completion_documents",
        type_="check",
    )

    # ---------------------------------------------------------
    # Add the new document_type/category constraint.
    # ---------------------------------------------------------
    op.create_check_constraint(
        "ck_completion_documents_category",
        "completion_documents",
        """
        (
            document_type = 'PHOTO'
            AND category IN ('BEFORE', 'AFTER')
        )
        OR
        (
            document_type = 'DOCUMENT'
            AND category IN (
                'MANUAL',
                'SERVICE_REPORT',
                'CERTIFICATE',
                'OTHER'
            )
        )
        """,
    )

    # ---------------------------------------------------------
    # Index job_id + document_type.
    # ---------------------------------------------------------
    op.create_index(
        "idx_completion_documents_job_type",
        "completion_documents",
        ["job_id", "document_type"],
        unique=False,
    )


def downgrade() -> None:
    # ---------------------------------------------------------
    # Remove the new index.
    # ---------------------------------------------------------
    op.drop_index(
        "idx_completion_documents_job_type",
        table_name="completion_documents",
    )

    # ---------------------------------------------------------
    # Remove the new category constraint.
    # ---------------------------------------------------------
    op.drop_constraint(
        "ck_completion_documents_category",
        "completion_documents",
        type_="check",
    )

    # ---------------------------------------------------------
    # Restore original category constraint.
    # ---------------------------------------------------------
    op.create_check_constraint(
        "ck_completion_documents_category",
        "completion_documents",
        "category IN ('BEFORE', 'AFTER')",
    )

    # ---------------------------------------------------------
    # Remove document_type.
    # ---------------------------------------------------------
    op.drop_column(
        "completion_documents",
        "document_type",
    )