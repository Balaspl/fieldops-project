from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..auth.dependencies import get_current_user, AuthenticatedUser


router = APIRouter(
    prefix="/dispatchers",
    tags=["Dispatchers"],
)


@router.get("")
async def get_dispatchers(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get dispatchers belonging ONLY to the current authenticated user's tenant.
    """

    # Get tenant from the authenticated JWT user
    tenant_id = current_user.tenant_id

    dispatchers = (
        db.query(
            models.User,
            models.Organization.name.label("organization_name"),
        )
        .outerjoin(
            models.Organization,
            models.Organization.id == models.User.tenant_id,
        )
        .filter(
            models.User.tenant_id == tenant_id,
            models.User.role == "dispatcher",
            models.User.deleted_at.is_(None),
        )
        .order_by(
            models.User.first_name,
            models.User.last_name,
        )
        .all()
    )

    return [
        {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "name": f"{user.first_name} {user.last_name}".strip(),
            "role": user.role,
            "tenant_id": user.tenant_id,
            "organization_name": organization_name,
            "is_active": user.is_active,
            "is_on_duty": user.is_on_duty,
            "phone_number": user.phone_number,
            "last_login": user.last_login,
        }
        for user, organization_name in dispatchers
    ]