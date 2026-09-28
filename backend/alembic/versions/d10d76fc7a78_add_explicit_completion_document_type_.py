from alembic import op


# revision identifiers, used by Alembic.
revision = "d10d76fc7a78"
down_revision = "2d3db6c0e7a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE completion_documents
        ADD CONSTRAINT ck_completion_documents_document_type
        CHECK (document_type IN ('PHOTO', 'DOCUMENT'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE completion_documents
        DROP CONSTRAINT ck_completion_documents_document_type
        """
    )