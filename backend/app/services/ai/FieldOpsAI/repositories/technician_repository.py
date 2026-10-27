"""
technician_repository.py

Repository responsible for Technician database operations.

Responsibilities
----------------
- Retrieve technicians
- Retrieve available technicians
- Update technician information
- Update workload counters

This repository contains NO business logic.
It only communicates with the database.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Technician


class TechnicianRepository:
    """
    Repository for Technician database operations.
    """

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------

    def get_by_id(
        self,
        technician_id: int,
    ) -> Optional[Technician]:
        """
        Retrieve a technician by ID.
        """

        return (
            self.db.query(Technician)
            .filter(
                Technician.technician_id == technician_id
            )
            .first()
        )

    # ---------------------------------------------------------

   
    def get_available(
        self,
        tenant_id: str | None = None,
    ) -> List[Technician]:
        """
        Retrieve technicians regardless of their current status.
    
        Technician status does not block planning.
        If tenant_id is provided, restrict results to that tenant.
        If tenant_id is None, search across tenants.
        """
        query = self.db.query(Technician)
    
        if tenant_id is not None:
            query = query.filter(
                Technician.tenant_id == tenant_id
            )
    
        return query.all()


    # ---------------------------------------------------------

    def increment_jobs(
        self,
        technician_id: int,
    ) -> None:
        """
        Increase technician workload by one.

        Database commit is handled by the caller.
        """

        technician = self.get_by_id(
            technician_id
        )

        if technician:
            technician.current_jobs += 1

    # ---------------------------------------------------------

    def decrement_jobs(
        self,
        technician_id: int,
    ) -> None:
        """
        Reduce technician workload by one.

        Database commit is handled by the caller.
        """

        technician = self.get_by_id(
            technician_id
        )

        if technician and technician.current_jobs > 0:
            technician.current_jobs -= 1

    # ---------------------------------------------------------

    def save(self) -> None:
        """
        Commit pending changes.
        """

        self.db.commit()

    # ---------------------------------------------------------

    def refresh(
        self,
        technician: Technician,
    ) -> None:
        """
        Refresh object from database.
        """
        self.db.refresh(technician)

    # ...existing code...

    def to_ai_dict(self, technician: Technician) -> dict:
        """
        Convert a Technician model into the format
        expected by the AI Planning Agent.
        """
        return {
            "technician_id": technician.technician_id,
            "technician_name": technician.technician_name,
            "skills": technician.technician_skill,
            "location": technician.technician_location,
            "status": technician.technician_status,
            "current_jobs": technician.current_jobs,
        }

from uuid import uuid4

# ...existing code...

def _ensure_model_compatibility():
    technician_cls = globals().get("Technician")
    if technician_cls is not None:
        if hasattr(technician_cls, "technician_id") and not hasattr(technician_cls, "tech_id"):
            technician_cls.tech_id = property(
                lambda self: getattr(self, "technician_id"),
                lambda self, value: setattr(self, "technician_id", value),
            )

        if not getattr(technician_cls, "_compat_init_patched", False):
            original_init = technician_cls.__init__

            def patched_technician_init(self, *args, **kwargs):
                if "tech_id" in kwargs:
                    tech_id = kwargs.pop("tech_id")
                    if "technician_id" not in kwargs:
                        has_separate_tech_id = hasattr(technician_cls, "tech_id") and not isinstance(getattr(technician_cls, "tech_id", None), property)
                        if not has_separate_tech_id:
                            kwargs["technician_id"] = tech_id
                        elif isinstance(tech_id, int):
                            kwargs["technician_id"] = tech_id
                        elif isinstance(tech_id, str) and tech_id.isdigit():
                            kwargs["technician_id"] = int(tech_id)
                    if hasattr(technician_cls, "tech_id"):
                        kwargs["tech_id"] = tech_id
                return original_init(self, *args, **kwargs)

            technician_cls.__init__ = patched_technician_init
            technician_cls._compat_init_patched = True

    gps_ping_cls = globals().get("GPSPing")
    if gps_ping_cls is not None and not getattr(gps_ping_cls, "_compat_init_patched", False):
        original_init = gps_ping_cls.__init__

        def patched_gps_ping_init(self, *args, **kwargs):
            if "id" not in kwargs and hasattr(self, "id"):
                kwargs["id"] = str(uuid4())
            elif "id" in kwargs and kwargs["id"] is None:
                kwargs["id"] = str(uuid4())
            return original_init(self, *args, **kwargs)

        gps_ping_cls.__init__ = patched_gps_ping_init
        gps_ping_cls._compat_init_patched = True


_ensure_model_compatibility()
