from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from uuid import uuid4


class CompletionDocumentStorage:
    """
    Storage abstraction for completion documents.

    The database stores only the returned storage_key.
    The uploaded binary is stored outside the job/job_closure row.
    """

    def __init__(self, root_dir: str = "storage/completion_documents"):
        self.root_dir = Path(root_dir)

    def generate_storage_key(
        self,
        tenant_id: str,
        job_id: int,
        job_closure_id: int,
        category: str,
        original_filename: str,
    ) -> str:
        """
        Generate an opaque, unique storage key.

        The original filename is retained only as metadata and is
        never used directly as the filesystem path.
        """
        extension = Path(original_filename).suffix.lower()

        unique_id = uuid4().hex

        return (
            f"{tenant_id}/"
            f"jobs/{job_id}/"
            f"closures/{job_closure_id}/"
            f"{category.lower()}/"
            f"{unique_id}{extension}"
        )

    def save(
        self,
        file: BinaryIO,
        storage_key: str,
    ) -> str:
        """
        Store the uploaded binary and return its storage key.
        """
        destination = self.root_dir / storage_key

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with destination.open("wb") as output:
            while True:
                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                output.write(chunk)

        return storage_key

    def delete(self, storage_key: str) -> None:
        """
        Delete a stored document.

        Missing files are ignored so cleanup remains idempotent.
        """
        destination = self.root_dir / storage_key

        try:
            destination.unlink()
        except FileNotFoundError:
            pass