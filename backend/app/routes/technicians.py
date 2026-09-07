from fastapi import APIRouter, Depends, HTTPException, status, Header, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Union, Optional
from sqlalchemy import func

from ..database import get_db
from .. import models, schemas
import uuid

from app.auth.dependencies import get_current_user_or_tenant, AuthenticatedUser

from ..schemas import NotificationPreferencesInput, PreferencesUpdateResponse
from ..services.preferences import (
    get_technician_preferences,
    update_technician_preferences,
    DEFAULT_PREFS,
)

from datetime import datetime, timezone


router = APIRouter(
    prefix="/technicians",
    tags=["Technicians"]
)


@router.post(
    "",
    response_model=Union[
        schemas.TechnicianResponse,
        List[schemas.TechnicianResponse]
    ],
    status_code=status.HTTP_200_OK
)
def create_technician(
    technician: Union[
        schemas.TechnicianCreate,
        List[schemas.TechnicianCreate]
    ],
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db)
):
    """
    Register one or more new technicians.

    Technicians are always created inside the authenticated user's tenant.
    Duplicate checks are also tenant-scoped.
    """
    user, tenant_id = user_tenant

    try:
        # Normalize to list for uniform processing
        tech_list = technician if isinstance(technician, list) else [technician]
        created_techs = []

        for tech_data in tech_list:

            # Check for duplicate only inside the current tenant
            existing = db.query(models.Technician).filter(
                models.Technician.technician_name == tech_data.technician_name,
                models.Technician.technician_skill == tech_data.technician_skill,
                models.Technician.tenant_id == tenant_id
            ).first()

            if existing:
                if not isinstance(technician, list):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Technician with name "
                            f"'{tech_data.technician_name}' and skill "
                            f"'{tech_data.technician_skill}' already exists"
                        )
                    )

                # For bulk, skip duplicates
                continue

            new_tech = models.Technician(
                tech_id=tech_data.tech_id or f"tech-{uuid.uuid4().hex[:8]}",
                technician_name=tech_data.technician_name,
                technician_skill=tech_data.technician_skill,
                technician_location=tech_data.technician_location,
                technician_status=tech_data.technician_status,
                tenant_id=tenant_id
            )

            db.add(new_tech)
            created_techs.append(new_tech)

        db.commit()

        # Refresh and return
        for t in created_techs:
            db.refresh(t)

        if isinstance(technician, list):
            return created_techs

        if not created_techs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Technician already exists"
            )

        return created_techs[0]

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while creating technician: {str(e)}"
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.get("", response_model=List[schemas.TechnicianResponse])
def get_all_technicians(
    response: Response,
    search: Optional[str] = None,
    status: Optional[str] = None,
    zone: Optional[str] = None,
    skill: Optional[str] = None,
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] = Query(None, ge=1),
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db)
):
    """
    Retrieve technicians belonging ONLY to the authenticated tenant.
    """
    user, tenant_id = user_tenant

    try:
        # ALWAYS tenant-scoped.
        # This also applies to super_admin.
        query = db.query(models.Technician).filter(
            models.Technician.tenant_id == tenant_id
        )

        if search:
            search_pattern = f"%{search}%"

            query = query.filter(
                (models.Technician.technician_name.ilike(search_pattern)) |
                (models.Technician.technician_skill.ilike(search_pattern)) |
                (models.Technician.technician_location.ilike(search_pattern))
            )

        if status and status.upper() != "ALL":
            query = query.filter(
                func.lower(models.Technician.technician_status)
                == status.lower()
            )

        if zone and zone.upper() != "ALL":
            query = query.filter(
                func.lower(models.Technician.technician_location)
                == zone.lower()
            )

        if skill and skill.upper() != "ALL":
            query = query.filter(
                func.lower(models.Technician.technician_skill)
                == skill.lower()
            )

        total_count = query.count()

        response.headers["X-Total-Count"] = str(total_count)
        response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

        query = query.order_by(
            models.Technician.technician_id.desc()
        )

        if page and limit:
            query = query.offset(
                (page - 1) * limit
            ).limit(limit)

        return query.all()

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error while fetching technicians: {str(e)}"
        )


