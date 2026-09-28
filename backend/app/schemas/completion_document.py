from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocumentType = Literal[
    "PHOTO",
    "DOCUMENT",
]

CompletionDocumentStatus = Literal[
    "PENDING",
    "AVAILABLE",
    "REJECTED",
]

CompletionDocumentScanStatus = Literal[
    "PENDING",
    "CLEAN",
    "REJECTED",
]


class CompletionDocumentCreate(BaseModel):
    job_closure_id: int
    job_id: int

    tenant_id: str = Field(
        min_length=1,
        max_length=50,
    )

    uploaded_by: str = Field(
        min_length=1,
        max_length=50,
    )

    document_type: DocumentType

    category: str = Field(
        min_length=1,
        max_length=20,
    )

    original_filename: str = Field(
        min_length=1,
        max_length=255,
    )

    content_type: str = Field(
        min_length=1,
        max_length=100,
    )

    file_size: int = Field(
        gt=0,
    )

    checksum_sha256: str = Field(
        min_length=64,
        max_length=64,
    )

    storage_key: str = Field(
        min_length=1,
        max_length=500,
    )

    storage_url: str | None = None

    status: CompletionDocumentStatus = "PENDING"

    scan_status: CompletionDocumentScanStatus = "PENDING"

    scanned_at: datetime | None = None


class CompletionDocumentResponse(BaseModel):
    id: int
    job_id: int
    job_closure_id: int
    tenant_id: str
    uploaded_by: str
    document_type: DocumentType
    category: str
    original_filename: str
    content_type: str
    file_size: int
    checksum_sha256: str
    storage_key: str
    storage_url: str | None
    status: CompletionDocumentStatus
    scan_status: CompletionDocumentScanStatus
    scanned_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class CompletionDocumentMetadata(BaseModel):
    id: int
    document_type: DocumentType
    category: str
    original_filename: str
    content_type: str
    file_size: int
    checksum_sha256: str
    status: CompletionDocumentStatus
    scan_status: CompletionDocumentScanStatus
    scanned_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
    )