import pytest

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import CompletionDocument
from app.repositories import CompletionDocumentRepository


# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield


@pytest.fixture
def db():
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_document(
    *,
    job_id=1001,
    tenant_id="tenant-1",
    checksum="a" * 64,
    storage_key="tenant-1/jobs/1001/documents/file.jpg",
):
    return CompletionDocument(
        job_closure_id=1,
        job_id=job_id,
        tenant_id=tenant_id,
        uploaded_by="tech-123",
        document_type="PHOTO",
        category="AFTER",
        original_filename="after.jpg",
        content_type="image/jpeg",
        file_size=1024,
        checksum_sha256=checksum,
        storage_key=storage_key,
        storage_url=None,
        status="PENDING",
    )


# ---------------------------------------------------------------------------
# 4.4.3 Requirement 1
# Metadata persists correctly
# ---------------------------------------------------------------------------

def test_completion_document_metadata_persists(db):
    document = _build_document()

    repository = CompletionDocumentRepository(db)

    repository.create(document)
    repository.save()

    stored = repository.get_by_id(document.id)

    assert stored is not None
    assert stored.id == document.id
    assert stored.job_id == 1001
    assert stored.job_closure_id == 1
    assert stored.tenant_id == "tenant-1"
    assert stored.uploaded_by == "tech-123"
    assert stored.document_type == "PHOTO"
    assert stored.category == "AFTER"
    assert stored.original_filename == "after.jpg"
    assert stored.content_type == "image/jpeg"
    assert stored.file_size == 1024
    assert stored.checksum_sha256 == "a" * 64
    assert stored.storage_key == (
        "tenant-1/jobs/1001/documents/file.jpg"
    )
    assert stored.status == "PENDING"
    assert stored.storage_url is None
    assert stored.created_at is not None
    assert stored.updated_at is not None


# ---------------------------------------------------------------------------
# 4.4.3 Requirement 2
# Job/tenant scoped retrieval is enforced
# ---------------------------------------------------------------------------

def test_document_retrieval_is_scoped_by_job_and_tenant(db):
    document = _build_document(
        job_id=1001,
        tenant_id="tenant-1",
        checksum="b" * 64,
        storage_key="tenant-1/jobs/1001/documents/a.jpg",
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    repository = CompletionDocumentRepository(db)

    # Correct job + tenant -> found.
    result = repository.get_by_id_for_job(
        document_id=document.id,
        job_id=1001,
        tenant_id="tenant-1",
    )

    assert result is not None
    assert result.id == document.id

    # Wrong job -> blocked.
    result = repository.get_by_id_for_job(
        document_id=document.id,
        job_id=9999,
        tenant_id="tenant-1",
    )

    assert result is None

    # Wrong tenant -> blocked.
    result = repository.get_by_id_for_job(
        document_id=document.id,
        job_id=1001,
        tenant_id="tenant-2",
    )

    assert result is None


def test_list_for_job_returns_only_matching_tenant_and_job(db):
    documents = [
        _build_document(
            job_id=1001,
            tenant_id="tenant-1",
            checksum="c" * 64,
            storage_key="tenant-1/jobs/1001/documents/1.jpg",
        ),
        _build_document(
            job_id=1001,
            tenant_id="tenant-1",
            checksum="d" * 64,
            storage_key="tenant-1/jobs/1001/documents/2.jpg",
        ),
        _build_document(
            job_id=1002,
            tenant_id="tenant-1",
            checksum="e" * 64,
            storage_key="tenant-1/jobs/1002/documents/3.jpg",
        ),
        _build_document(
            job_id=1001,
            tenant_id="tenant-2",
            checksum="f" * 64,
            storage_key="tenant-2/jobs/1001/documents/4.jpg",
        ),
    ]

    db.add_all(documents)
    db.commit()

    repository = CompletionDocumentRepository(db)

    result = repository.list_for_job(
        job_id=1001,
        tenant_id="tenant-1",
    )

    assert len(result) == 2
    assert {document.job_id for document in result} == {1001}
    assert {document.tenant_id for document in result} == {"tenant-1"}


# ---------------------------------------------------------------------------
# 4.4.3 Requirement 3
# Required metadata cannot be NULL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field_name",
    [
        "job_closure_id",
        "job_id",
        "tenant_id",
        "uploaded_by",
        "document_type",
        "category",
        "original_filename",
        "content_type",
        "file_size",
        "checksum_sha256",
        "storage_key",
        "status",
    ],
)
def test_required_completion_document_metadata_cannot_be_null(
    db,
    field_name,
):
    kwargs = {
        "job_closure_id": 1,
        "job_id": 1001,
        "tenant_id": "tenant-1",
        "uploaded_by": "tech-123",
        "document_type": "PHOTO",
        "category": "AFTER",
        "original_filename": "after.jpg",
        "content_type": "image/jpeg",
        "file_size": 1024,
        "checksum_sha256": "1" * 64,
        "storage_key": "tenant-1/jobs/1001/documents/null-test.jpg",
        "status": "PENDING",
    }

    kwargs[field_name] = None

    # Use a Core INSERT so an explicit NULL is sent to the database
    # instead of SQLAlchemy applying the model's server default.
    from sqlalchemy import insert

    statement = insert(CompletionDocument).values(**kwargs)

    with pytest.raises(IntegrityError):
        db.execute(statement)
        db.commit()

    db.rollback()

# ---------------------------------------------------------------------------
# 4.4.3 Requirement 4
# Checksum can detect duplicate content
# ---------------------------------------------------------------------------

def test_checksum_detects_duplicate_content_within_tenant(db):
    checksum = "2" * 64

    first_document = _build_document(
        job_id=1001,
        tenant_id="tenant-1",
        checksum=checksum,
        storage_key="tenant-1/jobs/1001/documents/first.jpg",
    )

    second_document = _build_document(
        job_id=1002,
        tenant_id="tenant-1",
        checksum=checksum,
        storage_key="tenant-1/jobs/1002/documents/second.jpg",
    )

    db.add_all([first_document, second_document])
    db.commit()

    repository = CompletionDocumentRepository(db)

    duplicate = repository.get_by_checksum(
        checksum_sha256=checksum,
        tenant_id="tenant-1",
    )

    assert duplicate is not None
    assert duplicate.checksum_sha256 == checksum


def test_same_checksum_in_another_tenant_is_not_returned(db):
    checksum = "3" * 64

    document = _build_document(
        job_id=1001,
        tenant_id="tenant-1",
        checksum=checksum,
        storage_key="tenant-1/jobs/1001/documents/tenant1.jpg",
    )

    db.add(document)
    db.commit()

    repository = CompletionDocumentRepository(db)

    result = repository.get_by_checksum(
        checksum_sha256=checksum,
        tenant_id="tenant-2",
    )

    assert result is None


# ---------------------------------------------------------------------------
# 4.4.3 Requirement 2 / 3
# Indexes and foreign keys exist
# ---------------------------------------------------------------------------

def test_job_and_tenant_indexes_exist():
    inspector = inspect(engine)

    indexes = inspector.get_indexes(
        "completion_documents"
    )

    index_names = {
        index["name"]
        for index in indexes
    }

    assert "idx_completion_documents_tenant_job" in index_names
    assert "idx_completion_documents_job_type" in index_names


def test_completion_document_foreign_keys_exist():
    inspector = inspect(engine)

    foreign_keys = inspector.get_foreign_keys(
        "completion_documents"
    )

    fk_pairs = {
        (
            foreign_key["constrained_columns"][0],
            foreign_key["referred_table"],
        )
        for foreign_key in foreign_keys
    }

    assert (
        "job_id",
        "jobs",
    ) in fk_pairs

    assert (
        "job_closure_id",
        "job_closures",
    ) in fk_pairs

    assert (
        "tenant_id",
        "organizations",
    ) in fk_pairs


# ---------------------------------------------------------------------------
# 4.4.3 Requirement 4
# Raw binary content must not be stored in PostgreSQL
# ---------------------------------------------------------------------------

def test_completion_document_has_no_raw_file_content_column():
    columns = {
        column.name
        for column in CompletionDocument.__table__.columns
    }

    assert "file_content" not in columns
    assert "content" not in columns
    assert "blob" not in columns

    assert "storage_key" in columns
    assert "checksum_sha256" in columns