@router.get(
    "/workload",
    response_model=schemas.WorkloadResponse
)
def get_technician_workload(
    technician_id: int,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Retrieve workload details of a technician
    belonging to the authenticated tenant.
    """
    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    return {
        "technician": tech.technician_name,
        "current_jobs": tech.current_jobs,
        "status": tech.technician_status
    }


@router.put(
    "/update-workload",
    response_model=schemas.WorkloadResponse
)
def update_technician_workload(
    update: schemas.WorkloadUpdate,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Update technician workload only inside the authenticated tenant.
    """
    from ..workload_utils import sync_technician_status

    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == update.technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    if update.current_jobs < 0:
        raise HTTPException(
            status_code=400,
            detail="Workload count cannot be negative"
        )

    tech.current_jobs = update.current_jobs
    sync_technician_status(tech)

    db.commit()
    db.refresh(tech)

    return {
        "technician": tech.technician_name,
        "current_jobs": tech.current_jobs,
        "status": tech.technician_status
    }


@router.put(
    "/update-status",
    response_model=schemas.TechnicianResponse
)
def update_technician_status(
    update: schemas.TechnicianStatusUpdate,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Update technician availability status only
    inside the authenticated tenant.
    """
    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == update.technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found"
        )

    tech.technician_status = update.status

    try:
        db.commit()
        db.refresh(tech)
        return tech

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@router.get(
    "/validate-workload",
    response_model=schemas.WorkloadValidationResponse
)
def validate_technician_workload_api(
    technician_id: int,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Validate workload only for a technician
    belonging to the authenticated tenant.
    """
    from ..validation import get_workload_validation_status

    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    return get_workload_validation_status(tech)


@router.get(
    "/available",
    response_model=List[schemas.AvailableTechnicianResponse]
)
def get_available_technicians(
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Retrieve available technicians ONLY from
    the authenticated user's tenant.
    """
    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.tenant_id == tenant_id
    )

    # Try fetching available or assigned technicians first
    available_query = query.filter(
        models.Technician.technician_status.in_(
            ["AVAILABLE", "ASSIGNED", "Available", "Assigned"]
        )
    )

    techs = available_query.all()

    # If no active/available technicians found,
    # fallback to all technicians from the same tenant
    if not techs:
        techs = query.all()

    result = []

    for tech in techs:
        is_eligible = (
            (tech.current_jobs or 0) < (tech.max_jobs or 5)
            and (tech.technician_status or "").upper()
            in ["AVAILABLE", "ASSIGNED"]
        )

        result.append({
            "technician_id": tech.technician_id,
            "technician": tech.technician_name,
            "skill": tech.technician_skill,
            "location": tech.technician_location,
            "status": tech.technician_status,
            "current_jobs": tech.current_jobs or 0,
            "max_jobs": tech.max_jobs or 5,
            "eligible_for_assignment": is_eligible
        })

    return result


@router.get(
    "/zones",
    response_model=List[str]
)
def get_all_zones(
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Retrieve technician zones/locations ONLY from
    the authenticated user's tenant.
    """
    user, tenant_id = user_tenant

    try:
        query = db.query(
            models.Technician.technician_location
        ).filter(
            models.Technician.tenant_id == tenant_id
        )

        results = query.distinct().all()

        # Filter out empty/null locations,
        # trim, remove duplicates, and sort.
        zones = sorted(
            list(
                set(
                    r[0].strip()
                    for r in results
                    if r[0] and r[0].strip()
                )
            )
        )

        return zones

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while fetching zones: {str(e)}"
        )


@router.get(
    "/{technician_id}",
    response_model=schemas.TechnicianResponse
)
def get_technician_by_id(
    technician_id: int,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Retrieve technician details only when the technician
    belongs to the authenticated tenant.
    """
    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    return tech


@router.put(
    "/{id}/availability"
)
def update_technician_availability(
    id: str,
    update_data: schemas.TechnicianAvailabilityUpdate,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Update technician availability by integer ID or
    string tech_id, only within the authenticated tenant.
    """
    user, tenant_id = user_tenant

    tech = None

    # Integer DB ID
    if id.isdigit():
        query = db.query(models.Technician).filter(
            models.Technician.technician_id == int(id),
            models.Technician.tenant_id == tenant_id
        )

        tech = query.first()

    # String tech_id
    if not tech:
        query = db.query(models.Technician).filter(
            models.Technician.tech_id == id,
            models.Technician.tenant_id == tenant_id
        )

        tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    # Validation is handled by Pydantic Literal
    tech.technician_status = update_data.technician_status

    db.commit()
    db.refresh(tech)

    return {
        "message": "Technician availability updated successfully",
        "technician": {
            "id": tech.technician_id,
            "tech_id": tech.tech_id,
            "name": tech.technician_name,
            "technician_status": tech.technician_status
        }
    }


@router.get("/{id}/preferences")
async def get_preferences(
    id: str,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    user, tenant_id = user_tenant

    prefs = get_technician_preferences(
        db=db,
        tech_id=id,
        tenant_id=tenant_id,
    )

    return {
        "tech_id": id,
        "preferences": prefs,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": "self"
    }


@router.patch(
    "/{id}/preferences",
    response_model=PreferencesUpdateResponse
)
async def update_preferences(
    id: str,
    payload: NotificationPreferencesInput,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    user, tenant_id = user_tenant

    try:
        updated_prefs = update_technician_preferences(
            db=db,
            tech_id=id,
            tenant_id=tenant_id,
            new_prefs=payload.model_dump(),
            updated_by="self"
        )

        if not updated_prefs:
            raise HTTPException(
                status_code=404,
                detail="Technician not found"
            )

        return {
            "tech_id": id,
            "preferences": updated_prefs,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "self"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "VALIDATION_FAILED",
                "message": str(e)
            }
        )


@router.post(
    "/{id}/preferences/reset"
)
async def reset_preferences(
    id: str,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    user, tenant_id = user_tenant

    try:
        updated_prefs = update_technician_preferences(
            db=db,
            tech_id=id,
            tenant_id=tenant_id,
            new_prefs=DEFAULT_PREFS.copy(),
            updated_by="self"
        )

        if not updated_prefs:
            raise HTTPException(
                status_code=404,
                detail="Technician not found"
            )

        return {
            "tech_id": id,
            "preferences": updated_prefs,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "self"
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "VALIDATION_FAILED",
                "message": str(e)
            }
        )


@router.put(
    "/{technician_id}",
    response_model=schemas.TechnicianResponse
)
def update_technician(
    technician_id: int,
    technician: schemas.TechnicianCreate,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Update technician details only inside
    the authenticated tenant.
    """
    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    tech.technician_name = technician.technician_name
    tech.technician_skill = technician.technician_skill
    tech.technician_location = technician.technician_location
    tech.technician_status = technician.technician_status

    try:
        db.commit()
        db.refresh(tech)
        return tech

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )


@router.delete(
    "/{technician_id}",
    status_code=status.HTTP_200_OK
)
def delete_technician(
    technician_id: int,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Delete technician only from the authenticated tenant.
    """
    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    try:
        db.delete(tech)
        db.commit()

        return {
            "message": "Technician deleted successfully"
        }

    except SQLAlchemyError as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )


@router.put(
    "/{technician_id}/status"
)
def update_technician_status_by_id(
    technician_id: int,
    update_data: schemas.TechnicianAvailabilityUpdate,
    user_tenant: tuple[
        Optional[AuthenticatedUser],
        str
    ] = Depends(get_current_user_or_tenant),
    db: Session = Depends(get_db),
):
    """
    Update technician status only inside
    the authenticated tenant.
    """
    user, tenant_id = user_tenant

    query = db.query(models.Technician).filter(
        models.Technician.technician_id == technician_id,
        models.Technician.tenant_id == tenant_id
    )

    tech = query.first()

    if not tech:
        raise HTTPException(
            status_code=404,
            detail="Technician not found"
        )

    tech.technician_status = update_data.technician_status

    try:
        db.commit()
        db.refresh(tech)

        return {
            "message": "Technician status updated successfully",
            "technician": {
                "id": tech.technician_id,
                "name": tech.technician_name,
                "technician_status": tech.technician_status
            }
        }

    except SQLAlchemyError as e:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )